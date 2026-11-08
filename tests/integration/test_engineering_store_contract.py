"""Cross-backend contract tests for the durable EngineeringStore interface.

The same persistence contract is exercised against SQLite (default local-first
mode) and PostgreSQL (shared server mode). The PostgreSQL runs are fully
isolated: every test creates a throwaway schema, points the store's
``search_path`` at it, and drops the schema in teardown. No shared table rows,
schema objects or credentials are read or modified.
"""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import Iterator
from typing import Any

import pytest

from zcoder.domain.models.engineering import Attempt, Checkpoint, EngineeringTask, TaskStatus
from zcoder.infrastructure.stores.sqlite_engineering import SQLiteEngineeringStore


def _dsn_with_search_path(dsn: str, schema: str) -> str:
    """Return ``dsn`` with libpq ``options`` selecting an isolated schema."""
    separator = "&" if "?" in dsn else "?"
    return f"{dsn}{separator}options=-csearch_path%3D{schema}"


def _postgres_store() -> Iterator[tuple[Any, list[str]]]:
    dsn = os.environ.get("DATABASE_URL", "")
    if not dsn:
        pytest.skip("DATABASE_URL PostgreSQL instance not configured")
        return

    try:
        import psycopg2
        from zcoder.infrastructure.stores.postgres_engineering import PostgresEngineeringStore
    except ImportError as exc:  # pragma: no cover - optional dependency
        pytest.skip(f"PostgreSQL driver unavailable: {exc}")
        return

    schema = f"zcoder_contract_{uuid.uuid4().hex}"
    try:
        admin = psycopg2.connect(dsn, connect_timeout=3)
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"PostgreSQL instance not reachable: {exc}")
        return

    try:
        admin.autocommit = True
        with admin.cursor() as cur:
            cur.execute(f'CREATE SCHEMA "{schema}"')
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"PostgreSQL schema creation not permitted: {exc}")
        return
    finally:
        admin.close()

    store: PostgresEngineeringStore | None = None
    try:
        postgres_store = PostgresEngineeringStore(
            dsn=_dsn_with_search_path(dsn, schema),
            min_conn=1,
            max_conn=2,
            connect_timeout=3,
        )
        store = postgres_store
        postgres_store.init_schema()
        yield postgres_store, []
    finally:
        try:
            if store is not None:
                store.close()
        finally:
            cleanup = psycopg2.connect(dsn, connect_timeout=3)
            try:
                cleanup.autocommit = True
                with cleanup.cursor() as cur:
                    cur.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            finally:
                cleanup.close()


@pytest.fixture(params=["sqlite", "postgres"])
def store_and_created(request: pytest.FixtureRequest, tmp_path) -> Iterator[tuple[Any, list[str]]]:
    if request.param == "sqlite":
        yield SQLiteEngineeringStore(db_path=tmp_path / "contract.db"), []
        return
    yield from _postgres_store()


def _save_task(store: Any, created: list[str]) -> EngineeringTask:
    task = EngineeringTask(
        id=f"contract_{uuid.uuid4().hex}",
        task_description="cross-backend contract task",
        metadata={"suite": "engineering-store-contract"},
    )
    created.append(task.id)
    store.save_task(task)
    return task


def test_task_roundtrip_contract(store_and_created: tuple[Any, list[str]]) -> None:
    store, created = store_and_created
    task = _save_task(store, created)

    loaded = store.get_task(task.id)
    assert loaded is not None
    assert loaded.id == task.id
    assert loaded.task_description == task.task_description
    assert loaded.status == TaskStatus.CREATED
    assert loaded.metadata == task.metadata


def test_task_update_and_listing_contract(store_and_created: tuple[Any, list[str]]) -> None:
    store, created = store_and_created
    task = _save_task(store, created)

    task.status = TaskStatus.SUCCEEDED
    store.save_task(task)

    loaded = store.get_task(task.id)
    assert loaded is not None
    assert loaded.status == TaskStatus.SUCCEEDED
    assert task.id in {item.id for item in store.list_tasks()}
    assert task.id in {item.id for item in store.list_tasks(status=TaskStatus.SUCCEEDED)}


def test_attempt_and_latest_checkpoint_contract(store_and_created: tuple[Any, list[str]]) -> None:
    store, created = store_and_created
    task = _save_task(store, created)
    attempt = Attempt(id=f"contract_att_{uuid.uuid4().hex}", task_id=task.id)
    created.append(attempt.id)
    store.create_attempt(attempt)

    first = Checkpoint(
        id=f"contract_chk_{uuid.uuid4().hex}",
        task_id=task.id,
        attempt_id=attempt.id,
        sequence=1,
        phase="start",
        state_snapshot={"step": 1},
    )
    second = Checkpoint(
        id=f"contract_chk_{uuid.uuid4().hex}",
        task_id=task.id,
        attempt_id=attempt.id,
        sequence=2,
        phase="finish",
        state_snapshot={"step": 2},
    )
    for checkpoint in (first, second):
        created.append(checkpoint.id)
        store.save_checkpoint(checkpoint)

    latest = store.get_latest_checkpoint(attempt.id)
    assert latest is not None
    assert latest.id == second.id
    assert latest.sequence == 2
    assert latest.phase == "finish"


def test_claim_returns_running_task_contract(store_and_created: tuple[Any, list[str]]) -> None:
    """Claim must atomically hand out a RUNNING task on both backends.

    PostgreSQL runs inside a throwaway schema, so the oldest CREATED row is
    always the task created here. The row is dated earlier than wall-clock time
    to keep the ordering unambiguous.
    """
    store, created = store_and_created
    task = EngineeringTask(
        id=f"contract_{uuid.uuid4().hex}",
        task_description="claim contract task",
        created_at=0.0,
    )
    created.append(task.id)
    store.save_task(task)
    time.sleep(0.01)

    claimed = store.claim_task()
    assert claimed is not None
    assert claimed.id == task.id
    assert claimed.status == TaskStatus.RUNNING
