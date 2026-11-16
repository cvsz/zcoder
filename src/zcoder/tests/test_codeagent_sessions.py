"""Tests for zcoder.agent.codeagent.sessions - session management for codeagent."""

from __future__ import annotations

import pytest

from zcoder.agent.codeagent.sessions import (
    DEFAULT_MODEL_PRICING,
    SESSION_FORMAT_VERSION,
    CostBreakdown,
    SessionEvent,
    SessionInfo,
    SessionProjection,
    SessionStore,
    TokenUsage,
    ToolUsageStat,
    estimate_cost,
    log_cost_event,
    log_token_usage,
    log_tool_call,
    log_tool_result,
    new_session_id,
    session_event_to_dict,
)


class TestNewSessionId:
    """Tests for new_session_id() factory function."""

    def test_format(self):
        sid = new_session_id()
        parts = sid.split("-")
        assert len(parts) == 3
        date_part, time_part, hex_part = parts
        assert len(date_part) == 8
        assert len(time_part) == 6
        assert len(hex_part) == 6
        int(date_part)  # must be numeric
        int(time_part)  # must be numeric
        int(hex_part, 16)  # must be hex

    def test_unique(self):
        ids = {new_session_id() for _ in range(100)}
        assert len(ids) == 100


class TestSessionEvent:
    """Tests for SessionEvent dataclass."""

    def test_create_minimal(self):
        event = SessionEvent(kind="turn/start", data={"turn": 1})
        assert event.kind == "turn/start"
        assert event.data == {"turn": 1}
        assert event.source_event_seqs is None
        assert event.ignorable is False
        assert event.surface_op is None
        assert event.event_id == ""
        assert event.timestamp == 0.0

    def test_create_full(self):
        event = SessionEvent(
            kind="tool/call",
            data={"toolName": "read", "arguments": {"path": "/tmp/test"}},
            source_event_seqs=[1, 2],
            ignorable=True,
            surface_op="append",
            event_id="evt-abc123",
            timestamp=1234567890.0,
        )
        assert event.kind == "tool/call"
        assert event.data == {"toolName": "read", "arguments": {"path": "/tmp/test"}}
        assert event.source_event_seqs == [1, 2]
        assert event.ignorable is True
        assert event.surface_op == "append"
        assert event.event_id == "evt-abc123"
        assert event.timestamp == 1234567890.0


class TestSessionEventSerialization:
    """Tests for SessionEvent serialization round-trip."""

    def test_to_dict_and_from_dict(self):
        original = SessionEvent(
            kind="turn/start",
            data={"turn": 1},
            source_event_seqs=[1],
            ignorable=False,
            surface_op="append",
            event_id="evt-1",
            timestamp=1000.0,
        )
        d = session_event_to_dict(original)
        assert d["kind"] == "turn/start"
        assert d["data"] == {"turn": 1}
        assert d["sourceEventSeqs"] == [1]
        assert d["ignorable"] is False
        assert d["surfaceOp"] == "append"
        assert d["eventId"] == "evt-1"
        assert d["timestamp"] == 1000.0

    def test_from_dict_round_trip(self):
        original = SessionEvent(
            kind="user/message",
            data={"content": "hello"},
            event_id="evt-2",
            timestamp=2000.0,
        )
        d = session_event_to_dict(original)
        restored = SessionEvent(
            kind=d["kind"],
            data=d.get("data", {}),
            source_event_seqs=d.get("source_event_seqs"),
            ignorable=d.get("ignorable", False),
            surface_op=d.get("surface_op", d.get("surfaceOp")),
            event_id=str(d.get("event_id", d.get("eventId", ""))),
            timestamp=float(d.get("timestamp", 0.0)),
        )
        assert restored.kind == original.kind
        assert restored.data == original.data
        assert restored.event_id == original.event_id
        assert restored.timestamp == original.timestamp


