"""
zcoder.tools.types — Typed data structures for tool execution.

Defines ToolContext (input context), ToolOutput (raw output), and ToolResult
(typed result) used across all tool implementations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolContext:
    """Execution context for a tool call.

    Carries workspace, cancellation, permissions, and ambient services
    needed by tool implementations.
    """

    workspace: Any = None
    todos: list[dict[str, Any]] = field(default_factory=list)
    cancel_event: Any = None  # threading.Event or asyncio.Event
    scrub_env: bool = True
    pass_env: tuple[str, ...] = ()
    agent_llm: Any = None
    agent_policy: Any = None
    agent_registry: Any = None
    agent_mcp: Any = None
    agent_skills: Any = None


@dataclass(frozen=True)
class ToolOutput:
    """Raw tool output."""

    text: str
    diff: str | None = None


@dataclass(frozen=True)
class ToolResult:
    """Typed tool execution result.

    ``success`` indicates whether the tool completed successfully.
    ``output`` contains the raw output. ``metadata`` carries tool-specific
    metadata (e.g. execution time, token count).
    """

    success: bool
    output: ToolOutput | str
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
