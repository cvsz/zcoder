"""
Agent discovery registry for Phase 17.

Provides agent discovery and registry service for distributed agent systems.
Supports local agent registration, capability tracking, and keyword search.

Persistence
-----------
Registrations are stored as JSON on disk (default
``~/.zcoder/agent_registry/agents.json``, overridable per instance). Writes
are atomic (write-to-temp + ``os.replace``) so a crash cannot corrupt the
registry, and malformed on-disk payloads are quarantined to
``agents.json.corrupt`` instead of being silently discarded.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

AGENT_REGISTRY_DIR = Path.home() / ".zcoder" / "agent_registry"
REGISTRY_FILE = AGENT_REGISTRY_DIR / "agents.json"


@dataclass
class AgentInfo:
    """Information about a registered agent."""

    agent_id: str
    name: str
    capabilities: dict[str, Any] = field(default_factory=dict)
    endpoint: str = ""  # URL or identifier for the agent
    last_seen: float = field(default_factory=time.time)
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.agent_id, str) or not self.agent_id.strip():
            raise ValueError("agent_id must be a non-empty string")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be a non-empty string")
        if not isinstance(self.capabilities, dict):
            self.capabilities = {str(c): True for c in self.capabilities}
        if isinstance(self.tags, dict):  # tolerate legacy dict-of-tags payloads
            self.tags = list(self.tags)
        else:
            self.tags = [str(t) for t in (self.tags or [])]
        self.last_seen = float(self.last_seen)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the on-disk representation."""
        return {
            "name": self.name,
            "capabilities": self.capabilities,
            "endpoint": self.endpoint,
            "last_seen": self.last_seen,
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, agent_id: str, data: dict[str, Any]) -> AgentInfo:
        """Rehydrate an AgentInfo from its on-disk representation."""
        if not isinstance(data, dict):
            raise ValueError(f"registry entry for {agent_id!r} must be a mapping")
        return cls(
            agent_id=agent_id,
            name=str(data.get("name", agent_id)),
            capabilities=data.get("capabilities", {}),
            endpoint=str(data.get("endpoint", "")),
            last_seen=data.get("last_seen", time.time()),
            tags=data.get("tags", []),
        )


class AgentRegistry:
    """Agent discovery registry with disk persistence and atomic writes."""

    def __init__(self, storage_path: Path | str | None = None) -> None:
        """Initialize the registry, loading from disk if present.

        Args:
            storage_path: Optional explicit registry file path. Defaults to
                ``REGISTRY_FILE`` (``~/.zcoder/agent_registry/agents.json``).
        """
        self._path = Path(storage_path) if storage_path is not None else REGISTRY_FILE
        self._lock = threading.Lock()
        self._registry: dict[str, dict[str, Any]] = self._load()

    @property
    def path(self) -> Path:
        """Return the on-disk file backing this registry."""
        return self._path

    def _load(self) -> dict[str, dict[str, Any]]:
        """Load the registry from disk, quarantining corrupt payloads."""
        if not self._path.exists():
            return {}
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            corrupt = self._path.with_suffix(self._path.suffix + ".corrupt")
            try:
                os.replace(self._path, corrupt)
            except OSError:
                pass
            return {}
        if not isinstance(data, dict):
            corrupt = self._path.with_suffix(self._path.suffix + ".corrupt")
            try:
                os.replace(self._path, corrupt)
            except OSError:
                pass
            return {}
        return dict(data)

    def _save_locked(self) -> None:
        """Persist the registry atomically. Caller must hold ``self._lock``."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=self._path.name + ".", suffix=".tmp", dir=self._path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._registry, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self._path)
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def reload(self) -> None:
        """Re-read the registry from disk, discarding in-memory state."""
        with self._lock:
            self._registry = self._load()

    def register_agent(self, agent: AgentInfo) -> None:
        """Register or re-register an agent (upsert by agent_id)."""
        with self._lock:
            self._registry[agent.agent_id] = agent.to_dict()
            self._save_locked()

    def unregister_agent(self, agent_id: str) -> bool:
        """Unregister an agent. Returns True if it was present."""
        with self._lock:
            if agent_id not in self._registry:
                return False
            del self._registry[agent_id]
            self._save_locked()
            return True

    def get_agent(self, agent_id: str) -> AgentInfo | None:
        """Get information about a specific agent, or None if missing."""
        with self._lock:
            info = self._registry.get(agent_id)
            if info is None:
                return None
        try:
            return AgentInfo.from_dict(agent_id, info)
        except ValueError:
            return None

    def heartbeat(self, agent_id: str) -> AgentInfo | None:
        """Update ``last_seen`` for a registered agent and return it."""
        with self._lock:
            info = self._registry.get(agent_id)
            if info is None:
                return None
            info["last_seen"] = time.time()
            self._save_locked()
        return self.get_agent(agent_id)

    def list_agents(self) -> list[AgentInfo]:
        """List all registered agents."""
        with self._lock:
            items = list(self._registry.items())
        agents: list[AgentInfo] = []
        for agent_id, info in items:
            try:
                agents.append(AgentInfo.from_dict(agent_id, info))
            except ValueError:
                continue
        return agents

    def find_agents_by_capability(self, capability: str, tag: str | None = None) -> list[AgentInfo]:
        """Find agents that advertise ``capability``, optionally narrowed by tag.

        An agent matches iff it advertises ``capability`` (as a key in its
        capabilities mapping) and, when ``tag`` is given, also carries that
        tag. Capability matching is exact on keys and on boolean capability
        values (``False`` disables a capability).
        """
        capability = capability.lower()
        matching: list[AgentInfo] = []
        for agent in self.list_agents():
            cap_value = next((v for k, v in agent.capabilities.items() if str(k).lower() == capability), None)
            has_cap = cap_value is not None and cap_value is not False
            if not has_cap:
                continue
            if tag is not None and tag not in agent.tags:
                continue
            matching.append(agent)
        return matching

    def search_agents(self, query: str, search_in: list[str] | None = None) -> list[AgentInfo]:
        """Search for agents by name or tags (case-insensitive substring)."""
        if search_in is None:
            search_in = ["name", "tags"]

        query_lower = query.lower()
        matching: list[AgentInfo] = []
        for agent in self.list_agents():
            name_match = "name" in search_in and query_lower in agent.name.lower()
            tags_match = "tags" in search_in and any(query_lower in t.lower() for t in agent.tags)
            capabilities_match = "capabilities" in search_in and any(
                query_lower in str(k).lower() for k in agent.capabilities
            )
            if name_match or tags_match or capabilities_match:
                matching.append(agent)
        return matching

    def clear(self) -> None:
        """Remove every registered agent from disk and memory."""
        with self._lock:
            self._registry = {}
            self._save_locked()


_instance: AgentRegistry | None = None
_instance_lock = threading.Lock()


def get_registry() -> AgentRegistry:
    """Get the global registry instance (thread-safe)."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = AgentRegistry()
    return _instance


__all__ = ["AGENT_REGISTRY_DIR", "REGISTRY_FILE", "AgentInfo", "AgentRegistry", "get_registry"]
