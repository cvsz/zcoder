"""Live PostgreSQL integration coverage for the Upgrade-33 continuous backend."""

from __future__ import annotations

import os
import uuid
from types import SimpleNamespace

import psycopg2
import pytest

import zcoder.services.continuous_engineering as continuous_engineering
from zcoder.services.upgrade_loop import LoopPolicy, LoopState, ValidationResult, feature_work
from zcoder.services.upgrade_postgres_lease import PostgresUpgradeRunLeaseError

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


pytestmark = pytest.mark.skipif(
    not pg_is_available(), reason="DATABASE_URL PostgreSQL instance not reachable"
)


class PassingExecutor:
    def __init__(self) -> None:
        self.calls = []

    def execute(self, item):
        self.calls.append(item.fingerprint)
        return SimpleNamespace(task_id=item.item_id, status="SUCCEEDED")

    def validate(self, item, execution):
        return ValidationResult(passed=True, summary="passed")


def _build(monkeypatch, tmp_path, namespace, executor):
    monkeypatch.setattr(
        continuous_engineering,
        "_build_upgrade20_executor",
        lambda *args, **kwargs: executor,
    )
    return continuous_engineering.build_postgres_store_pipeline(
        tmp_path,
        PG_URL,
        ledger_namespace=namespace,
        policy=LoopPolicy(max_iterations=3),
    )


def test_live_postgres_backend_persists_success_and_deduplicates_restart(monkeypatch, tmp_path):
    namespace = f"upgrade33-restart-{uuid.uuid4().hex}"
    item = feature_work("PostgreSQL backend feature", "Execute exactly once across restart")

    first_executor = PassingExecutor()
    first = _build(monkeypatch, tmp_path, namespace, first_executor)
    try:
        first_report = first.run([item])
        assert first_report.state == LoopState.COMPLETED
        assert first_executor.calls == [item.fingerprint]
        assert first.ledger.terminal_counts()["SUCCEEDED"] == 1
    finally:
        first.close()

    second_executor = PassingExecutor()
    second = _build(monkeypatch, tmp_path, namespace, second_executor)
    try:
        duplicate = feature_work("PostgreSQL backend feature", "Execute exactly once across restart")
        second_report = second.run([duplicate])
        assert second_report.state == LoopState.COMPLETED
        assert second_executor.calls == []
        assert second.ledger.terminal_counts()["SUCCEEDED"] == 1
    finally:
        second.close()


def test_live_postgres_backend_excludes_concurrent_runner(monkeypatch, tmp_path):
    namespace = f"upgrade33-contention-{uuid.uuid4().hex}"
    first = _build(monkeypatch, tmp_path, namespace, PassingExecutor())
    second = _build(monkeypatch, tmp_path, namespace, PassingExecutor())

    first.run_lease.acquire()
    try:
        with pytest.raises(PostgresUpgradeRunLeaseError, match="already held"):
            second.run([feature_work("Contending feature", "Must not execute concurrently")])
    finally:
        first.run_lease.release()
        first.close()
        second.close()
