"""Tests for zcoder.session - session event log infrastructure."""

from zcoder.session.event import (
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
from zcoder.session.replay import SessionReplay


class TestBrandedIds:
    """Tests for branded ID types."""

    def test_brand_session_id(self):
        sid = brandSessionId("session-abc")
        assert isinstance(sid, str)
        assert sid == "session-abc"

    def test_brand_event_id(self):
        eid = brandEventId("event-123")
        assert isinstance(eid, str)
        assert eid == "event-123"

    def test_brand_tool_call_id(self):
        tcid = brandToolCallId("tool-456")
        assert isinstance(tcid, str)
        assert tcid == "tool-456"

    def test_session_id_factory(self):
        sid = session_id("s-1")
        assert isinstance(sid, str)
        assert sid == "s-1"

    def test_event_id_factory(self):
        eid = event_id("e-1")
        assert isinstance(eid, str)
        assert eid == "e-1"

    def test_tool_call_id_factory(self):
        tcid = tool_call_id("tc-1")
        assert isinstance(tcid, str)
        assert tcid == "tc-1"

    def test_different_brands_are_different_types(self):
        sid = brandSessionId("same-value")
        eid = brandEventId("same-value")
        assert sid == eid  # Same string value at runtime
        # Both are just strings at runtime; branding is a static type construct


class TestSessionEvent:
    """Tests for SessionEvent dataclass."""

    def test_create_minimal(self):
        event = SessionEvent(
            event_type=EventType.USER_MESSAGE,
            session_id=brandSessionId("s1"),
            event_id=brandEventId("e1"),
        )
        assert event.event_type == EventType.USER_MESSAGE
        assert str(event.session_id) == "s1"
        assert str(event.event_id) == "e1"
        assert event.timestamp != ""
        assert event.payload == {}
        assert event.ignorable is False
        assert event.surface_op is None

    def test_create_full(self):
        event = SessionEvent(
            event_type=EventType.TOOL_CALL,
            session_id=brandSessionId("s2"),
            event_id=brandEventId("e2"),
            payload={"toolName": "read", "arguments": {"path": "/tmp/test"}},
            ignorable=False,
            surface_op="append",
        )
        assert event.event_type == EventType.TOOL_CALL
        assert event.payload == {"toolName": "read", "arguments": {"path": "/tmp/test"}}
        assert event.surface_op == "append"

    def test_to_dict_and_from_dict(self):
        original = SessionEvent(
            event_type=EventType.TURN_START,
            session_id=brandSessionId("s3"),
            event_id=brandEventId("e3"),
            payload={"turn": 1},
            ignorable=False,
        )
        d = original.to_dict()
        assert d["event_type"] == "turn/start"
        assert d["session_id"] == "s3"
        assert d["event_id"] == "e3"
        assert d["payload"] == {"turn": 1}
        assert d["ignorable"] is False

        restored = SessionEvent.from_dict(d)
        assert restored.event_type == original.event_type
        assert str(restored.session_id) == str(original.session_id)
        assert str(restored.event_id) == str(original.event_id)
        assert restored.payload == original.payload
        assert restored.ignorable == original.ignorable


class TestSessionEventStore:
    """Tests for SessionEventStore."""

    def test_append_and_get_events(self, tmp_path):
        store = SessionEventStore(db_path=tmp_path / "test.db")
        event = SessionEvent(
            event_type=EventType.USER_MESSAGE,
            session_id=brandSessionId("s1"),
            event_id=brandEventId("e1"),
            payload={"content": "hello"},
        )
        row_id = store.append(event)
        assert row_id == 1

        events = store.get_events("s1")
        assert len(events) == 1
        assert events[0].event_type == EventType.USER_MESSAGE
        assert str(events[0].session_id) == "s1"
        assert events[0].payload == {"content": "hello"}

    def test_append_multiple_events_ordered(self, tmp_path):
        store = SessionEventStore(db_path=tmp_path / "test2.db")
        store.append(
            SessionEvent(
                event_type=EventType.TURN_START,
                session_id=brandSessionId("s2"),
                event_id=brandEventId("e1"),
                payload={"turn": 1},
            )
        )
        store.append(
            SessionEvent(
                event_type=EventType.USER_MESSAGE,
                session_id=brandSessionId("s2"),
                event_id=brandEventId("e2"),
                payload={"content": "hello"},
            )
        )
        store.append(
            SessionEvent(
                event_type=EventType.TURN_END,
                session_id=brandSessionId("s2"),
                event_id=brandEventId("e3"),
                payload={"turn": 1, "reason": "complete"},
            )
        )

        events = store.get_events("s2")
        assert len(events) == 3
        assert events[0].event_type == EventType.TURN_START
        assert events[1].event_type == EventType.USER_MESSAGE
        assert events[2].event_type == EventType.TURN_END

    def test_ignorable_events_filtered(self, tmp_path):
        store = SessionEventStore(db_path=tmp_path / "test3.db")
        store.append(
            SessionEvent(
                event_type=EventType.REQUEST_HEADER,
                session_id=brandSessionId("s3"),
                event_id=brandEventId("e1"),
                payload={"header": {}},
                ignorable=True,
            )
        )
        store.append(
            SessionEvent(
                event_type=EventType.USER_MESSAGE,
                session_id=brandSessionId("s3"),
                event_id=brandEventId("e2"),
                payload={"content": "hello"},
                ignorable=False,
            )
        )

        all_events = store.get_events("s3", include_ignorable=True)
        assert len(all_events) == 2

        non_ignorable = store.get_events("s3", include_ignorable=False)
        assert len(non_ignorable) == 1
        assert non_ignorable[0].event_type == EventType.USER_MESSAGE

    def test_list_sessions(self, tmp_path):
        store = SessionEventStore(db_path=tmp_path / "test4.db")
        store.append(
            SessionEvent(
                event_type=EventType.TURN_START,
                session_id=brandSessionId("s1"),
                event_id=brandEventId("e1"),
                payload={"turn": 1},
            )
        )
        store.append(
            SessionEvent(
                event_type=EventType.TURN_START,
                session_id=brandSessionId("s2"),
                event_id=brandEventId("e2"),
                payload={"turn": 1},
            )
        )

        sessions = store.list_sessions()
        assert "s1" in sessions
        assert "s2" in sessions

    def test_snapshot_events(self, tmp_path):
        store = SessionEventStore(db_path=tmp_path / "test5.db")
        store.append(
            SessionEvent(
                event_type=EventType.TURN_START,
                session_id=brandSessionId("s5"),
                event_id=brandEventId("e1"),
                payload={"turn": 1},
            )
        )
        store.append(
            SessionEvent(
                event_type=EventType.USER_MESSAGE,
                session_id=brandSessionId("s5"),
                event_id=brandEventId("e2"),
                payload={"content": "hello"},
                ignorable=True,
            )
        )
        store.append(
            SessionEvent(
                event_type=EventType.TURN_END,
                session_id=brandSessionId("s5"),
                event_id=brandEventId("e3"),
                payload={"turn": 1, "reason": "done"},
            )
        )

        snapshot = store.snapshot_events("s5")
        assert snapshot["session_format_version"] == 4
        assert snapshot["session_id"] == "s5"
        assert snapshot["event_count"] == 2  # Ignorable excluded
        assert len(snapshot["events"]) == 2


class TestSessionReplay:
    """Tests for SessionReplay."""

    def test_replay_empty_session(self, tmp_path):
        store = SessionEventStore(db_path=tmp_path / "replay_test.db")
        replayer = SessionReplay(store)
        result = replayer.replay("empty-session")
        assert result.session_id == "empty-session"
        assert result.events == []
        assert result.model_requests == []
        assert result.tool_results == []

    def test_replay_with_messages(self, tmp_path):
        store = SessionEventStore(db_path=tmp_path / "replay_test2.db")
        store.append(
            SessionEvent(
                event_type=EventType.SYSTEM_MESSAGE,
                session_id=brandSessionId("s-replay"),
                event_id=brandEventId("e1"),
                payload={"content": "You are a helpful assistant"},
            )
        )
        store.append(
            SessionEvent(
                event_type=EventType.USER_MESSAGE,
                session_id=brandSessionId("s-replay"),
                event_id=brandEventId("e2"),
                payload={"content": "Hello"},
            )
        )
        store.append(
            SessionEvent(
                event_type=EventType.ASSISTANT_MESSAGE,
                session_id=brandSessionId("s-replay"),
                event_id=brandEventId("e3"),
                payload={"content": "Hi there"},
            )
        )

        replayer = SessionReplay(store)
        result = replayer.replay("s-replay")

        assert len(result.model_requests) == 1
        mr = result.model_requests[0]
        assert mr.system == "You are a helpful assistant"
        assert len(mr.messages) == 3  # system + user + assistant
        assert mr.messages[0] == {"role": "system", "content": "You are a helpful assistant"}
        assert mr.messages[1] == {"role": "user", "content": "Hello"}
        assert mr.messages[2] == {"role": "assistant", "content": "Hi there"}

    def test_replay_with_tool_calls(self, tmp_path):
        store = SessionEventStore(db_path=tmp_path / "replay_test3.db")
        store.append(
            SessionEvent(
                event_type=EventType.USER_MESSAGE,
                session_id=brandSessionId("s-replay2"),
                event_id=brandEventId("e1"),
                payload={"content": "Read file"},
            )
        )
        store.append(
            SessionEvent(
                event_type=EventType.TOOL_CALL,
                session_id=brandSessionId("s-replay2"),
                event_id=brandEventId("e2"),
                payload={"toolName": "read", "arguments": {"path": "/tmp/test.txt"}},
            )
        )
        store.append(
            SessionEvent(
                event_type=EventType.TOOL_RESULT,
                session_id=brandSessionId("s-replay2"),
                event_id=brandEventId("e3"),
                payload={"toolName": "read", "result": "file contents", "tool_call_id": "tc-1"},
            )
        )
        store.append(
            SessionEvent(
                event_type=EventType.ASSISTANT_MESSAGE,
                session_id=brandSessionId("s-replay2"),
                event_id=brandEventId("e4"),
                payload={"content": "Here is the file content"},
            )
        )

        replayer = SessionReplay(store)
        result = replayer.replay("s-replay2")

        assert len(result.model_requests) == 1
        mr = result.model_requests[0]
        # Should have user + tool_call + tool_result + assistant messages
        assert len(mr.messages) == 4
        assert mr.tool_calls == [{"name": "read", "arguments": {"path": "/tmp/test.txt"}, "event_id": "e2"}]
        assert len(result.tool_results) == 1
        assert result.tool_results[0]["tool_name"] == "read"