class TestSessionStore:
    """Tests for SessionStore."""

    @pytest.fixture
    def store(self, tmp_path):
        return SessionStore(directory=tmp_path / "sessions")

    def test_save_and_load(self, store):
        session_id = "20260115-120000-abc123"
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        store.save(session_id, "/tmp/test", messages, usage={"prompt": 10, "completion": 5})

        doc = store.load(session_id)
        assert doc["id"] == session_id
        assert doc["cwd"] == "/tmp/test"
        assert doc["title"] == "Hello"
        assert len(doc["messages"]) == 2
        assert doc["usage"] == {"prompt": 10, "completion": 5}

    def test_load_missing_raises_keyerror(self, store):
        with pytest.raises(KeyError):
            store.load("20260115-120000-000000")

    def test_load_corrupt_returns_empty(self, store):
        session_id = "20260115-120000-000001"
        path = store._path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not valid json", encoding="utf-8")
        assert store.load(session_id) == {}

    def test_list_sessions(self, store):
        # Save two sessions
        store.save("20260115-120000-aaa111", "/tmp/test1", [{"role": "user", "content": "First"}])
        store.save("20260115-120001-bbb222", "/tmp/test2", [{"role": "user", "content": "Second"}])

        sessions = store.list_sessions()
        assert len(sessions) == 2
        ids = [s.id for s in sessions]
        assert "20260115-120000-aaa111" in ids
        assert "20260115-120001-bbb222" in ids
        assert all(isinstance(s, SessionInfo) for s in sessions)

    def test_list_sessions_filtered_by_cwd(self, store):
        store.save("20260115-120000-aaa111", "/tmp/cwd1", [{"role": "user", "content": "One"}])
        store.save("20260115-120001-bbb222", "/tmp/cwd2", [{"role": "user", "content": "Two"}])

        sessions = store.list_sessions(cwd="/tmp/cwd1")
        assert len(sessions) == 1
        assert sessions[0].id == "20260115-120000-aaa111"

    def test_delete(self, store):
        session_id = "20260115-120000-dea111"
        store.save(session_id, "/tmp/test", [{"role": "user", "content": "To be deleted"}])
        assert store.load(session_id) is not None

        store.delete(session_id, confirm=False)
        with pytest.raises(KeyError):
            store.load(session_id)

    def test_fork(self, store):
        original_id = "20260115-120000-0ff111"
        messages = [
            {"role": "user", "content": "Original message"},
            {"role": "assistant", "content": "Original response"},
        ]
        store.save(original_id, "/tmp/test", messages)

        new_id = store.fork(original_id, label="Forked session")
        assert new_id != original_id

        doc = store.load(new_id)
        assert len(doc["messages"]) == 3  # original 2 + label message
        assert doc["messages"][2]["content"] == "Forked session"
        assert doc["cwd"] == "/tmp/test"

    def test_rename(self, store):
        session_id = "20260115-120000-cee111"
        store.save(session_id, "/tmp/test", [{"role": "user", "content": "Old title"}])

        store.rename(session_id, "New title")
        doc = store.load(session_id)
        assert doc["title"] == "New title"
        assert doc["messages"][0]["content"] == "New title"

    def test_validate_session_id_rejects_invalid(self, store):
        with pytest.raises(ValueError):
            store._validate_session_id("../escape")
        with pytest.raises(ValueError):
            store._validate_session_id("with/slash")
        with pytest.raises(ValueError):
            store._validate_session_id("with\\backslash")
        with pytest.raises(ValueError):
            store._validate_session_id("invalid-format")
        with pytest.raises(ValueError):
            store._validate_session_id(123)  # not a string

    def test_validate_session_id_accepts_valid(self, store):
        assert store._validate_session_id("20260115-120000-abc123") == "20260115-120000-abc123"


