"""zcoder.session — Session event log infrastructure.

Provides durable, event-sourced session logging. Everything model-visible
(input sent to a model) must be reproducible from the session log —
model-visible ⟺ logged.
"""

from zcoder.session.event import (
    IGNORABLE_EVENT_TYPES,
    SESSION_FORMAT_VERSION,
    EventType,
    SessionEvent,
    brandEventId,
    brandSessionId,
    brandToolCallId,
    event_id,
    session_id,
    tool_call_id,
)
from zcoder.session.logger import SessionEventStore
from zcoder.session.replay import SessionReplay, replay_session

__all__ = [
    "EventType",
    "IGNORABLE_EVENT_TYPES",
    "SESSION_FORMAT_VERSION",
    "SessionEvent",
    "SessionEventStore",
    "SessionReplay",
    "brandEventId",
    "brandSessionId",
    "brandToolCallId",
    "event_id",
    "replay_session",
    "session_id",
    "tool_call_id",
]
