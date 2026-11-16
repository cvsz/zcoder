"""
zcoder.session.event — Session event types and branded IDs.

Provides branded opaque IDs for session, event, and tool call identifiers,
and the SessionEvent dataclass used throughout the session event log.

Branded strings make structurally identical values non-interchangeable at the
type level: a SessionId cannot be passed where a ToolCallId is expected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, TypeVar, cast

T = TypeVar("T")

BRAND: str = "__brand__"


def brandString(value: str) -> str:
    """Brand a raw string as a nominal type.

    Changes only the static type; performs no runtime validation. Validate
    domain grammar before calling when the owning type has one. Once branded,
    the id compares, logs, serializes to JSON, and crosses the wire as an
    ordinary string.
    """
    return value


# ── Session id brand ──────────────────────────────────────────────────────────

SessionId = Annotated[str, "SessionId"]


def brandSessionId(value: str) -> SessionId:
    """Brand a raw string as a SessionId."""
    return cast(SessionId, brandString(value))


def session_id(value: str) -> SessionId:
    """Create a branded SessionId from a raw string."""
    return brandSessionId(value)


# ── Event id brand ────────────────────────────────────────────────────────────

EventId = Annotated[str, "EventId"]


def brandEventId(value: str) -> EventId:
    """Brand a raw string as an EventId."""
    return cast(EventId, brandString(value))


def event_id(value: str) -> EventId:
    """Create a branded EventId from a raw string."""
    return brandEventId(value)


# ── ToolCall id brand ─────────────────────────────────────────────────────────

ToolCallId = Annotated[str, "ToolCallId"]


def brandToolCallId(value: str) -> ToolCallId:
    """Brand a raw string as a ToolCallId."""
    return cast(ToolCallId, brandString(value))


def tool_call_id(value: str) -> ToolCallId:
    """Create a branded ToolCallId from a raw string."""
    return brandToolCallId(value)


# ── Event type enum ───────────────────────────────────────────────────────────


class EventType(StrEnum):
    """Session event types.

    Events marked ``ignorable`` may be safely skipped by readers that do not
    recognise them, enabling forward-compatible schema evolution.
    """

    # Turn lifecycle
    TURN_START = "turn/start"
    TURN_END = "turn/end"

    # Step lifecycle
    STEP_START = "step/start"
    STEP_END = "step/end"

    # Messages
    USER_MESSAGE = "user/message"
    DEVELOPER_MESSAGE = "developer/message"
    SYSTEM_MESSAGE = "system/message"
    ASSISTANT_MESSAGE = "assistant/message"
    ASSISTANT_ATTEMPT = "assistant/attempt"

    # Tool calls
    TOOL_CALL = "tool/call"
    TOOL_RESULT = "tool/result"

    # Request metadata (optional / ignorable)
    REQUEST_HEADER = "request/header"
    REQUEST_CONTEXT = "request/context"

    # Session seed
    SESSION_END_SEED = "session/end-seed"


# Event types that optional readers may safely ignore.
IGNORABLE_EVENT_TYPES = frozenset(
    {
        EventType.REQUEST_HEADER,
        EventType.REQUEST_CONTEXT,
    }
)


SESSION_FORMAT_VERSION = 4


@dataclass(frozen=True)
class SessionEvent:
    """Durable session event appended to the log.

    Events are the source of truth for model-visible context. New event types
    added to this set require the envelope's ``ignorable`` marker so older
    readers do not misinterpret them.

    @param event_type - one of EventType or an ignorable extension
    @param session_id - branded session identifier
    @param event_id - branded event identifier (unique within the session)
    @param timestamp - ISO-8601 timestamp (defaults to now)
    @param payload - event-specific payload data
    @param source_event_seqs - sequence numbers of events this derives from
    @param ignorable - if True, older readers may safely skip this event
    @param surface_op - surface operation marker ('append' for committed appends)
    """

    event_type: EventType
    session_id: SessionId
    event_id: EventId
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    payload: dict[str, Any] = field(default_factory=dict)
    source_event_seqs: list[int] | None = None
    ignorable: bool = False
    surface_op: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-serializable dict."""
        return {
            "event_type": self.event_type.value,
            "session_id": str(self.session_id),
            "event_id": str(self.event_id),
            "timestamp": self.timestamp,
            "payload": self.payload,
            "source_event_seqs": self.source_event_seqs,
            "ignorable": self.ignorable,
            "surface_op": self.surface_op,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionEvent:
        """Build a SessionEvent from a persisted envelope."""
        return cls(
            event_type=EventType(data["event_type"]),
            session_id=data["session_id"],
            event_id=data["event_id"],
            timestamp=data.get("timestamp", ""),
            payload=data.get("payload", {}),
            source_event_seqs=data.get("source_event_seqs"),
            ignorable=data.get("ignorable", False),
            surface_op=data.get("surface_op"),
        )
