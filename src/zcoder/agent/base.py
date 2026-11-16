"""
zcoder.agent.base — Base agent class with constructor injection.

Provides BaseAgent, an abstract base class that receives all services
through constructor injection. Concrete agents implement the abstract
run() method and register themselves as effects via the plugin system.

Capability Seam consumer pattern (deepseek-harness Section 4.1).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any

from zcoder.core.exceptions import ZCoderError


class AgentError(ZCoderError):
    """Raised when an agent operation fails."""

    error_code = "AGENT_ERROR"


class BaseAgent(ABC):
    """Abstract base class for ZCoder agents.

    All dependencies are injected through the constructor. Subclasses
    implement the abstract run() method and register themselves as
    effects via the plugin system.
    """

    def __init__(
        self,
        *,
        session_id: str,
        agent_id: str,
        services: dict[str, Any] | None = None,
    ) -> None:
        self.session_id = session_id
        self.agent_id = agent_id
        self.services = services or {}
        self.running = False
        self._interrupted = False

    @property
    def name(self) -> str:
        """Human-readable agent name."""
        return self.agent_id

    @abstractmethod
    async def run(self, prompt: str) -> AsyncGenerator[Any, None]:
        """Run one agent turn.

        @param prompt - user input
        @returns async generator of events
        """

    async def start(self) -> None:
        """Start the agent."""
        self.running = True
        self._interrupted = False

    async def stop(self) -> None:
        """Stop the agent."""
        self.running = False
        self._interrupted = True

    def interrupt(self) -> None:
        """Request interruption."""
        self._interrupted = True

    def get_service(self, name: str) -> Any:
        """Get a registered service by name."""
        if name not in self.services:
            raise AgentError(
                f"Service '{name}' not registered with agent '{self.agent_id}'",
                details={"agent": self.agent_id, "service": name},
            )
        return self.services[name]

    def register_service(self, name: str, service: Any) -> None:
        """Register a service with this agent."""
        self.services[name] = service

    def is_running(self) -> bool:
        """Return True if the agent is currently running."""
        return self.running


__all__ = [
    "BaseAgent",
    "AgentError",
]