class TestSessionProjection:
    """Tests for SessionProjection."""

    @pytest.fixture
    def projection(self):
        return SessionProjection()

    def test_fold_turn_start(self, projection):
        event = SessionEvent(
            kind="turn/start",
            data={"turn": 1, "model": "zcoder-pro"},
            event_id="evt-1",
            timestamp=1000.0,
        )
        projection.fold(event)
        assert projection.state["turn_count"] == 1
        assert projection.state["current_turn"] == 1
        assert len(projection.state["turns"]) == 1
        assert projection.state["turns"][0]["started_at"] == 1000.0
        assert projection.state["turns"][0]["model"] == "zcoder-pro"

    def test_fold_turn_end(self, projection):
        # Start a turn first
        projection.fold(
            SessionEvent(
                kind="turn/start",
                data={"turn": 1},
                event_id="evt-1",
                timestamp=1000.0,
            )
        )
        projection.fold(
            SessionEvent(
                kind="turn/end",
                data={"turn": 1, "reason": "complete"},
                event_id="evt-2",
                timestamp=2000.0,
            )
        )
        assert projection.state["turn_end_count"] == 1
        assert projection.state["turns"][0]["ended_at"] == 2000.0
        assert projection.state["turns"][0]["reason"] == "complete"

    def test_fold_user_message(self, projection):
        projection.fold(
            SessionEvent(
                kind="user/message",
                data={"content": "Hello"},
                event_id="evt-1",
                timestamp=1000.0,
            )
        )
        assert len(projection.state["messages"]) == 1
        assert projection.state["messages"][0]["role"] == "user"
        assert projection.state["messages"][0]["content"] == "Hello"
        assert projection.state["messages"][0]["timestamp"] == 1000.0
        assert projection.state["messages"][0]["event_id"] == "evt-1"

    def test_fold_assistant_message(self, projection):
        projection.fold(
            SessionEvent(
                kind="assistant/message",
                data={"content": "Hi"},
                event_id="evt-1",
                timestamp=1000.0,
            )
        )
        assert len(projection.state["assistant_messages"]) == 1
        assert projection.state["assistant_messages"][0]["role"] == "assistant"

    def test_fold_tool_call_and_result(self, projection):
        projection.fold(
            SessionEvent(
                kind="tool/call",
                data={"tool_call_id": "tc-1", "tool_name": "read", "arguments": {}},
                event_id="evt-1",
                timestamp=1000.0,
            )
        )
        projection.fold(
            SessionEvent(
                kind="tool/result",
                data={"tool_call_id": "tc-1", "tool_name": "read", "result": "ok"},
                event_id="evt-2",
                timestamp=2000.0,
            )
        )
        assert len(projection.state["tool_calls"]) == 1
        assert projection.state["tool_calls"][0]["tool_name"] == "read"
        assert len(projection.state["tool_results"]) == 1
        assert projection.state["tool_results"][0]["result"] == "ok"

    def test_fold_request_header(self, projection):
        projection.fold(
            SessionEvent(
                kind="request/header",
                data={"header": {}, "reason": "initial", "starts_series": True},
                event_id="evt-1",
                timestamp=1000.0,
            )
        )
        assert projection.state["request_header"]["reason"] == "initial"
        assert projection.state["request_header"]["starts_series"] is True
        assert projection.state["request_header"]["event_id"] == "evt-1"

    def test_fold_many(self, projection):
        events = [
            SessionEvent(kind="turn/start", data={"turn": 1}, event_id="e1", timestamp=1.0),
            SessionEvent(kind="user/message", data={"content": "hi"}, event_id="e2", timestamp=2.0),
            SessionEvent(kind="turn/end", data={"turn": 1, "reason": "done"}, event_id="e3", timestamp=3.0),
        ]
        projection.fold_many(events)
        assert projection.event_count == 3
        assert projection.state["turn_count"] == 1
        assert len(projection.state["messages"]) == 1

    def test_get_state(self, projection):
        projection.fold(SessionEvent(kind="turn/start", data={"turn": 1}, event_id="e1", timestamp=1.0))
        state = projection.get_state()
        assert state["turn_count"] == 1
        # Should be a copy, not the internal state
        state["turn_count"] = 999
        assert projection.state["turn_count"] == 1

    def test_get_session_summary(self, projection):
        projection.fold(SessionEvent(kind="turn/start", data={"turn": 1}, event_id="e1", timestamp=1.0))
        projection.fold(
            SessionEvent(kind="user/message", data={"content": "hi"}, event_id="e2", timestamp=2.0)
        )
        summary = projection.get_session_summary()
        assert summary["event_count"] == 2
        assert summary["turn_count"] == 1
        assert summary["message_count"] == 1
        assert summary["last_event_seq"] == "e2"

    def test_last_event_seq(self, projection):
        projection.fold(SessionEvent(kind="turn/start", data={"turn": 1}, event_id="first", timestamp=1.0))
        projection.fold(
            SessionEvent(kind="user/message", data={"content": "hi"}, event_id="second", timestamp=2.0)
        )
        assert projection.last_event_seq == "second"


