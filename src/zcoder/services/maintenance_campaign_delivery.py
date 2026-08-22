"""Bounded downstream delivery adapter for maintenance campaign summaries.

Upgrade-36 persists one secret-free maintenance campaign summary in the durable
outbox. This module consumes one such outbox message at a time and deliberately
does not poll, schedule, retry, or back off. Those policies remain external so
the Upgrade-20/24 execution and boundedness contracts stay authoritative.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from zcoder.services.maintenance_campaign_worker import (
    MAINTENANCE_CAMPAIGN_SUMMARY_ACTION,
    MAINTENANCE_CAMPAIGN_SUMMARY_SCHEMA_VERSION,
)


class MaintenanceCampaignDeliveryError(ValueError):
    """Raised when a durable summary cannot be safely delivered."""


@dataclass(frozen=True)
class MaintenanceCampaignDeliveryResult:
    """Result of one bounded delivery attempt."""

    idempotency_key: str
    delivered: bool


MaintenanceCampaignSummarySink = Callable[[str, dict[str, Any]], None]


def _validated_summary_payload(action: str, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if action != MAINTENANCE_CAMPAIGN_SUMMARY_ACTION:
        raise MaintenanceCampaignDeliveryError(f"unsupported outbox action: {action}")

    if payload.get("schema_version") != MAINTENANCE_CAMPAIGN_SUMMARY_SCHEMA_VERSION:
        raise MaintenanceCampaignDeliveryError("unsupported maintenance campaign summary schema")

    idempotency_key = payload.get("idempotency_key")
    if not isinstance(idempotency_key, str) or not idempotency_key.startswith("maintenance-campaign:"):
        raise MaintenanceCampaignDeliveryError("invalid maintenance campaign idempotency key")

    report = payload.get("report")
    if not isinstance(report, dict):
        raise MaintenanceCampaignDeliveryError("maintenance campaign summary report must be an object")

    campaign_id = report.get("campaign_id")
    if not isinstance(campaign_id, str) or idempotency_key != f"maintenance-campaign:{campaign_id}":
        raise MaintenanceCampaignDeliveryError("maintenance campaign summary identity mismatch")

    exit_code = payload.get("exit_code")
    if not isinstance(exit_code, int) or isinstance(exit_code, bool):
        raise MaintenanceCampaignDeliveryError("maintenance campaign exit_code must be an integer")

    return idempotency_key, payload


def deliver_maintenance_campaign_summary_once(
    action: str,
    payload: dict[str, Any],
    sink: MaintenanceCampaignSummarySink,
) -> MaintenanceCampaignDeliveryResult:
    """Validate and deliver exactly one durable summary.

    The downstream sink receives the deterministic Upgrade-36 idempotency key
    as a separate argument so it can enforce its own durable exactly-once or
    replay-safe semantics. A sink exception is intentionally surfaced; this
    adapter never retries or marks success on its own.
    """

    idempotency_key, validated_payload = _validated_summary_payload(action, payload)
    sink(idempotency_key, validated_payload)
    return MaintenanceCampaignDeliveryResult(idempotency_key=idempotency_key, delivered=True)
