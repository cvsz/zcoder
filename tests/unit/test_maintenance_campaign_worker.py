from __future__ import annotations

from dataclasses import dataclass

import pytest

from zcoder.services.maintenance_campaign import (
    MaintenanceCampaignReport,
    MaintenanceCampaignRunResult,
)
from zcoder.services import maintenance_campaign_worker as worker


@dataclass
class _Message:
    id: str


class _Outbox:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, dict]] = []

    def enqueue_outbox(self, action: str, payload: dict):
        self.calls.append((action, payload))
        if self.fail:
            raise RuntimeError("outbox unavailable")
        return _Message("out_test1234")


def _run_result(*, state: str = "COMPLETED", exit_code: int = 0) -> MaintenanceCampaignRunResult:
    return MaintenanceCampaignRunResult(
        report=MaintenanceCampaignReport(
            campaign_id="maintenance-test",
            state=state,
            recommendations_discovered=3,
            work_seeded=2,
            iterations=1,
            completed_count=2,
            blocked_count=0,
            pending_count=0,
            halt_reason="",
            terminal_ledger_counts={"completed": 2},
            observer_error_count=0,
            started_at=10.0,
            finished_at=12.5,
        ),
        exit_code=exit_code,
    )


def test_summary_payload_is_versioned_secret_free_and_idempotent():
    payload = worker.maintenance_campaign_summary_payload(_run_result())

    assert payload["schema_version"] == 1
    assert payload["idempotency_key"] == "maintenance-campaign:maintenance-test"
    assert payload["exit_code"] == 0
    assert payload["report"]["campaign_id"] == "maintenance-test"
    assert payload["report"]["duration_seconds"] == 2.5
    serialized = repr(payload)
    assert "DATABASE_URL" not in serialized
    assert "api_key" not in serialized
    assert "recommendation evidence" not in serialized


def test_worker_runs_one_campaign_and_enqueues_one_summary(monkeypatch):
    result = _run_result()
    calls = []

    def fake_run(pipeline, intelligence, event_sink=None):
        calls.append((pipeline, intelligence, event_sink))
        return result

    monkeypatch.setattr(worker, "run_maintenance_campaign_once", fake_run)
    outbox = _Outbox()
    sink = object()

    dispatched = worker.run_maintenance_campaign_worker_once("pipeline", "intel", outbox, event_sink=sink)

    assert calls == [("pipeline", "intel", sink)]
    assert len(outbox.calls) == 1
    assert outbox.calls[0][0] == worker.MAINTENANCE_CAMPAIGN_SUMMARY_ACTION
    assert outbox.calls[0][1]["report"]["campaign_id"] == "maintenance-test"
    assert dispatched.run_result is result
    assert dispatched.outbox_message_id == "out_test1234"


def test_worker_preserves_halted_exit_code_in_durable_summary(monkeypatch):
    result = _run_result(state="HALTED", exit_code=2)
    monkeypatch.setattr(worker, "run_maintenance_campaign_once", lambda *args, **kwargs: result)
    outbox = _Outbox()

    dispatched = worker.run_maintenance_campaign_worker_once(None, None, outbox)

    assert dispatched.run_result.exit_code == 2
    assert outbox.calls[0][1]["exit_code"] == 2
    assert outbox.calls[0][1]["report"]["state"] == "HALTED"


def test_outbox_failure_is_surfaced_without_retrying_campaign_or_enqueue(monkeypatch):
    result = _run_result()
    campaign_calls = 0

    def fake_run(*args, **kwargs):
        nonlocal campaign_calls
        campaign_calls += 1
        return result

    monkeypatch.setattr(worker, "run_maintenance_campaign_once", fake_run)
    outbox = _Outbox(fail=True)

    with pytest.raises(RuntimeError, match="outbox unavailable"):
        worker.run_maintenance_campaign_worker_once(None, None, outbox)

    assert campaign_calls == 1
    assert len(outbox.calls) == 1
