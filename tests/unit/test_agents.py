"""Unit tests for Phase 6: Agent System Formalization."""

from __future__ import annotations

import asyncio

from zcoder.agent.orchestration.agents import (
    AGENT_EVENT_CREATE,
    AGENT_EVENT_ENTER,
    AGENT_EVENT_SEND,
    AGENT_EVENT_TURN_BOUNDARY,
    Agent,
    AgentOptions,
    AgentRegistry,
    AgentStatus,
    ModelSelection,
    modelSelectionProjectionDefinition,
    turnBoundaryProjectionDefinition,
    withInitiator,
    withoutInitiator,
)


def test_model_selection_defaults():
    ms = ModelSelection()
    assert ms.strategy == "round-robin"
    assert ms.candidates == []
    assert ms.pinned is None


def test_agent_registry_create_resume_get_list():
    reg = AgentRegistry()
    assert reg.list_agents() == []
    agent = reg.create(AgentOptions(), session="s1")
    assert agent.id.startswith("agent-")
    assert agent.status == AgentStatus.IDLE
    assert reg.list_agents() == [agent.id]
    assert reg.get(agent.id) is agent
    assert reg.resume(agent.id) is agent
    assert reg.get("nonexistent") is None


def test_agent_register_factory():
    reg = AgentRegistry()
    reg.register("greeter", lambda: "hello")
    assert "greeter" in reg._factories


def test_agent_enter_announce():
    reg = AgentRegistry()
    agent = reg.create(session=None)
    reg.enter(agent.id, "session-1")
    assert agent.session == "session-1"
    info = reg.announce(agent.id)
    assert info["id"] == agent.id
    assert info["session"] == "session-1"
    assert info["status"] == "idle"
    assert reg.announce("nope") == {"error": "unknown agent"}


def test_agent_send_followup_steer_inject():
    agent = Agent(id="a1", options=AgentOptions())
    agent.send({"role": "user", "content": "hi"})
    agent.followup({"role": "user", "content": "again"})
    agent.steer("be concise")
    agent.inject({"key": "val"})
    assert len(agent.inbox) == 4
    assert agent.status == AgentStatus.BUSY


def test_agent_cancel_whenidle():
    agent = Agent(id="a2", options=AgentOptions())
    agent.cancel()
    assert agent.status == AgentStatus.CANCELLED

    async def main():
        agent2 = Agent(id="a3", options=AgentOptions())
        agent2.status = AgentStatus.BUSY
        # whenIdle should return promptly once status is IDLE
        agent2.status = AgentStatus.IDLE
        await asyncio.wait_for(agent2.whenIdle(), timeout=1)

    asyncio.run(main())


def test_agent_runmaintenance():
    agent = Agent(id="a4", options=AgentOptions())
    agent.inbox = [{"x": 1, "_expired": True}, {"x": 2}]
    agent.runMaintenance()
    assert len(agent.inbox) == 1
    assert agent.inbox[0]["x"] == 2


def test_agent_event_constants():
    assert AGENT_EVENT_CREATE == "agent/create"
    assert AGENT_EVENT_ENTER == "agent/enter"
    assert AGENT_EVENT_SEND == "agent/send"
    assert AGENT_EVENT_TURN_BOUNDARY == "agent/turn-boundary"


def test_model_selection_projection():
    events = [
        {"event_type": AGENT_EVENT_CREATE, "payload": {"model_selection": {"strategy": "pinned"}}},
        {"event_type": AGENT_EVENT_CREATE, "payload": {"model_selection": {"strategy": "round-robin"}}},
    ]
    proj = modelSelectionProjectionDefinition.compute(events)
    assert proj["selections"] == [{"strategy": "pinned"}, {"strategy": "round-robin"}]


def test_turn_boundary_projection():
    events = [
        {"event_type": AGENT_EVENT_TURN_BOUNDARY, "payload": {"inbox_count": 3}},
        {"event_type": AGENT_EVENT_TURN_BOUNDARY, "payload": {"inbox_count": 0}},
    ]
    proj = turnBoundaryProjectionDefinition.compute(events)
    assert proj["boundaries"] == [{"inbox_count": 3}, {"inbox_count": 0}]


def test_with_without_initiator():
    events = [
        {"initiator": "alice", "msg": "a"},
        {"initiator": "bob", "msg": "b"},
        {"initiator": "alice", "msg": "c"},
    ]
    assert len(withInitiator(events, "alice")) == 2
    assert len(withoutInitiator(events, "alice")) == 1
    assert withoutInitiator(events, "alice")[0]["msg"] == "b"
