"""Unit tests for Phase 4: Session Event Log.

Covers Prompt 7.4:
- SESSION_FORMAT_VERSION = 4
- EventType enum
- SessionEventStore with SQLite persistence
- append / get_events / snapshot_events
- ignorable event types
"""

from __future__ import annotations

import tempfile

from zcoder.agent.orchestration.session_log import (
    SESSION_FORMAT_VERSION,
    EventType,
    SessionEvent,
    SessionEventStore,
)


def test_session_format_version_is_4():
    assert SESSION_FORMAT_VERSION == 4


def test_event_type_enum_has_required_members():
    assert EventType.TURN_START == "turn/start"
    assert EventType.TURN_END == "turn/end"
    assert EventType.ASSISTANT_MESSAGE == "assistant/message"
    assert EventType.TOOL_CALL == "tool/call"
    assert EventType.TOOL_RESULT == "tool/result"
    assert EventType.REQUEST_HEADER == "request/header"


def test_ignorable_event_types():
    assert EventType.REQUEST_HEADER in EventType.__members__.values()
    assert EventType.REQUEST_CONTEXT in EventType.__members__.values()


def test_session_event_to_dict_and_from_dict():
    event = SessionEvent(
        event_type=EventType.USER_MESSAGE,
        session_id="s1",
        payload={"content": "hello"},
        ignorable=False,
    )
    d = event.to_dict()
    assert d["event_type"] == "user/message"
    assert d["session_id"] == "s1"
    assert d["payload"] == {"content": "hello"}
    assert d["ignorable"] is False

    restored = SessionEvent.from_dict(d)
    assert restored == event


def test_append_and_get_events(tmp_path):
    db = tmp_path / "sessions.db"
    store = SessionEventStore(db_path=db)

    store.append(SessionEvent(event_type=EventType.TURN_START, session_id="s1"))
    store.append(SessionEvent(event_type=EventType.USER_MESSAGE, session_id="s1", payload={"content": "hi"}))
    store.append(
        SessionEvent(event_type=EventType.ASSISTANT_MESSAGE, session_id="s1", payload={"content": "hello"})
    )

    events = store.get_events("s1")
    assert len(events) == 3
    assert events[0].event_type == EventType.TURN_START
    assert events[1].event_type == EventType.USER_MESSAGE
    assert events[2].event_type == EventType.ASSISTANT_MESSAGE
    assert events[1].payload["content"] == "hi"


def test_get_events_excludes_ignorable():
    db = tempfile.mktemp(suffix=".db")
    store = SessionEventStore(db_path=db)

    store.append(SessionEvent(event_type=EventType.TURN_START, session_id="s1"))
    store.append(
        SessionEvent(
            event_type=EventType.REQUEST_HEADER,
            session_id="s1",
            payload={"headers": {}},
            ignorable=True,
        )
    )
    store.append(SessionEvent(event_type=EventType.TURN_END, session_id="s1"))

    all_events = store.get_events("s1", include_ignorable=True)
    assert len(all_events) == 3

    filtered = store.get_events("s1", include_ignorable=False)
    assert len(filtered) == 2
    assert all(not e.ignorable for e in filtered)


def test_snapshot_events():
    db = tempfile.mktemp(suffix=".db")
    store = SessionEventStore(db_path=db)

    store.append(SessionEvent(event_type=EventType.TURN_START, session_id="snap1"))
    store.append(
        SessionEvent(event_type=EventType.USER_MESSAGE, session_id="snap1", payload={"content": "hello"})
    )

    snap = store.snapshot_events("snap1")
    assert snap["session_format_version"] == 4
    assert snap["session_id"] == "snap1"
    assert snap["event_count"] == 2
    assert snap["first_timestamp"] == snap["events"][0]["timestamp"]
    assert snap["last_timestamp"] == snap["events"][-1]["timestamp"]
    assert snap["events"][0]["event_type"] == "turn/start"


def test_list_sessions():
    db = tempfile.mktemp(suffix=".db")
    store = SessionEventStore(db_path=db)

    store.append(SessionEvent(event_type=EventType.TURN_START, session_id="alpha"))
    store.append(SessionEvent(event_type=EventType.TURN_START, session_id="beta"))
    store.append(SessionEvent(event_type=EventType.TURN_START, session_id="alpha"))

    sessions = store.list_sessions()
    assert "alpha" in sessions
    assert "beta" in sessions
    assert len(sessions) == 2
