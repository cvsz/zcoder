"""Tests for zcoder.agent.base - Base agent class."""

import asyncio
from typing import Any

import pytest

from zcoder.agent.base import AgentError
from zcoder.session.event import (
    EventType,
    SessionEvent,
    brandEventId,
    brandSessionId,
    brandToolCallId,
)
from zcoder.session.logger import SessionEventStore


class TestAgent:
    """Test agent implementation for testing."""

    def __init__(self, session_id: str = "test-session", agent_id: str = "test-agent"):
        self.session_id = session_id
        self.agent_id = agent_id
        self.services = {}
        self.running = False
        self._interrupted = False
        self.calls = []

    @property
    def name(self) -> str:
        return self.agent_id

    async def run(self, prompt: str):
        self.calls.append(prompt)
        yield f"Response to: {prompt}"

    async def start(self) -> None:
        self.running = True
        self._interrupted = False

    async def stop(self) -> None:
        self.running = False
        self._interrupted = True

    def interrupt(self) -> None:
        self._interrupted = True

    def get_service(self, name: str):
        if name not in self.services:
            raise AgentError(
                f"Service '{name}' not registered",
                details={"agent": self.agent_id, "service": name},
            )
        return self.services[name]

    def register_service(self, name: str, service: Any) -> None:
        self.services[name] = service

    def is_running(self) -> bool:
        return self.running


class TestBaseAgent:
    """Tests for BaseAgent base class."""

    def test_create_base_agent(self):
        agent = TestAgent(session_id="s1", agent_id="agent-1")
        assert agent.session_id == "s1"
        assert agent.agent_id == "agent-1"
        assert agent.is_running() is False

    def test_start_stop(self):
        agent = TestAgent(session_id="s1", agent_id="agent-1")

        async def run_test():
            await agent.start()
            assert agent.running is True
            assert agent._interrupted is False
            await agent.stop()
            assert agent.running is False

        asyncio.run(run_test())

    def test_interrupt(self):
        agent = TestAgent(session_id="s1", agent_id="agent-1")
        agent.running = True
        agent._interrupted = False

        agent.interrupt()
        assert agent._interrupted is True

    def test_register_service(self):
        agent = TestAgent(session_id="s1", agent_id="agent-1")

        agent.register_service("llm", "my-llm-service")
        assert agent.get_service("llm") == "my-llm-service"

    def test_get_service_missing(self):
        agent = TestAgent(session_id="s1", agent_id="agent-1")

        with pytest.raises(AgentError) as exc_info:
            agent.get_service("nonexistent")
        assert exc_info.value.error_code == "AGENT_ERROR"


class TestAgentIntegration:
    """Integration tests for agent with session store."""

    def test_agent_with_session_store(self, tmp_path):
        store = SessionEventStore(db_path=tmp_path / "session.db")
        session_id = brandSessionId("test-session")

        # Verify we can create a session and log events
        event = SessionEvent(
            event_type=EventType.TURN_START,
            session_id=session_id,
            event_id=brandEventId("e1"),
            payload={"turn": 1},
        )
        store.append(event)
        events = store.get_events("test-session")
        assert len(events) == 1
        assert events[0].event_type == EventType.TURN_START

    def test_agent_branded_ids(self):
        from zcoder.session.event import brandEventId, brandSessionId

        sid = brandSessionId("session-1")
        eid = brandEventId("event-1")
        tcid = brandToolCallId("tool-1")

        assert str(sid) == "session-1"
        assert str(eid) == "event-1"
        assert str(tcid) == "tool-1"
