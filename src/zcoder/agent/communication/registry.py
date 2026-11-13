"""
Agent discovery registry for Phase 17.

Provides agent discovery and registry service for distributed agent systems.
Supports local agent registration, remote discovery, and capability tracking.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

AGENT_REGISTRY_DIR = Path.home() / ".zcoder" / "agent_registry"
REGISTRY_FILE = AGENT_REGISTRY_DIR / "agents.json"

# Module-level registry instance
_instance: AgentRegistry | None = None


def _ensure_registry_dir() -> None:
    """Ensure the agent registry directory exists."""
    AGENT_REGISTRY_DIR.mkdir(parents=True, exist_ok=True)


def _load_registry() -> dict[str, dict[str, Any]]:
    """Load the agent registry from disk."""
    _ensure_registry_dir()
    if not REGISTRY_FILE.exists():
        return {}
    try:
        with open(REGISTRY_FILE) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_registry(registry: dict[str, dict[str, Any]]) -> None:
    """Save the agent registry to disk."""
    _ensure_registry_dir()
    with open(REGISTRY_FILE, "w") as f:
        json.dump(registry, f, indent=2)


class AgentRegistry:
    """Agent discovery registry for distributed agent systems."""

    def __init__(self) -> None:
        """Initialize the registry, loading from disk if needed."""
        self._registry: dict[str, dict[str, Any]] = _load_registry()

    def register_agent(self, agent: AgentInfo) -> None:
        """Register an agent in the registry."""
        self._registry[agent.agent_id] = {
            "name": agent.name,
            "capabilities": agent.capabilities,
            "endpoint": agent.endpoint,
            "last_seen": agent.last_seen,
            "tags": agent.tags,
        }
        _save_registry(self._registry)

    def unregister_agent(self, agent_id: str) -> None:
        """Unregister an agent from the registry."""
        if agent_id in self._registry:
            del self._registry[agent_id]
            _save_registry(self._registry)

    def get_agent(self, agent_id: str) -> AgentInfo | None:
        """Get information about a specific agent."""
        if agent_id not in self._registry:
            return None
        info = self._registry[agent_id]
        return AgentInfo(
            agent_id=agent_id,
            name=info["name"],
            capabilities=info.get("capabilities", {}),
            endpoint=info.get("endpoint", ""),
            last_seen=info.get("last_seen", 0),
            tags=info.get("tags", []),
        )

    def list_agents(self) -> list[AgentInfo]:
        """List all registered agents."""
        return [
            AgentInfo(
                agent_id=aid,
                name=info["name"],
                capabilities=info.get("capabilities", {}),
                endpoint=info.get("endpoint", ""),
                last_seen=info.get("last_seen", 0),
                tags=info.get("tags", []),
            )
            for aid, info in self._registry.items()
        ]

    def find_agents_by_capability(
        self, capability: str, tag: str | None = None
    ) -> list[AgentInfo]:
        """Find agents that have a specific capability or tag."""
        matching: list[AgentInfo] = []
        for agent_id, info in self._registry.items():
            capabilities = info.get("capabilities", {})
            tags = info.get("tags", [])
            has_capability = capability in capabilities
            has_tag = tag is None or tag in tags
            if has_capability or has_tag:
                matching.append(
                    AgentInfo(
                        agent_id=agent_id,
                        name=info["name"],
                        capabilities=capabilities,
                        endpoint=info.get("endpoint", ""),
                        last_seen=info.get("last_seen", 0),
                        tags=tags,
                    )
                )
        return matching

    def search_agents(
        self, query: str, search_in: list[str] | None = None
    ) -> list[AgentInfo]:
        """Search for agents by name or tags."""
        if search_in is None:
            search_in = ["name", "tags"]

        query_lower = query.lower()
        matching: list[AgentInfo] = []
        for agent_id, info in self._registry.items():
            name_match = (
                query_lower in info.get("name", "").lower()
                if "name" in search_in
                else False
            )
            tags_match = (
                any(query_lower in tag.lower() for tag in info.get("tags", []))
                if "tags" in search_in
                else False
            )
            if name_match or tags_match:
                matching.append(
                    AgentInfo(
                        agent_id=agent_id,
                        name=info["name"],
                        capabilities=info.get("capabilities", {}),
                        endpoint=info.get("endpoint", ""),
                        last_seen=info.get("last_seen", 0),
                        tags=info.get("tags", []),
                    )
                )
        return matching


@dataclass
class AgentInfo:
    """Information about a registered agent."""
    agent_id: str
    name: str
    capabilities: dict[str, Any] = field(default_factory=dict)
    endpoint: str = ""  # URL or identifier for the agent
    last_seen: float = field(default_factory=lambda: __import__("time").time())
    tags: list[str] = field(default_factory=list)


def get_registry() -> AgentRegistry:
    """Get the global registry instance."""
    global _instance
    if _instance is None:
        _instance = AgentRegistry()
    return _instance