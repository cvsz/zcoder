"""
zcoder.session.logger — Durable session event store.

Provides SQLite-backed persistence for session events. Events are appended
immutably; the store supports reading all events for a session and producing
a snapshot (merged view) of a session's events.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from zcoder.session.event import (
    IGNORABLE_EVENT_TYPES,
    EventType,
    SessionEvent,
    SessionId,
    brandEventId,
)


class SessionEventStore:
    """SQLite-backed session event store.

    Events are appended immutably; the store supports reading all events for a
    session and producing a snapshot (merged view) of a session's events.

    @param db_path - path to the SQLite database file. Defaults to
        ``data/session_events.db``.
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
                    event_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    source_event_seqs TEXT,
                    ignorable INTEGER NOT NULL DEFAULT 0,
                    surface_op TEXT,
                    seq INTEGER NOT NULL
                )
                """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_session_events_session_id "
                "ON session_events(session_id, seq)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_session_events_event_id " "ON session_events(event_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_session_events_type " "ON session_events(event_type)"
            )

    def append(self, event: SessionEvent) -> int:
        """Append one event to the store. Returns the database row id.

        @param event - the SessionEvent to persist
        @returns the row id of the inserted row
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 FROM session_events WHERE session_id = ?",
                (str(event.session_id),),
            )
            seq = row.fetchone()[0]
            conn.execute(
                """
                INSERT INTO session_events
                    (session_id, event_id, event_type, timestamp, payload,
                     source_event_seqs, ignorable, surface_op, seq)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(event.session_id),
                    str(event.event_id),
                    event.event_type.value,
                    event.timestamp,
                    json.dumps(event.payload, ensure_ascii=False),
                    json.dumps(event.source_event_seqs) if event.source_event_seqs else None,
                    1 if event.ignorable else 0,
                    event.surface_op,
                    seq,
                ),
            )
            return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    def get_events(self, session_id: str | SessionId, include_ignorable: bool = True) -> list[SessionEvent]:
        """Return all events for *session_id* ordered by sequence.

        @param session_id - session id (branded or raw string)
        @param include_ignorable - if False, events tagged ``ignorable = True``
            are excluded, matching forward-compatible reader behaviour
        @returns list of SessionEvent objects ordered by sequence
        """
        sid = str(session_id)
        with self._connect() as conn:
            if include_ignorable:
                rows = conn.execute(
                    """
                    SELECT session_id, event_id, event_type, timestamp, payload,
                           source_event_seqs, ignorable, surface_op
                    FROM session_events WHERE session_id = ? ORDER BY seq
                    """,
                    (sid,),
                )
            else:
                rows = conn.execute(
                    """
                    SELECT session_id, event_id, event_type, timestamp, payload,
                           source_event_seqs, ignorable, surface_op
                    FROM session_events WHERE session_id = ? AND ignorable = 0
                    ORDER BY seq
                    """,
                    (sid,),
                )
            return [
                SessionEvent(
                    event_type=EventType(row["event_type"]),
                    session_id=row["session_id"],
                    event_id=row["event_id"],
                    timestamp=row["timestamp"],
                    payload=json.loads(row["payload"]),
                    source_event_seqs=(
                        json.loads(row["source_event_seqs"]) if row["source_event_seqs"] else None
                    ),
                    ignorable=bool(row["ignorable"]),
                    surface_op=row["surface_op"],
                )
                for row in rows
            ]

    def append_event(
        self,
        session_id: str | SessionId,
        event_type: EventType,
        payload: dict[str, Any] | None = None,
        *,
        source_event_seqs: list[int] | None = None,
        ignorable: bool = False,
        surface_op: str | None = None,
    ) -> SessionEvent:
        """Create and append one event in a single call.

        @param session_id - session id (branded or raw string)
        @param event_type - type of event
        @param payload - optional payload data
        @returns the created and persisted SessionEvent
        """
        sid = str(session_id)
        event = SessionEvent(
            event_type=event_type,
            session_id=sid,
            event_id=brandEventId(f"{event_type.value}:{sid}"),
            payload=payload or {},
            source_event_seqs=source_event_seqs,
            ignorable=ignorable,
            surface_op=surface_op,
        )
        self.append(event)
        return event

    def snapshot_events(self, session_id: str | SessionId) -> dict[str, Any]:
        """Return a merged snapshot view of all events for *session_id*.

        @param session_id - session id (branded or raw string)
        @returns dict with version, session_id, event count, first/last
            timestamps, and ordered non-ignorable events
        """
        events = self.get_events(session_id, include_ignorable=False)
        first_ts = events[0].timestamp if events else ""
        last_ts = events[-1].timestamp if events else ""
        return {
            "session_format_version": 4,
            "session_id": str(session_id),
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

    def event_count(self, session_id: str | SessionId) -> int:
        """Return the number of events for *session_id* (non-ignorable only)."""
        sid = str(session_id)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM session_events WHERE session_id = ? AND ignorable = 0",
                (sid,),
            )
            return row.fetchone()[0]


__all__ = [
    "SessionEventStore",
    "IGNORABLE_EVENT_TYPES",
]