class TestSessionStoreAppendEvent:
    """Tests for session event logging via SessionStore."""

    @pytest.fixture
    def store(self, tmp_path):
        return SessionStore(directory=tmp_path / "sessions")

    def test_append_event_and_reload(self, store):
        session_id = "20260115-120000-0dd111"
        messages = [{"role": "user", "content": "Initial"}]
        store.save(session_id, "/tmp/test", messages)

        # Simulate appending an event (the _log_session_event pattern)
        doc = store.load(session_id)
        messages = list(doc.get("messages", []))
        messages.append(
            {
                "kind": "assistant/message",
                "data": {"content": "Hello!"},
                "sourceEventSeqs": None,
                "ignorable": False,
                "surfaceOp": None,
                "eventId": "evt-1",
                "timestamp": 1000.0,
            }
        )
        store.save(session_id, doc.get("cwd", ""), messages, doc.get("usage"))

        doc = store.load(session_id)
        assert len(doc["messages"]) == 2
        assert doc["messages"][1]["kind"] == "assistant/message"
        assert doc["messages"][1]["data"] == {"content": "Hello!"}


class TestSessionInfo:
    """Tests for SessionInfo dataclass."""

    def test_create(self):
        info = SessionInfo(
            id="s1",
            title="Test session",
            cwd="/tmp/test",
            updated=1000.0,
            turns=3,
        )
        assert info.id == "s1"
        assert info.title == "Test session"
        assert info.cwd == "/tmp/test"
        assert info.updated == 1000.0
        assert info.turns == 3


class TestSessionFormatVersion:
    """Tests for SESSION_FORMAT_VERSION constant."""

    def test_version_is_int(self):
        assert isinstance(SESSION_FORMAT_VERSION, int)
        assert SESSION_FORMAT_VERSION > 0


class TestTokenUsage:
    """Tests for TokenUsage dataclass."""

    def test_defaults(self):
        tu = TokenUsage()
        assert tu.input_tokens == 0
        assert tu.output_tokens == 0
        assert tu.model == ""
        assert tu.total_tokens == 0

    def test_full(self):
        tu = TokenUsage(input_tokens=100, output_tokens=50, model="zcoder-pro")
        assert tu.input_tokens == 100
        assert tu.output_tokens == 50
        assert tu.model == "zcoder-pro"
        assert tu.total_tokens == 150


class TestToolUsageStat:
    """Tests for ToolUsageStat dataclass."""

    def test_defaults(self):
        stat = ToolUsageStat(tool_name="read")
        assert stat.tool_name == "read"
        assert stat.call_count == 0
        assert stat.success_count == 0
        assert stat.error_count == 0
        assert stat.total_input_tokens == 0
        assert stat.total_output_tokens == 0
        assert stat.total_cost == 0.0
        assert stat.success_rate == 0.0
        assert stat.total_tokens == 0

    def test_success_rate(self):
        stat = ToolUsageStat(tool_name="read", call_count=10, success_count=8, error_count=2)
        assert stat.success_rate == 0.8

    def test_total_tokens(self):
        stat = ToolUsageStat(
            tool_name="write",
            total_input_tokens=100,
            total_output_tokens=50,
        )
        assert stat.total_tokens == 150


class TestCostBreakdown:
    """Tests for CostBreakdown dataclass."""

    def test_defaults(self):
        cb = CostBreakdown()
        assert cb.input_cost == 0.0
        assert cb.output_cost == 0.0
        assert cb.total_cost == 0.0
        assert cb.by_category == {"input": 0.0, "output": 0.0, "total": 0.0}

    def test_full(self):
        cb = CostBreakdown(input_cost=1.5, output_cost=2.5)
        assert cb.input_cost == 1.5
        assert cb.output_cost == 2.5
        assert cb.total_cost == 4.0
        assert cb.by_category == {"input": 1.5, "output": 2.5, "total": 4.0}


class TestEstimateCost:
    """Tests for estimate_cost function."""

    def test_default_model(self):
        cost = estimate_cost(1000, 500)
        expected = (1000 / 1000.0) * DEFAULT_MODEL_PRICING["zcoder-flash"]["input"] + (
            500 / 1000.0
        ) * DEFAULT_MODEL_PRICING["zcoder-flash"]["output"]
        assert abs(cost - expected) < 1e-10

    def test_specific_model(self):
        cost = estimate_cost(1000, 500, model="zcoder-pro")
        expected = (1000 / 1000.0) * DEFAULT_MODEL_PRICING["zcoder-pro"]["input"] + (
            500 / 1000.0
        ) * DEFAULT_MODEL_PRICING["zcoder-pro"]["output"]
        assert abs(cost - expected) < 1e-10

    def test_zero_tokens(self):
        cost = estimate_cost(0, 0)
        assert cost == 0.0

    def test_unknown_model_uses_flash(self):
        cost = estimate_cost(1000, 500, model="unknown-model")
        expected = (1000 / 1000.0) * DEFAULT_MODEL_PRICING["zcoder-flash"]["input"] + (
            500 / 1000.0
        ) * DEFAULT_MODEL_PRICING["zcoder-flash"]["output"]
        assert abs(cost - expected) < 1e-10


