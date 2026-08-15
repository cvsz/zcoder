from __future__ import annotations

import pytest

from zcoder.services.maintenance_campaign_delivery import (
    MaintenanceCampaignDeliveryError,
    deliver_maintenance_campaign_summary_once,
)
from zcoder.services.maintenance_campaign_worker import MAINTENANCE_CAMPAIGN_SUMMARY_ACTION


def _payload() -> dict:
    return {
        "schema_version": 1,
        "idempotency_key": "maintenance-campaign:camp-123",
        "exit_code": 0,
        "report": {"campaign_id": "camp-123", "status": "completed"},
    }


def test_delivery_calls_sink_once_with_deterministic_idempotency_key():
    calls = []

    def sink(idempotency_key, payload):
        calls.append((idempotency_key, payload))

    result = deliver_maintenance_campaign_summary_once(MAINTENANCE_CAMPAIGN_SUMMARY_ACTION, _payload(), sink)

    assert result.delivered is True
    assert result.idempotency_key == "maintenance-campaign:camp-123"
    assert calls == [("maintenance-campaign:camp-123", _payload())]


def test_delivery_rejects_unknown_action_before_sink():
    calls = []

    with pytest.raises(MaintenanceCampaignDeliveryError, match="unsupported outbox action"):
        deliver_maintenance_campaign_summary_once(
            "github.create_pr",
            _payload(),
            lambda *args: calls.append(args),
        )

    assert calls == []


def test_delivery_rejects_schema_mismatch_before_sink():
    payload = _payload()
    payload["schema_version"] = 999
    calls = []

    with pytest.raises(
        MaintenanceCampaignDeliveryError,
        match="unsupported maintenance campaign summary schema",
    ):
        deliver_maintenance_campaign_summary_once(
            MAINTENANCE_CAMPAIGN_SUMMARY_ACTION,
            payload,
            lambda *args: calls.append(args),
        )

    assert calls == []


def test_delivery_rejects_identity_mismatch_before_sink():
    payload = _payload()
    payload["report"]["campaign_id"] = "camp-other"
    calls = []

    with pytest.raises(MaintenanceCampaignDeliveryError, match="identity mismatch"):
        deliver_maintenance_campaign_summary_once(
            MAINTENANCE_CAMPAIGN_SUMMARY_ACTION,
            payload,
            lambda *args: calls.append(args),
        )

    assert calls == []


def test_sink_failure_surfaces_without_internal_retry():
    calls = []

    def failing_sink(idempotency_key, payload):
        calls.append((idempotency_key, payload))
        raise RuntimeError("downstream unavailable")

    with pytest.raises(RuntimeError, match="downstream unavailable"):
        deliver_maintenance_campaign_summary_once(
            MAINTENANCE_CAMPAIGN_SUMMARY_ACTION,
            _payload(),
            failing_sink,
        )

    assert len(calls) == 1


def test_delivery_rejects_boolean_exit_code():
    payload = _payload()
    payload["exit_code"] = True

    with pytest.raises(MaintenanceCampaignDeliveryError, match="exit_code must be an integer"):
        deliver_maintenance_campaign_summary_once(
            MAINTENANCE_CAMPAIGN_SUMMARY_ACTION,
            payload,
            lambda *_: None,
        )
