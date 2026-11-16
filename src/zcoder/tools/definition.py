"""zcoder.tools.definition — Tool protocol (Service Definition).

Defines the capability seam between tool consumers and tool implementations.
Consumers depend on this Protocol, not on any concrete tool — enabling tool
swaps without touching consumer code (Capability Seam pattern, Section 4.1).

Tool registrations are effects (Registrations Are Effects, Section 4.2).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from zcoder.tools.types import ToolContext, ToolResult


@runtime_checkable
class ToolProtocol(Protocol):
    """Service Definition for a tool.

    All tools must implement this protocol. Consumers call ``execute`` with
    typed context and parameters and receive a typed result.
    """

    @property
    def name(self) -> str:
        """Unique tool name (e.g. ``"read"``, ``"write"``, ``"bash"``)."""

    @property
    def description(self) -> str:
        """Human-readable description of what the tool does."""

    @property
    def parameters(self) -> dict[str, Any]:
        """JSON Schema for tool parameters."""

    @property
    def category(self) -> str:
        """Tool category: ``read``, ``edit``, ``exec``, ``meta``, ``plan``."""

    async def execute(self, context: ToolContext, params: dict[str, Any]) -> ToolResult:
        """Execute the tool with the given context and parameters.

        @param context - tool execution context (workspace, cancellation,
            permissions, etc.)
        @param params - tool parameters matching the JSON Schema
        @returns typed tool result (output, diff, metadata)
        @raises ToolError on execution failure
        """


class ToolError(Exception):
    """Base error for all tool operations."""

    error_code = "TOOL_ERROR"
    RETRYABLE = False

    def __init__(self, message: str, *, tool: str | None = None, details: dict | None = None) -> None:
        super().__init__(message)
        self.tool = tool
        self.details = details or {}