class TestSessionProjectionTokenTracking:
    """Tests for token usage tracking in SessionProjection."""

    @pytest.fixture
    def projection(self):
        return SessionProjection()

    def test_track_tokens_from_event(self, projection):
        event = SessionEvent(
            kind="request/header",
            data={"input_tokens": 100, "output_tokens": 50, "model": "zcoder-pro"},
            event_id="evt-1",
            timestamp=1000.0,
        )
        projection.fold(event)
        assert projection.total_input_tokens == 100
        assert projection.total_output_tokens == 50
        assert projection.cost_breakdown.total_cost > 0

    def test_get_token_usage(self, projection):
        projection.fold(
            SessionEvent(
                kind="request/header",
                data={"input_tokens": 100, "output_tokens": 50, "model": "zcoder-pro"},
                event_id="evt-1",
                timestamp=1000.0,
            )
        )
        usage = projection.get_token_usage()
        assert usage["total_input_tokens"] == 100
        assert usage["total_output_tokens"] == 50
        assert usage["total_tokens"] == 150
        assert usage["model"] == "zcoder-pro"


class TestSessionProjectionToolStats:
    """Tests for tool usage statistics in SessionProjection."""

    @pytest.fixture
    def projection(self):
        return SessionProjection()

    def test_tool_call_and_result_tracking(self, projection):
        projection.fold(
            SessionEvent(
                kind="tool/call",
                data={
                    "tool_name": "read",
                    "arguments": {"path": "/tmp/test"},
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "model": "zcoder-pro",
                },
                event_id="evt-1",
                timestamp=1000.0,
            )
        )
        projection.fold(
            SessionEvent(
                kind="tool/result",
                data={
                    "tool_name": "read",
                    "result": "ok",
                    "is_error": False,
                    "input_tokens": 0,
                    "output_tokens": 20,
                    "model": "zcoder-pro",
                },
                event_id="evt-2",
                timestamp=2000.0,
            )
        )
        stats = projection.get_tool_statistics()
        assert "read" in stats
        assert stats["read"]["call_count"] == 1
        assert stats["read"]["success_count"] == 1
        assert stats["read"]["error_count"] == 0
        assert stats["read"]["success_rate"] == 1.0
        assert stats["read"]["total_input_tokens"] == 10
        assert stats["read"]["total_output_tokens"] == 25

    def test_tool_error_tracking(self, projection):
        projection.fold(
            SessionEvent(
                kind="tool/call",
                data={"tool_name": "write", "arguments": {"path": "/tmp/x"}},
                event_id="evt-1",
                timestamp=1000.0,
            )
        )
        projection.fold(
            SessionEvent(
                kind="tool/result",
                data={"tool_name": "write", "result": "error", "is_error": True},
                event_id="evt-2",
                timestamp=2000.0,
            )
        )
        stats = projection.get_tool_statistics()
        assert stats["write"]["call_count"] == 1
        assert stats["write"]["success_count"] == 0
        assert stats["write"]["error_count"] == 1
        assert stats["write"]["success_rate"] == 0.0


class TestSessionProjectionCostTracking:
    """Tests for cost tracking in SessionProjection."""

    @pytest.fixture
    def projection(self):
        return SessionProjection()

    def test_cost_tracking_from_tokens(self, projection):
        projection.fold(
            SessionEvent(
                kind="request/header",
                data={"input_tokens": 1000, "output_tokens": 500, "model": "zcoder-pro"},
                event_id="evt-1",
                timestamp=1000.0,
            )
        )
        breakdown = projection.get_cost_breakdown()
        assert breakdown["total_cost"] > 0
        assert breakdown["input_cost"] > 0
        assert breakdown["output_cost"] > 0


