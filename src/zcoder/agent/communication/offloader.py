"""Distributed Task Offloader for Phase 17.

Enables distributed task offloading between agents using the
JSON-RPC protocol and agent registry for discovery.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from zcoder.agent.communication.protocol import Operation
from zcoder.agent.communication.registry import AgentRegistry, create_default_registry

logger = logging.getLogger(__name__)


class OffloadStatus(Enum):
    """Status of task offloading."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class OffloadResult:
    """Result of a task offload operation."""

    status: OffloadStatus
    target_agent: str
    request_id: str
    response: Any | None = None
    error: str | None = None
    latency_ms: float = 0.0


class TaskOffloader:
    """Manages distributed task offloading between agents."""

    def __init__(self, registry: AgentRegistry | None = None) -> None:
        self.registry = registry or create_default_registry()
        self._pending: dict[str, any] = {}
        self._timeout = 30.0

    def set_timeout(self, seconds: float) -> None:
        """Set the timeout for offload operations."""
        self._timeout = seconds

    async def offload(
        self,
        target: str,
        operation: Operation,
        payload: dict[str, Any],
        timeout: float | None = None,
    ) -> OffloadResult:
        """Offload a task to another agent.

        Args:
            target: Target agent identifier
            operation: The operation to perform
            payload: The operation payload
            timeout: Optional timeout in seconds

        Returns:
            OffloadResult with the operation result
        """
        raise NotImplementedError("Subclasses must implement offload")

    def register_agent(self, agent_id: str, capabilities: list[str]) -> None:
        """Register an agent with the registry."""
        self.registry.register(agent_id, capabilities)

    def unregister_agent(self, agent_id: str) -> None:
        """Unregister an agent from the registry."""
        self.registry.unregister(agent_id)

    def get_agents_by_capability(self, capability: str) -> list[str]:
        """Get agents that have a specific capability."""
        return self.registry.get_by_capability(capability)

    def get_metrics(self) -> dict[str, Any]:
        """Get offloader metrics."""
        return {
            "pending_tasks": len(self._pending),
            "timeout": self._timeout,
        }
