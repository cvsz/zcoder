"""Agent Discovery Registry for Phase 17.

Provides a service registry for agent discovery and lookup,
enabling distributed task offloading and agent communication.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


class RegistryState(Enum):
    """State of the agent registry."""

    OFFLINE = "offline"
    ONLINE = "online"
    MAINTENANCE = "maintenance"


@dataclass
class AgentDescription:
    """Description of an agent available in the network."""

    agent_id: str
    name: str
    capabilities: set[str] = field(default_factory=set)
    endpoint: str = ""  # HTTP endpoint or connection string
    metadata: dict[str, Any] = field(default_factory=dict)
    last_seen: float = 0.0
    tags: set[str] = field(default_factory=set)


class AgentRegistry:
    """Service registry for agent discovery."""

    def __init__(self, backend: str = "memory", registry_url: str | None = None) -> None:
        self.backend = backend
        self.registry_url = registry_url
        self._agents: dict[str, AgentDescription] = {}
        self._state: RegistryState = RegistryState.OFFLINE
        self._refresh_task: asyncio.Task | None = None

    def start(self) -> None:
        """Start the registry service."""
        self._state = RegistryState.ONLINE
        if self.backend == "memory":
            # In-memory registry, no background refresh needed
            pass
        elif self.backend == "http" and self.registry_url:
            self._refresh_task = asyncio.create_task(self._periodic_refresh())

    def stop(self) -> None:
        """Stop the registry service."""
        self._state = RegistryState.OFFLINE
        if self._refresh_task:
            self._refresh_task.cancel()
            self._refresh_task = None

    def register(self, agent: AgentDescription) -> None:
        """Register an agent in the registry."""
        self._agents[agent.agent_id] = agent
        agent.last_seen = time.time()
        logger.info(f"Registered agent: {agent.agent_id} ({agent.name})")

    def unregister(self, agent_id: str) -> None:
        """Unregister an agent from the registry."""
        if agent_id in self._agents:
            del self._agents[agent_id]
            logger.info(f"Unregistered agent: {agent_id}")

    def get(self, agent_id: str) -> AgentDescription | None:
        """Get an agent description by ID."""
        agent = self._agents.get(agent_id)
        if agent and self._is_stale(agent):
            # Remove stale agents
            del self._agents[agent_id]
            return None
        return agent

    def search(
        self, capabilities: set[str] | None = None, tags: set[str] | None = None
    ) -> list[AgentDescription]:
        """Search for agents matching given capabilities and/or tags."""
        results: list[AgentDescription] = []
        for agent in self._agents.values():
            if self._matches(agent, capabilities, tags):
                results.append(agent)
        return results

    def _matches(self, agent: AgentDescription, capabilities: set[str] | None, tags: set[str] | None) -> bool:
        """Check if an agent matches the search criteria."""
        if capabilities:
            if not capabilities.issubset(agent.capabilities):
                return False
        if tags:
            if not tags.intersection(agent.tags):
                return False
        return True

    def _is_stale(self, agent: AgentDescription, max_age: float = 300.0) -> bool:
        """Check if an agent is stale based on last_seen timestamp."""
        return time.time() - agent.last_seen > max_age

    def list_agents(self) -> list[AgentDescription]:
        """List all registered agents."""
        return list(self._agents.values())

    async def discover(
        self, capabilities: set[str] | None = None, tags: set[str] | None = None, timeout: float = 5.0
    ) -> list[AgentDescription]:
        """Discover agents matching criteria, potentially via HTTP registry."""
        if self.backend == "http" and self.registry_url:
            return await self._http_discover(capabilities, tags, timeout)
        return self.search(capabilities, tags)

    async def _http_discover(
        self, capabilities: set[str] | None, tags: set[str] | None, timeout: float
    ) -> list[AgentDescription]:
        """Discover agents via HTTP registry endpoint."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.registry_url}/agents",
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        agents: list[AgentDescription] = []
                        for item in data.get("agents", []):
                            agent = AgentDescription(
                                agent_id=item.get("agent_id", ""),
                                name=item.get("name", ""),
                                capabilities=set(item.get("capabilities", [])),
                                endpoint=item.get("endpoint", ""),
                                metadata=item.get("metadata", {}),
                                last_seen=item.get("last_seen", 0.0),
                                tags=set(item.get("tags", [])),
                            )
                            agents.append(agent)
                        return agents
        except Exception as e:
            logger.warning(f"HTTP agent discovery failed: {e}")
        return []


def create_default_registry() -> AgentRegistry:
    """Create a default in-memory agent registry."""
    registry = AgentRegistry(backend="memory")
    registry.start()
    return registry
