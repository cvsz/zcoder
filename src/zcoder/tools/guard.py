"""
zcoder.tools.guard — Guarded tool execution with timeout and loop protection.

Provides:
- GuardedToolExecutor — wraps tool execution with timeout and loop guards
- LoopGuard — prevents infinite tool call loops
- TimeoutGuard — enforces per-call timeouts

Follows: Guarded Execution (deepseek-harness guard/ package).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

from zcoder.tools.definition import ToolError, ToolProtocol
from zcoder.tools.types import ToolContext, ToolOutput, ToolResult


@dataclass
class LoopGuard:
    """Prevents infinite tool call loops.

    Tracks the number of tool calls per turn and per session. When the
    limit is exceeded, raises ToolError to break the loop.
    """

    max_calls_per_turn: int = 40
    max_calls_per_session: int = 400

    def __post_init__(self) -> None:
        self._turn_calls: int = 0
        self._session_calls: int = 0
        self._turn_started: bool = False

    def start_turn(self) -> None:
        """Start a new turn, resetting the per-turn counter."""
        self._turn_calls = 0
        self._turn_started = True

    def record_call(self) -> None:
        """Record one tool call. Raises ToolError if limits are exceeded."""
        if not self._turn_started:
            self.start_turn()
        self._turn_calls += 1
        self._session_calls += 1

        if self._turn_calls > self.max_calls_per_turn:
            raise ToolError(
                f"Tool call limit exceeded: {self._turn_calls} calls in this turn "
                f"(max {self.max_calls_per_turn})",
                details={"turn_calls": self._turn_calls, "max_per_turn": self.max_calls_per_turn},
            )
        if self._session_calls > self.max_calls_per_session:
            raise ToolError(
                f"Session tool call limit exceeded: {self._session_calls} calls "
                f"(max {self.max_calls_per_session})",
                details={"session_calls": self._session_calls, "max_per_session": self.max_calls_per_session},
            )

    @property
    def turn_calls(self) -> int:
        return self._turn_calls

    @property
    def session_calls(self) -> int:
        return self._session_calls


@dataclass
class TimeoutGuard:
    """Enforces per-call timeouts for tool execution."""

    default_timeout: float = 30.0

    async def run_with_timeout(self, coro: Any, timeout: float | None = None) -> Any:
        """Run a coroutine with a timeout.

        @param coro - coroutine to run
        @param timeout - timeout in seconds (uses default if None)
        @returns the coroutine result
        @raises ToolError on timeout
        """
        timeout = timeout or self.default_timeout
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except TimeoutError as exc:
            raise ToolError(
                f"Tool execution timed out after {timeout}s",
                details={"timeout": timeout},
            ) from exc


class GuardedToolExecutor:
    """Wraps tool execution with loop and timeout guards."""

    def __init__(
        self,
        loop_guard: LoopGuard | None = None,
        timeout_guard: TimeoutGuard | None = None,
    ) -> None:
        self._loop_guard = loop_guard or LoopGuard()
        self._timeout_guard = timeout_guard or TimeoutGuard()

    def start_turn(self) -> None:
        """Start a new turn (resets loop guard)."""
        self._loop_guard.start_turn()

    async def execute(
        self,
        tool: ToolProtocol,
        context: ToolContext,
        params: dict[str, Any],
        timeout: float | None = None,
    ) -> ToolResult:
        """Execute a tool with guards applied.

        @param tool - tool implementation conforming to ToolProtocol
        @param context - tool execution context
        @param params - tool parameters
        @param timeout - optional per-call timeout override
        @returns typed ToolResult
        """
        self._loop_guard.record_call()

        start_time = time.monotonic()
        try:
            result = await self._timeout_guard.run_with_timeout(
                tool.execute(context, params), timeout=timeout
            )
            elapsed = time.monotonic() - start_time

            if isinstance(result, ToolResult):
                result.metadata = {
                    **result.metadata,
                    "elapsed_ms": round(elapsed * 1000, 2),
                    "tool": tool.name,
                }
                return result

            # Wrap plain output in ToolResult
            if isinstance(result, ToolOutput):
                return ToolResult(
                    success=True,
                    output=result,
                    metadata={"elapsed_ms": round(elapsed * 1000, 2), "tool": tool.name},
                )
            return ToolResult(
                success=True,
                output=ToolOutput(text=str(result), diff=None),
                metadata={"elapsed_ms": round(elapsed * 1000, 2), "tool": tool.name},
            )

        except ToolError as exc:
            elapsed = time.monotonic() - start_time
            return ToolResult(
                success=False,
                output=ToolOutput(text="", diff=None),
                error=str(exc),
                metadata={
                    "elapsed_ms": round(elapsed * 1000, 2),
                    "tool": tool.name,
                    "error_type": "ToolError",
                },
            )
        except Exception as exc:
            elapsed = time.monotonic() - start_time
            return ToolResult(
                success=False,
                output=ToolOutput(text="", diff=None),
                error=str(exc),
                metadata={
                    "elapsed_ms": round(elapsed * 1000, 2),
                    "tool": tool.name,
                    "error_type": type(exc).__name__,
                },
            )

    @property
    def loop_guard(self) -> LoopGuard:
        return self._loop_guard

    @property
    def timeout_guard(self) -> TimeoutGuard:
        return self._timeout_guard


__all__ = [
    "LoopGuard",
    "TimeoutGuard",
    "GuardedToolExecutor",
]
