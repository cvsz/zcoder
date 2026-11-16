"""Integration tests for full session lifecycle using zcoder.agent.codeagent.sessions.

These tests cover the complete session lifecycle end-to-end:
1. Create a session store
2. Save a session with messages
3. Load the session back
4. Log events (turn start/end, user/assistant messages, tool calls/results, request headers)
5. Project events into session state
6. Generate session summary
7. Verify persistence across save/load cycles
"""

from __future__ import annotations

import pytest

from zcoder.agent.codeagent.sessions import (
    SessionEvent,
    SessionProjection,
    SessionStore,
    log_assistant_message,
    log_request_header,
    log_tool_call,
    log_tool_result,
    log_turn_end,
    log_turn_start,
    log_user_message,
)


class TestSessionLifecycle:
    """Full session lifecycle integration tests."""

    @pytest.fixture
    def store(self, tmp_path):
        return SessionStore(directory=tmp_path / "sessions")

    def test_full_lifecycle_save_load_append_project(self, store):
        """Complete lifecycle: save → load → append events → project → summarize."""
        session_id = "20260115-120000-abcdef"

        # --- Phase 1: Save initial session ---
        messages = [{"role": "user", "content": "What is the capital of France?"}]
        store.save(session_id, "/tmp/project", messages)

        # --- Phase 2: Load the session ---
        doc = store.load(session_id)
        assert doc["id"] == session_id
        assert doc["title"] == "What is the capital of France?"
        assert len(doc["messages"]) == 1

        # --- Phase 3: Append events via log functions ---
        log_turn_start(store, session_id, turn=1)
        log_user_message(store, session_id, turn=1, step=1, content="What is the capital of France?")
        log_assistant_message(store, session_id, turn=1, step=2, content="Paris is the capital of France.")
        log_tool_call(store, session_id, tool_name="read", arguments={"path": "/tmp/notes.txt"})
        log_tool_result(store, session_id, tool_name="read", result="Paris\n")
        log_turn_end(store, session_id, turn=1, reason="complete")
        log_request_header(
            store, session_id, header={"model": "zcoder-pro"}, reason="initial", starts_series=True
        )

        # --- Phase 4: Reload and verify events persisted ---
        doc = store.load(session_id)
        event_messages = [m for m in doc["messages"] if "kind" in m]
        kinds = [m["kind"] for m in event_messages]
        assert "turn/start" in kinds
        assert "user/message" in kinds
        assert "assistant/message" in kinds
        assert "tool/call" in kinds
        assert "tool/result" in kinds
        assert "turn/end" in kinds
        assert "request/header" in kinds

        # --- Phase 5: Project events into state ---
        projection = SessionProjection()
        for m in event_messages:
            event = SessionEvent(
                kind=m["kind"],
                data=m["data"],
                event_id=m.get("eventId", ""),
                timestamp=m.get("timestamp", 0.0),
            )
            projection.fold(event)

        assert projection.state["turn_count"] == 1
        assert projection.state["turn_end_count"] == 1
        assert len(projection.state["messages"]) == 1
        assert len(projection.state["assistant_messages"]) == 1
        assert len(projection.state["tool_calls"]) == 1
        assert len(projection.state["tool_results"]) == 1
        assert projection.state["request_header"]["reason"] == "initial"

        # --- Phase 6: Get session summary ---
        summary = projection.get_session_summary()
        assert summary["turn_count"] == 1
        assert summary["message_count"] == 1
        assert summary["tool_call_count"] == 1
        assert summary["tool_result_count"] == 1
        assert isinstance(summary["last_event_seq"], str)

    def test_session_persistence_across_store_instances(self, tmp_path):
        """Data survives when a new SessionStore instance opens the same directory."""
        session_id = "20260115-120000-fedcba"

        store1 = SessionStore(directory=tmp_path / "sessions")
        store1.save(session_id, "/tmp/project", [{"role": "user", "content": "Persistent data"}])

        # New store instance pointing to the same directory
        store2 = SessionStore(directory=tmp_path / "sessions")
        doc = store2.load(session_id)
        assert doc["title"] == "Persistent data"
        assert len(doc["messages"]) == 1

    def test_multiple_sessions_independent(self, store):
        """Multiple sessions are independent; saving one doesn't affect others."""
        store.save("20260115-120000-000001", "/tmp/a", [{"role": "user", "content": "Session A"}])
        store.save("20260115-120001-000002", "/tmp/b", [{"role": "user", "content": "Session B"}])

        sessions = store.list_sessions()
        assert len(sessions) == 2

        doc_a = store.load("20260115-120000-000001")
        assert doc_a["messages"][0]["content"] == "Session A"

        doc_b = store.load("20260115-120001-000002")
        assert doc_b["messages"][0]["content"] == "Session B"

    def test_fork_creates_independent_copy(self, store):
        """Forking a session creates a new independent session with copied messages."""
        original_id = "20260115-120000-000003"
        store.save(
            original_id,
            "/tmp/project",
            [
                {"role": "user", "content": "Original question"},
                {"role": "assistant", "content": "Original answer"},
            ],
        )

        forked_id = store.fork(original_id, label="Follow-up question")

        # Forked session is different
        assert forked_id != original_id

        # Forked session has original messages + label
        forked = store.load(forked_id)
        assert len(forked["messages"]) == 3
        assert forked["messages"][2]["content"] == "Follow-up question"

        # Original session unchanged
        original = store.load(original_id)
        assert len(original["messages"]) == 2

    def test_list_sessions_sorted_by_updated_desc(self, store):
        """list_sessions returns sessions sorted by updated time descending."""
        # Save sessions in order
        store.save("20260115-120000-000004", "/tmp/x", [{"role": "user", "content": "First"}])
        store.save("20260115-120001-000005", "/tmp/x", [{"role": "user", "content": "Second"}])

        sessions = store.list_sessions()
        assert len(sessions) == 2
        # Most recently updated should be first
        assert sessions[0].id == "20260115-120001-000005"
        assert sessions[1].id == "20260115-120000-000004"

    def test_projection_event_count_and_last_seq(self, store):
        """Projection correctly counts events and tracks last event sequence."""
        session_id = "20260115-120000-000006"
        store.save(session_id, "/tmp/x", [{"role": "user", "content": "Hi"}])

        log_turn_start(store, session_id, turn=1)
        log_user_message(store, session_id, turn=1, step=1, content="Hello")
        log_turn_end(store, session_id, turn=1, reason="done")

        doc = store.load(session_id)
        event_messages = [m for m in doc["messages"] if "kind" in m]
        projection = SessionProjection()
        for m in event_messages:
            event = SessionEvent(
                kind=m["kind"],
                data=m["data"],
                event_id=m.get("eventId", ""),
                timestamp=m.get("timestamp", 0.0),
            )
            projection.fold(event)

        assert projection.event_count == 3  # turn/start + user/message + turn/end
        assert isinstance(projection.last_event_seq, str)
