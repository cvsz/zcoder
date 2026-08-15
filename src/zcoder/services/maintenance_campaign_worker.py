"""One-shot worker adapter for durable maintenance campaign summaries.

This module intentionally does not schedule or retry campaigns. Recurrence and
retry policy remain external; one invocation runs at most one Upgrade-34/35
maintenance campaign and performs at most one durable outbox enqueue.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from zcoder.services.maintenance_campaign import (
    MaintenanceCampaignRunResult,
    run_maintenance_campaign_once,
)
from zcoder.services.maintenance_observability import MaintenanceCampaignEventSink

MAINTENANCE_CAMPAIGN_SUMMARY_ACTION = "maintenance.campaign.summary"
MAINTENANCE_CAMPAIGN_SUMMARY_SCHEMA_VERSION = 1


class OutboxMessageLike(Protocol):
    id: str


class MaintenanceCampaignOutbox(Protocol):
    """Minimal existing control-plane outbox boundary used by the adapter."""

    def enqueue_outbox(self, action: str, payload: dict[str, Any]) -> OutboxMessageLike: ...


@dataclass(frozen=True)
class MaintenanceCampaignDispatchResult:
    """One bounded campaign result plus its durable outbox receipt."""

    run_result: MaintenanceCampaignRunResult
    outbox_message_id: str


def maintenance_campaign_summary_payload(run_result: MaintenanceCampaignRunResult) -> dict[str, Any]:
    """Build the versioned, secret-free durable summary payload."""

    report = run_result.report
    return {
        "schema_version": MAINTENANCE_CAMPAIGN_SUMMARY_SCHEMA_VERSION,
        "idempotency_key": f"maintenance-campaign:{report.campaign_id}",
        "exit_code": run_result.exit_code,
        "report": report.to_dict(),
    }


def enqueue_maintenance_campaign_summary(
    outbox: MaintenanceCampaignOutbox,
    run_result: MaintenanceCampaignRunResult,
) -> str:
    """Persist exactly one summary message; delivery/retry stays external."""

    message = outbox.enqueue_outbox(
        MAINTENANCE_CAMPAIGN_SUMMARY_ACTION,
        maintenance_campaign_summary_payload(run_result),
    )
    return message.id


def run_maintenance_campaign_worker_once(
    pipeline: Any,
    intelligence: Any,
    outbox: MaintenanceCampaignOutbox,
    event_sink: MaintenanceCampaignEventSink | None = None,
) -> MaintenanceCampaignDispatchResult:
    """Run one bounded campaign and enqueue one durable summary.

    There is deliberately no internal loop and no automatic outbox retry. If
    the durable enqueue fails, the exception is surfaced to the external
    worker/scheduler while the engineering result remains owned by Upgrade-20
    and Upgrade-24 state/ledger semantics.
    """

    run_result = run_maintenance_campaign_once(
        pipeline,
        intelligence,
        event_sink=event_sink,
    )
    message_id = enqueue_maintenance_campaign_summary(outbox, run_result)
    return MaintenanceCampaignDispatchResult(
        run_result=run_result,
        outbox_message_id=message_id,
    )
