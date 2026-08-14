"""Unit coverage for Upgrade-34 bounded maintenance campaigns."""

import json
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

import zcoder.services.maintenance_campaign as maintenance_campaign
from zcoder.services.maintenance_campaign import (
    MaintenanceCampaignService,
    load_signals_file,
    maintenance_campaign_work,
)
from zcoder.services.upgrade_loop import LoopReport, LoopState, WorkKind


@dataclass
class FakeRecommendation:
    id: str
    repository: str = "cvsz/zcoder"
    type: str = "PATCH_DEPENDENCY"
    priority: int = 7
    risk: str = "low"
    reason: str = "Dependency outdated: demo"


class FakeIntelligence:
    def __init__(self, recommendations):
        self.recommendations = list(recommendations)

    def generate_recommendations(self):
        return list(self.recommendations)


class FakePipeline:
    def __init__(self, report=None):
        self.seed = None
        self.closed = False
        self.ledger = SimpleNamespace(terminal_counts=lambda: {"SUCCEEDED": 2, "BLOCKED": 0})
        self.report = report or LoopReport(
            state=LoopState.COMPLETED,
            iterations=2,
            completed_item_ids=("a", "b"),
            blocked_item_ids=(),
            pending_item_ids=(),
            records=(),
        )

    def run(self, seed):
        self.seed = list(seed)
        return self.report

    def close(self):
        self.closed = True


def test_campaign_work_ignores_volatile_recommendation_uuid_for_fingerprint():
    first = maintenance_campaign_work(FakeRecommendation(id="rec-random-one"))
    second = maintenance_campaign_work(FakeRecommendation(id="rec-random-two"))

    assert first.kind == WorkKind.UPDATE
    assert first.fingerprint == second.fingerprint
    assert first.payload["recommendation_key"] == second.payload["recommendation_key"]
    assert "recommendation_id" not in first.payload


def test_campaign_deduplicates_equivalent_recommendations_before_pipeline():
    recommendations = [FakeRecommendation(id="rec-1"), FakeRecommendation(id="rec-2")]
    pipeline = FakePipeline()

    report = MaintenanceCampaignService(pipeline, FakeIntelligence(recommendations)).run()

    assert report.recommendations_discovered == 2
    assert report.work_seeded == 1
    assert len(pipeline.seed) == 1
    assert report.state == LoopState.COMPLETED.value
    assert report.completed_count == 2


def test_empty_campaign_still_invokes_pipeline_to_resume_durable_work():
    pipeline = FakePipeline(
        LoopReport(
            state=LoopState.COMPLETED,
            iterations=0,
            completed_item_ids=(),
            blocked_item_ids=(),
            pending_item_ids=(),
            records=(),
        )
    )

    report = MaintenanceCampaignService(pipeline, FakeIntelligence([])).run()

    assert pipeline.seed == []
    assert report.recommendations_discovered == 0
    assert report.work_seeded == 0
    assert report.iterations == 0


def test_campaign_report_preserves_blocked_and_halt_summary():
    pipeline = FakePipeline(
        LoopReport(
            state=LoopState.HALTED,
            iterations=1,
            completed_item_ids=(),
            blocked_item_ids=("blocked",),
            pending_item_ids=("pending",),
            records=(),
            halt_reason="blocked_work_remaining",
        )
    )

    report = MaintenanceCampaignService(
        pipeline,
        FakeIntelligence([FakeRecommendation(id="rec-1")]),
    ).run()

    assert report.state == LoopState.HALTED.value
    assert report.blocked_count == 1
    assert report.pending_count == 1
    assert report.halt_reason == "blocked_work_remaining"
    assert report.duration_seconds >= 0


def test_load_signals_file_validates_and_builds_supported_signals(tmp_path):
    path = tmp_path / "signals.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "signal-1",
                    "repository": "cvsz/zcoder",
                    "type": "dependency_outdated",
                    "source": "dependency-scan",
                    "evidence": {"package": "demo"},
                },
                {
                    "repository": "cvsz/zcoder",
                    "type": "CI_FAILURE",
                    "source": "github-actions",
                },
            ]
        ),
        encoding="utf-8",
    )

    signals = load_signals_file(path)

    assert len(signals) == 2
    assert signals[0].id == "signal-1"
    assert signals[0].type.value == "DEPENDENCY_OUTDATED"
    assert signals[0].evidence == {"package": "demo"}
    assert signals[1].type.value == "CI_FAILURE"


def test_load_signals_file_rejects_unknown_signal_type(tmp_path):
    path = tmp_path / "signals.json"
    path.write_text('[{"type":"UNKNOWN"}]', encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported maintenance signal type"):
        load_signals_file(path)


def test_postgres_campaign_cli_uses_environment_secret_without_output(tmp_path, monkeypatch, capsys):
    secret = "postgresql://campaign-user:campaign-password@db.invalid/zcoder"
    pipeline = FakePipeline(
        LoopReport(
            state=LoopState.COMPLETED,
            iterations=0,
            completed_item_ids=(),
            blocked_item_ids=(),
            pending_item_ids=(),
            records=(),
        )
    )
    captured = {}
    monkeypatch.setenv("DATABASE_URL", secret)

    def fake_builder(repository_root, database_url, **kwargs):
        captured["database_url"] = database_url
        captured["namespace"] = kwargs["ledger_namespace"]
        return pipeline

    monkeypatch.setattr(maintenance_campaign, "build_postgres_store_pipeline", fake_builder)

    result = maintenance_campaign.main(
        [
            "--repository",
            str(tmp_path),
            "--state-backend",
            "postgres",
            "--ledger-namespace",
            "campaign-prod",
        ]
    )

    output = capsys.readouterr().out
    assert result == 0
    assert captured == {"database_url": secret, "namespace": "campaign-prod"}
    assert pipeline.closed is True
    assert secret not in output
    assert "campaign-password" not in output


def test_campaign_cli_defaults_to_json_backend():
    args = maintenance_campaign.build_parser().parse_args([])

    assert args.state_backend == "json"
    assert args.ledger_namespace == "zcoder-maintenance-campaign"
