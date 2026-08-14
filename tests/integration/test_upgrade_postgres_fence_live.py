"""Live PostgreSQL integration coverage for Upgrade-31 stale-writer fencing."""

from __future__ import annotations

import os
import time
import uuid
from contextlib import contextmanager

import psycopg2
import pytest

from zcoder.domain.models.engineering import EngineeringTask, TaskStatus
from zcoder.services.upgrade_postgres_fence import (
    PostgresUpgradeFence,
    StalePostgresUpgradeFenceError,
)

PG_URL = os.environ.get("DATABASE_URL", "")


def pg_is_available() -> bool:
    if not PG_URL:
        return False
    try:
        connection = psycopg2.connect(PG_URL, connect_timeout=2)
        connection.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not pg_is_available(), reason="DATABASE_URL PostgreSQL instance not reachable")


@contextmanager
def connection_scope():
    connection = psycopg2.connect(PG_URL, connect_timeout=2)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def ensure_schema() -> None:
    with connection_scope() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS engineering_tasks (
                    id TEXT PRIMARY KEY,
                    task_description TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at DOUBLE PRECISION NOT NULL,
                    updated_at DOUBLE PRECISION NOT NULL,
                    metadata JSONB NOT NULL DEFAULT '{}'
                )
                """
            )


def fetch_task(task_id: str):
    with connection_scope() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT status, metadata FROM engineering_tasks WHERE id = %s", (task_id,))
            return cursor.fetchone()


def test_new_generation_fences_stale_writer_in_same_transaction_boundary():
    ensure_schema()
    unique = uuid.uuid4().hex
    namespace = f"upgrade31-live-{unique}"
    control_task_id = f"upgrade-ledger-{unique}-control"
    fence = PostgresUpgradeFence(connection_scope, namespace=namespace, control_task_id=control_task_id)

    first = fence.acquire_token()
    assert first.generation == 1

    task_one = EngineeringTask(
        id=f"upgrade-work-{unique}-one",
        task_description="first generation write",
        status=TaskStatus.PAUSED,
        created_at=time.time(),
        metadata={"generation": 1},
    )
    fence.save_task(task_one, first)
    assert fetch_task(task_one.id)[0] == TaskStatus.PAUSED.value

    second = fence.acquire_token()
    assert second.generation == 2

    stale_task = EngineeringTask(
        id=f"upgrade-work-{unique}-stale",
        task_description="must never persist",
        status=TaskStatus.PAUSED,
        created_at=time.time(),
        metadata={"generation": 1},
    )
    with pytest.raises(StalePostgresUpgradeFenceError, match="stale PostgreSQL upgrade fence"):
        fence.save_task(stale_task, first)
    assert fetch_task(stale_task.id) is None

    current_task = EngineeringTask(
        id=f"upgrade-work-{unique}-current",
        task_description="current generation write",
        status=TaskStatus.PAUSED,
        created_at=time.time(),
        metadata={"generation": 2},
    )
    fence.save_task(current_task, second)
    assert fetch_task(current_task.id)[0] == TaskStatus.PAUSED.value


def test_control_checkpoint_write_preserves_fence_generation():
    ensure_schema()
    unique = uuid.uuid4().hex
    namespace = f"upgrade31-control-{unique}"
    control_task_id = f"upgrade-ledger-{unique}-control"
    fence = PostgresUpgradeFence(connection_scope, namespace=namespace, control_task_id=control_task_id)
    token = fence.acquire_token()

    control = EngineeringTask(
        id=control_task_id,
        task_description="ledger checkpoint control",
        status=TaskStatus.PAUSED,
        created_at=time.time(),
        metadata={
            "zcoder_upgrade_ledger": {
                "schema_version": 1,
                "record_type": "control",
                "namespace": namespace,
                "checkpoints": [{"iteration": 1}],
            }
        },
    )
    fence.save_task(control, token)
    fence.assert_current(token)

    row = fetch_task(control_task_id)
    assert row[1]["zcoder_upgrade_ledger"]["fence_generation"] == token.generation
    assert row[1]["zcoder_upgrade_ledger"]["checkpoints"] == [{"iteration": 1}]

    newer = fence.acquire_token()
    assert newer.generation == token.generation + 1
    with pytest.raises(StalePostgresUpgradeFenceError):
        fence.assert_current(token)
    fence.assert_current(newer)
