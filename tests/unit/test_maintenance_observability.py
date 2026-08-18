"""Unit coverage for Upgrade-35 maintenance campaign observability."""

from zcoder.infrastructure.observability.maintenance import OtelMaintenanceCampaignEventSink
from zcoder.infrastructure.observability.otel import ZCoderMetrics
from zcoder.services.maintenance_observability import (
    MaintenanceCampaignEvent,
    MaintenanceCampaignEventType,
)


def event(event_type, **overrides):
    values = {
        "event_type": event_type,
        "campaign_id": "maintenance-test",
        "timestamp": 100.0,
    }
    values.update(overrides)
    return MaintenanceCampaignEvent(**values)


def test_event_dict_is_bounded_and_secret_free():
    payload = event(
        MaintenanceCampaignEventType.COMPLETED,
        state="COMPLETED",
        recommendations_discovered=3,
        work_seeded=2,
        completed_count=2,
        duration_seconds=1.5,
    ).to_dict()

    assert payload["event_type"] == "campaign.completed"
    assert payload["campaign_id"] == "maintenance-test"
    assert "database_url" not in payload
    assert "evidence" not in payload
    assert "payload" not in payload
    assert "repository_snapshot" not in payload


def test_otel_sink_records_bounded_campaign_metrics():
    metrics = ZCoderMetrics()
    sink = OtelMaintenanceCampaignEventSink(metrics)

    sink.emit(event(MaintenanceCampaignEventType.STARTED))
    sink.emit(
        event(
            MaintenanceCampaignEventType.RECOMMENDATIONS_DISCOVERED,
            recommendations_discovered=4,
            work_seeded=3,
        )
    )
    sink.emit(
        event(
            MaintenanceCampaignEventType.COMPLETED,
            state="COMPLETED",
            completed_count=2,
            blocked_count=1,
            pending_count=0,
            duration_seconds=2.5,
            observer_error_count=1,
        )
    )

    assert metrics.maintenance_campaigns_total.get() == 1.0
    assert metrics.maintenance_campaigns_noncompleted_total.get() == 0.0
    assert metrics.maintenance_recommendations_total.get() == 4.0
    assert metrics.maintenance_work_seeded_total.get() == 3.0
    assert metrics.maintenance_completed_items_total.get() == 2.0
    assert metrics.maintenance_blocked_items_total.get() == 1.0
    assert metrics.maintenance_pending_items_total.get() == 0.0
    assert metrics.maintenance_observer_errors_total.get() == 1.0
    assert metrics.maintenance_campaign_duration_seconds.count() == 1
    assert metrics.maintenance_campaign_duration_seconds.sum() == 2.5


def test_halted_event_increments_noncompleted_metric():
    metrics = ZCoderMetrics()
    sink = OtelMaintenanceCampaignEventSink(metrics)

    sink.emit(
        event(
            MaintenanceCampaignEventType.HALTED,
            state="HALTED",
            blocked_count=1,
            pending_count=2,
            duration_seconds=0.25,
        )
    )

    assert metrics.maintenance_campaigns_noncompleted_total.get() == 1.0
    assert metrics.maintenance_blocked_items_total.get() == 1.0
    assert metrics.maintenance_pending_items_total.get() == 2.0


def test_prometheus_exposition_contains_maintenance_metrics():
    metrics = ZCoderMetrics()
    metrics.maintenance_campaigns_total.inc()
    metrics.maintenance_campaign_duration_seconds.observe(0.5)

    output = metrics.prometheus_exposition()

    assert "zcoder_maintenance_campaigns_total" in output
    assert "zcoder_maintenance_campaign_duration_seconds_count" in output
    assert "zcoder_maintenance_observer_errors_total" in output