class TestSessionProjectionAnalytics:
    """Tests for session analytics in SessionProjection."""

    @pytest.fixture
    def projection(self):
        return SessionProjection()

    def test_get_session_analytics(self, projection):
        projection.fold(
            SessionEvent(
                kind="turn/start",
                data={"turn": 1},
                event_id="evt-1",
                timestamp=1000.0,
            )
        )
        projection.fold(
            SessionEvent(
                kind="user/message",
                data={"content": "hi"},
                event_id="evt-2",
                timestamp=2000.0,
            )
        )
        projection.fold(
            SessionEvent(
                kind="turn/end",
                data={"turn": 1, "reason": "complete"},
                event_id="evt-3",
                timestamp=3000.0,
            )
        )
        analytics = projection.get_session_analytics()
        assert analytics["turn_count"] == 1
        assert analytics["message_count"] == 1
        assert analytics["session_duration_seconds"] == 2000.0
        assert analytics["model"] == "zcoder-flash"

    def test_extended_session_summary(self, projection):
        projection.fold(
            SessionEvent(
                kind="turn/start",
                data={"turn": 1, "model": "zcoder-pro"},
                event_id="evt-1",
                timestamp=1000.0,
            )
        )
        projection.fold(
            SessionEvent(
                kind="request/header",
                data={"input_tokens": 1000, "output_tokens": 500, "model": "zcoder-pro"},
                event_id="evt-2",
                timestamp=2000.0,
            )
        )
        projection.fold(
            SessionEvent(
                kind="turn/end",
                data={"turn": 1, "reason": "complete"},
                event_id="evt-3",
                timestamp=3000.0,
            )
        )
        summary = projection.get_session_summary()
        assert summary["total_input_tokens"] == 1000
        assert summary["total_output_tokens"] == 500
        assert summary["total_tokens"] == 1500
        assert summary["total_cost"] > 0
        assert summary["model"] == "zcoder-pro"
        assert summary["session_duration_seconds"] == 2000.0


class TestLoggingFunctionsWithTokens:
    """Tests for logging functions with token/cost data."""

    @pytest.fixture
    def store(self, tmp_path):
        return SessionStore(directory=tmp_path / "sessions")

    def test_log_tool_call_with_tokens(self, store):
        session_id = "20260115-120000-000001"
        store.save(session_id, "/tmp/test", [{"role": "user", "content": "Hi"}])
        log_tool_call(
            store,
            session_id,
            "read",
            {"path": "/tmp/x"},
            input_tokens=10,
            output_tokens=5,
            model="zcoder-pro",
        )
        doc = store.load(session_id)
        events = [m for m in doc["messages"] if m.get("kind") == "tool/call"]
        assert len(events) == 1
        assert events[0]["data"]["input_tokens"] == 10
        assert events[0]["data"]["output_tokens"] == 5
        assert events[0]["data"]["model"] == "zcoder-pro"

    def test_log_tool_result_with_tokens(self, store):
        session_id = "20260115-120000-000002"
        store.save(session_id, "/tmp/test", [{"role": "user", "content": "Hi"}])
        log_tool_result(
            store,
            session_id,
            "read",
            "file contents",
            is_error=False,
            input_tokens=0,
            output_tokens=20,
            model="zcoder-pro",
        )
        doc = store.load(session_id)
        events = [m for m in doc["messages"] if m.get("kind") == "tool/result"]
        assert len(events) == 1
        assert events[0]["data"]["is_error"] is False
        assert events[0]["data"]["output_tokens"] == 20

    def test_log_token_usage(self, store):
        session_id = "20260115-120000-000003"
        store.save(session_id, "/tmp/test", [{"role": "user", "content": "Hi"}])
        log_token_usage(store, session_id, 100, 50, model="zcoder-pro", turn=1)
        doc = store.load(session_id)
        events = [m for m in doc["messages"] if m.get("kind") == "request/context"]
        assert len(events) == 1
        assert events[0]["data"]["input_tokens"] == 100
        assert events[0]["data"]["output_tokens"] == 50
        assert events[0]["data"]["model"] == "zcoder-pro"
        assert events[0]["data"]["turn"] == 1

    def test_log_cost_event(self, store):
        session_id = "20260115-120000-000004"
        store.save(session_id, "/tmp/test", [{"role": "user", "content": "Hi"}])
        log_cost_event(store, session_id, 0.0015, 0.003, model="zcoder-pro")
        doc = store.load(session_id)
        events = [m for m in doc["messages"] if m.get("kind") == "request/context"]
        assert len(events) == 1
        assert abs(events[0]["data"]["input_cost"] - 0.0015) < 1e-10
        assert abs(events[0]["data"]["output_cost"] - 0.003) < 1e-10
        assert abs(events[0]["data"]["total_cost"] - 0.0045) < 1e-10
        assert events[0]["data"]["model"] == "zcoder-pro"
