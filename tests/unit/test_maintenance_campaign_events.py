"""Focused Upgrade-35 lifecycle-event and scheduler-contract coverage."""

import logging
from dataclasses import dataclass
from types import SimpleNamespace

from zcoder.services.maintenance_campaign import (
    MaintenanceCampaignService,
    run_maintenance_campaign_once,
)
from zcoder.services.maintenance_observability import MaintenanceCampaignEventType
from zcoder.services.upgrade_loop import LoopReport, LoopState


@dataclass
class Recommendation:
    id: str = "volatile-rec"
    repository: str = "cvsz/zcoder"
    type: str = "PATCH_DEPENDENCY"
    priority: int = 5
    risk: str = "low"
    reason: str = "Dependency outdated: demo"


class Intelligence:
    def __init__(self, recommendations=None):
        self.recommendations = [Recommendation()] if recommendations is None else list(recommendations)

    def generate_recommendations(self):
        return list(self.recommendations)


class Pipeline:
    def __init__(self, state=LoopState.COMPLETED):
        self.ledger = SimpleNamespace(terminal_counts=lambda: {"SUCCEEDED": 1, "BLOCKED": 0})
        self.state = state
        self.seed = None

    def run(self, seed):
        self.seed = list(seed)
        completed = ("done",) if self.state == LoopState.COMPLETED else ()
        blocked = ("blocked",) if self.state != LoopState.COMPLETED else ()
        return LoopReport(
            state=self.state,
            iterations=1,
            completed_item_ids=completed,
            blocked_item_ids=blocked,
            pending_item_ids=(),
            records=(),
            halt_reason="blocked_work_remaining" if blocked else "",
        )


class RecordingSink:
    def __init__(self):
        self.events = []

    def emit(self, event):
        self.events.append(event)


class FailingSink:
    def __init__(self):
        self.calls = 0

    def emit(self, event):
        self.calls += 1
        raise RuntimeError("telemetry unavailable")


def test_completed_campaign_emits_finite_ordered_lifecycle_events():
    sink = RecordingSink()
    report = MaintenanceCampaignService(Pipeline(), Intelligence(), event_sink=sink).run()

    assert [event.event_type for event in sink.events] == [
        MaintenanceCampaignEventType.STARTED,
        MaintenanceCampaignEventType.RECOMMENDATIONS_DISCOVERED,
        MaintenanceCampaignEventType.COMPLETED,
    ]
    assert len({event.campaign_id for event in sink.events}) == 1
    discovered = sink.events[1]
    final = sink.events[2]
    assert discovered.recommendations_discovered == 1
    assert discovered.work_seeded == 1
    assert final.state == LoopState.COMPLETED.value
    assert final.completed_count == 1
    assert final.duration_seconds >= 0
    assert report.observer_error_count == 0


def test_halted_campaign_emits_halted_event_and_scheduler_exit_code_two():
    sink = RecordingSink()
    result = run_maintenance_campaign_once(
        Pipeline(state=LoopState.HALTED),
        Intelligence(),
        event_sink=sink,
    )

    assert result.exit_code == 2
    assert result.report.state == LoopState.HALTED.value
    assert sink.events[-1].event_type == MaintenanceCampaignEventType.HALTED
    assert sink.events[-1].blocked_count == 1
    assert sink.events[-1].halt_reason == "blocked_work_remaining"


def test_completed_campaign_scheduler_contract_returns_zero():
    result = run_maintenance_campaign_once(Pipeline(), Intelligence())

    assert result.exit_code == 0
    assert result.report.state == LoopState.COMPLETED.value


def test_observer_failure_is_best_effort_and_counted_without_changing_engineering_result(caplog):
    sink = FailingSink()
    logger = logging.getLogger("zcoder.services.maintenance_campaign")

    # The production logging setup deliberately disables propagation on the
    # zcoder logger. Attach pytest's capture handler to the exact child logger
    # so this regression assertion is stable across Python logging versions
    # without changing production logging or security behavior.
    logger.addHandler(caplog.handler)
    try:
        report = MaintenanceCampaignService(Pipeline(), Intelligence(), event_sink=sink).run()
    finally:
        logger.removeHandler(caplog.handler)

    assert report.state == LoopState.COMPLETED.value
    assert report.completed_count == 1
    assert report.observer_error_count == 3
    assert sink.calls == 3
    assert "telemetry unavailable" not in caplog.text
    assert "maintenance campaign observer failed" in caplog.text


def test_empty_campaign_events_are_still_finite_and_resume_pipeline():
    sink = RecordingSink()
    pipeline = Pipeline()

    report = MaintenanceCampaignService(pipeline, Intelligence([]), event_sink=sink).run()

    assert pipeline.seed == []
    assert report.recommendations_discovered == 0
    assert report.work_seeded == 0
    assert [event.event_type for event in sink.events] == [
        MaintenanceCampaignEventType.STARTED,
        MaintenanceCampaignEventType.RECOMMENDATIONS_DISCOVERED,
        MaintenanceCampaignEventType.COMPLETED,
    ]
