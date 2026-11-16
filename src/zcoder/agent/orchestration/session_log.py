"""
session_log.py — Session Event Log (Phase 4 of Big Upgrade).

Durable, event-sourced session logging. Everything model-visible (input sent
to a model) must be reproducible from the session log — model-visible ⟺ logged.

Implements:
- SESSION_FORMAT_VERSION = 4
- EventType enum of session event types
- SessionEventStore with SQLite persistence (append, get_events, snapshot_events)
- Optional events tagged ``ignorable = True`` for forward-compatible readers.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

SESSION_FORMAT_VERSION = 4


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
IGNORABLE_EVENT_TYPES = {
    EventType.REQUEST_HEADER,
    EventType.REQUEST_CONTEXT,
}


@dataclass(frozen=True)
class SessionEvent:
    """A single session event."""

    event_type: EventType
    session_id: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    payload: dict[str, Any] = field(default_factory=dict)
    ignorable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "payload": self.payload,
            "ignorable": self.ignorable,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionEvent:
        return cls(
            event_type=EventType(data["event_type"]),
            session_id=data["session_id"],
            timestamp=data.get("timestamp", ""),
            payload=data.get("payload", {}),
            ignorable=data.get("ignorable", False),
        )


class SessionEventStore:
    """SQLite-backed session event store.

    Events are appended immutably; the store supports reading all events for a
    session and producing a snapshot (merged view) of a session's events.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            db_path = Path("data") / "session_events.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS session_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    ignorable INTEGER NOT NULL DEFAULT 0,
                    seq INTEGER NOT NULL
                )
                """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_session_events_session_id "
                "ON session_events(session_id, seq)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_session_events_type " "ON session_events(event_type)"
            )

    def append(self, event: SessionEvent) -> int:
        """Append one event to the store. Returns the row id."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 FROM session_events WHERE session_id = ?",
                (event.session_id,),
            )
            seq = row.fetchone()[0]
            conn.execute(
                "INSERT INTO session_events "
                "(session_id, event_type, timestamp, payload, ignorable, seq) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    event.session_id,
                    event.event_type.value,
                    event.timestamp,
                    json.dumps(event.payload, ensure_ascii=False),
                    1 if event.ignorable else 0,
                    seq,
                ),
            )
            return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    def get_events(self, session_id: str, include_ignorable: bool = True) -> list[SessionEvent]:
        """Return all events for *session_id* ordered by sequence.

        If ``include_ignorable`` is False, events tagged ``ignorable = True``
        are excluded — matching forward-compatible reader behaviour.
        """
        with self._connect() as conn:
            if include_ignorable:
                rows = conn.execute(
                    "SELECT event_type, session_id, timestamp, payload, ignorable "
                    "FROM session_events WHERE session_id = ? ORDER BY seq",
                    (session_id,),
                )
            else:
                rows = conn.execute(
                    "SELECT event_type, session_id, timestamp, payload, ignorable "
                    "FROM session_events WHERE session_id = ? AND ignorable = 0 ORDER BY seq",
                    (session_id,),
                )
            return [
                SessionEvent(
                    event_type=EventType(row["event_type"]),
                    session_id=row["session_id"],
                    timestamp=row["timestamp"],
                    payload=json.loads(row["payload"]),
                    ignorable=bool(row["ignorable"]),
                )
                for row in rows
            ]

    def snapshot_events(self, session_id: str) -> dict[str, Any]:
        """Return a merged snapshot view of all events for *session_id*.

        The snapshot includes metadata (version, session_id, event count,
        first/last timestamps) plus the ordered list of non-ignorable events.
        """
        events = self.get_events(session_id, include_ignorable=False)
        first_ts = events[0].timestamp if events else ""
        last_ts = events[-1].timestamp if events else ""
        return {
            "session_format_version": SESSION_FORMAT_VERSION,
            "session_id": session_id,
            "event_count": len(events),
            "first_timestamp": first_ts,
            "last_timestamp": last_ts,
            "events": [e.to_dict() for e in events],
        }

    def list_sessions(self) -> list[str]:
        """Return all distinct session ids in the store."""
        with self._connect() as conn:
            rows = conn.execute("SELECT DISTINCT session_id FROM session_events ORDER BY session_id")
            return [row[0] for row in rows]
