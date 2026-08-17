"""Secret-free lifecycle events and observability boundary for maintenance campaigns."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Protocol


class MaintenanceCampaignEventType(str, Enum):
    """Finite lifecycle events emitted by one bounded maintenance campaign."""

    STARTED = "campaign.started"
    RECOMMENDATIONS_DISCOVERED = "campaign.recommendations_discovered"
    COMPLETED = "campaign.completed"
    HALTED = "campaign.halted"


@dataclass(frozen=True)
class MaintenanceCampaignEvent:
    """Bounded, secret-free event suitable for logs, traces, or scheduler adapters."""

    event_type: MaintenanceCampaignEventType
    campaign_id: str
    timestamp: float
    state: str = ""
    recommendations_discovered: int = 0
    work_seeded: int = 0
    iterations: int = 0
    completed_count: int = 0
    blocked_count: int = 0
    pending_count: int = 0
    halt_reason: str = ""
    duration_seconds: float = 0.0
    observer_error_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["event_type"] = self.event_type.value
        return payload


class MaintenanceCampaignEventSink(Protocol):
    """Observability boundary for one finite campaign lifecycle event."""

    def emit(self, event: MaintenanceCampaignEvent) -> None: ...
