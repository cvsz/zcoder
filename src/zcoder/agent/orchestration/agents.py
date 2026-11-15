"""
agents.py — Agent System Formalization (Phase 6 of Big Upgrade).

AgentRegistry with create/resume/register/enter/announce/setFactory/get/list/
turnBoundaryOf, Agent handle (id, options, session, model, inbox, status,
cancel, whenIdle, runMaintenance, send, followup, steer, inject), ModelSelection
type, projections, agent/* events, and initiator scope.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class AgentStatus(StrEnum):
    IDLE = "idle"
    BUSY = "busy"
    CANCELLED = "cancelled"
    ERROR = "error"


@dataclass(frozen=True)
class ModelSelection:
    """How an agent selects its model."""

    strategy: str = "round-robin"  # round-robin | pinned | capability-based
    candidates: list[str] = field(default_factory=list)
    pinned: str | None = None


@dataclass(frozen=True)
class AgentOptions:
    model_selection: ModelSelection = field(default_factory=ModelSelection)
    system: str | None = None
    temperature: float | None = None


@dataclass
class Agent:
    """Agent handle."""

    id: str
    options: AgentOptions
    session: str | None = None
    model: str | None = None
    inbox: list[dict[str, Any]] = field(default_factory=list)
    status: AgentStatus = AgentStatus.IDLE
    _cancel_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)

    def cancel(self) -> None:
        self._cancel_event.set()
        self.status = AgentStatus.CANCELLED

    async def whenIdle(self) -> None:
        while self.status != AgentStatus.IDLE:
            await asyncio.sleep(0.05)

    def runMaintenance(self) -> None:
        self.inbox = [m for m in self.inbox if not m.get("_expired", False)]

    def send(self, message: dict[str, Any]) -> None:
        self.inbox.append(message)
        self.status = AgentStatus.BUSY

    def followup(self, message: dict[str, Any]) -> None:
        self.inbox.append({**message, "followup": True})

    def steer(self, instruction: str) -> None:
        self.inbox.append({"steer": instruction})

    def inject(self, payload: dict[str, Any]) -> None:
        self.inbox.append({"inject": payload})


@dataclass
class ProjectionDefinition:
    name: str
    compute: Callable[[list[dict[str, Any]]], dict[str, Any]]


class AgentRegistry:
    """Registry of agents."""

    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}
        self._factories: dict[str, Callable] = {}
        self._projections: dict[str, ProjectionDefinition] = {}
        self._counter = 0

    def create(self, options: AgentOptions | None = None, session: str | None = None) -> Agent:
        self._counter += 1
        agent_id = f"agent-{self._counter}"
        agent = Agent(
            id=agent_id,
            options=options or AgentOptions(),
            session=session,
        )
        self._agents[agent_id] = agent
        return agent

    def resume(self, agent_id: str) -> Agent | None:
        return self._agents.get(agent_id)

    def register(self, name: str, factory: Callable) -> None:
        self._factories[name] = factory

    def enter(self, agent_id: str, session: str) -> None:
        agent = self._agents.get(agent_id)
        if agent:
            agent.session = session

    def announce(self, agent_id: str) -> dict[str, Any]:
        agent = self._agents.get(agent_id)
        if not agent:
            return {"error": "unknown agent"}
        return {
            "id": agent.id,
            "session": agent.session,
            "status": agent.status.value,
            "model": agent.model,
        }

    def setFactory(self, name: str, factory: Callable) -> None:
        self.register(name, factory)

    def get(self, agent_id: str) -> Agent | None:
        return self._agents.get(agent_id)

    def list_agents(self) -> list[str]:
        return sorted(self._agents.keys())

    def turnBoundaryOf(self, agent_id: str) -> dict[str, Any] | None:
        agent = self._agents.get(agent_id)
        if not agent:
            return None
        return {
            "agent_id": agent.id,
            "session": agent.session,
            "inbox_count": len(agent.inbox),
            "status": agent.status.value,
        }

    def register_projection(self, name: str, compute: Callable) -> None:
        self._projections[name] = ProjectionDefinition(name=name, compute=compute)

    def run_projection(self, name: str, events: list[dict[str, Any]]) -> dict[str, Any] | None:
        proj = self._projections.get(name)
        if not proj:
            return None
        return proj.compute(events)


# Agent event types (emitted into session log)
AGENT_EVENT_CREATE = "agent/create"
AGENT_EVENT_ENTER = "agent/enter"
AGENT_EVENT_ANNOUNCE = "agent/announce"
AGENT_EVENT_SEND = "agent/send"
AGENT_EVENT_TURN_BOUNDARY = "agent/turn-boundary"


def withInitiator(events: list[dict[str, Any]], initiator: str) -> list[dict[str, Any]]:
    """Scope events to those initiated by ``initiator``."""
    return [e for e in events if e.get("initiator") == initiator]


def withoutInitiator(events: list[dict[str, Any]], initiator: str) -> list[dict[str, Any]]:
    """Scope events to those NOT initiated by ``initiator``."""
    return [e for e in events if e.get("initiator") != initiator]


# Default model selection projections for query from event store
modelSelectionProjectionDefinition = ProjectionDefinition(
    name="modelSelection",
    compute=lambda events: {
        "selections": [
            e.get("payload", {}).get("model_selection")
            for e in events
            if e.get("event_type") == AGENT_EVENT_CREATE
        ]
    },
)

turnBoundaryProjectionDefinition = ProjectionDefinition(
    name="turnBoundary",
    compute=lambda events: {
        "boundaries": [
            e.get("payload", {})
            for e in events
            if e.get("event_type") == AGENT_EVENT_TURN_BOUNDARY
        ]
    },
)
