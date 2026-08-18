"""Live PostgreSQL integration coverage for Upgrade-34 maintenance campaigns."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from types import SimpleNamespace

import psycopg2
import pytest

import zcoder.interfaces.cli.continuous_engineering as continuous_engineering
from zcoder.services.maintenance_campaign import MaintenanceCampaignService
from zcoder.services.upgrade_loop import LoopPolicy, LoopState, ValidationResult

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


@dataclass
class Recommendation:
    id: str
    repository: str = "cvsz/zcoder"
    type: str = "PATCH_DEPENDENCY"
    priority: int = 4
    risk: str = "low"
    reason: str = "Dependency outdated: campaign-demo"


class Intelligence:
    def __init__(self, recommendation_id):
        self.recommendation_id = recommendation_id

    def generate_recommendations(self):
        return [Recommendation(id=self.recommendation_id)]


class PassingExecutor:
    def __init__(self):
        self.calls = []

    def execute(self, item):
        self.calls.append(item.fingerprint)
        return SimpleNamespace(task_id=item.item_id, status="SUCCEEDED")

    def validate(self, item, execution):
        return ValidationResult(passed=True, summary="passed")


def _pipeline(monkeypatch, tmp_path, namespace, executor):
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


def test_live_campaign_deduplicates_equivalent_recommendation_across_runs(monkeypatch, tmp_path):
    namespace = f"upgrade34-campaign-{uuid.uuid4().hex}"

    first_executor = PassingExecutor()
    first = _pipeline(monkeypatch, tmp_path, namespace, first_executor)
    try:
        first_report = MaintenanceCampaignService(first, Intelligence("volatile-rec-1")).run()
        assert first_report.state == LoopState.COMPLETED.value
        assert first_report.recommendations_discovered == 1
        assert first_report.work_seeded == 1
        assert len(first_executor.calls) == 1
    finally:
        first.close()

    second_executor = PassingExecutor()
    second = _pipeline(monkeypatch, tmp_path, namespace, second_executor)
    try:
        second_report = MaintenanceCampaignService(second, Intelligence("volatile-rec-2")).run()
        assert second_report.state == LoopState.COMPLETED.value
        assert second_report.recommendations_discovered == 1
        assert second_report.work_seeded == 1
        assert second_executor.calls == []
        assert second.ledger.terminal_counts()["SUCCEEDED"] == 1
    finally:
        second.close()
