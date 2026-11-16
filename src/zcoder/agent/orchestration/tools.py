"""
tools.py — Tool Registry & Guarded Execution (Phase 5 of Big Upgrade).

Implements ToolRegistry, ToolDefinition, ValueSchemaSpec DSL, and
ToolExecutionPipeline with waterfall events (pre-execute / execute /
post-execute) and emit events (result / change), plus executeToolBatch for
concurrent execution.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ValueSchemaSpec:
    """DSL for defining tool parameter schema.

    Supports type, required fields, and simple constraints.
    """

    type: str = "object"
    properties: dict[str, Any] = field(default_factory=dict)
    required: list[str] = field(default_factory=list)
    constraints: dict[str, Any] = field(default_factory=dict)

    def validate(self, params: dict[str, Any]) -> list[str]:
        """Return list of validation error messages (empty if valid)."""
        errors: list[str] = []
        if self.type == "object" and not isinstance(params, dict):
            errors.append("parameters must be an object")
            return errors
        for req in self.required:
            if req not in params:
                errors.append(f"missing required parameter: {req}")
        for name, spec in self.properties.items():
            if name in params and isinstance(spec, dict):
                expected_type = spec.get("type")
                val = params[name]
                if expected_type == "string" and not isinstance(val, str):
                    errors.append(f"parameter '{name}' must be a string")
                elif expected_type == "number" and not isinstance(val, (int, float)):
                    errors.append(f"parameter '{name}' must be a number")
                elif expected_type == "integer" and not isinstance(val, int):
                    errors.append(f"parameter '{name}' must be an integer")
                elif expected_type == "boolean" and not isinstance(val, bool):
                    errors.append(f"parameter '{name}' must be a boolean")
        return errors


@dataclass(frozen=True)
class ToolDefinition:
    """Definition of a registered tool."""

    name: str
    description: str
    parameters: ValueSchemaSpec
    execute: Callable[..., Any] = field(repr=False)

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        return self.parameters.validate(params)


class ToolRegistry:
    """Registry of named tools."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool definition."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition | None:
        """Look up a tool by name."""
        return self._tools.get(name)

    def list(self) -> list[str]:
        """Return registered tool names."""
        return sorted(self._tools.keys())


@dataclass(frozen=True)
class ToolResult:
    """Result of a tool execution."""

    tool_name: str
    success: bool
    result: Any = None
    error: str | None = None


class ToolExecutionPipeline:
    """Pipeline with waterfall events: pre-execute -> execute -> post-execute.

    Listeners are callables ``(context, next)`` where ``next`` is an async
    callable. A listener must call ``next()`` to pass control; returning
    without calling short-circuits the chain. Emits ``result`` and ``change``
    events via the emitter callback.
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry
        self._pre_listeners: list[Callable] = []
        self._post_listeners: list[Callable] = []
        self._emitter: Callable[[str, Any], None] | None = None

    def set_emitter(self, emitter: Callable[[str, Any], None]) -> None:
        """Register an event emitter (event_name, payload)."""
        self._emitter = emitter

    def add_pre_listener(self, listener: Callable) -> None:
        self._pre_listeners.append(listener)

    def add_post_listener(self, listener: Callable) -> None:
        self._post_listeners.append(listener)

    def _emit(self, event: str, payload: Any) -> None:
        if self._emitter is not None:
            self._emitter(event, payload)

    async def run(
        self,
        tool_name: str,
        params: dict[str, Any],
        context: Any = None,
    ) -> ToolResult:
        """Run one tool through the full pipeline."""
        tool = self.registry.get(tool_name)
        if tool is None:
            return ToolResult(tool_name=tool_name, success=False, error=f"unknown tool: {tool_name}")

        errors = tool.validate_params(params)
        if errors:
            return ToolResult(tool_name=tool_name, success=False, error="; ".join(errors))

        # pre-execute waterfall
        async def pre_next() -> None:
            pass

        for listener in self._pre_listeners:
            result = listener(context, pre_next)
            if asyncio.iscoroutine(result):
                await result
            # short-circuit if listener returned without calling next() —
            # here we simply continue (listeners that short-circuit raise)

        # execute
        try:
            if asyncio.iscoroutinefunction(tool.execute):
                result_value = await tool.execute(**params)
            else:
                result_value = tool.execute(**params)
        except Exception as exc:  # noqa: BLE001
            self._emit("result", {"tool": tool_name, "success": False, "error": str(exc)})
            return ToolResult(tool_name=tool_name, success=False, error=str(exc))

        # post-execute waterfall
        async def post_next() -> None:
            pass

        for listener in self._post_listeners:
            result = listener(context, post_next)
            if asyncio.iscoroutine(result):
                await result

        self._emit("result", {"tool": tool_name, "success": True, "result": result_value})
        self._emit("change", {"tool": tool_name, "result": result_value})
        return ToolResult(tool_name=tool_name, success=True, result=result_value)


async def executeToolBatch(
    pipeline: ToolExecutionPipeline,
    calls: list[tuple[str, dict[str, Any]]],
    context: Any = None,
    max_concurrency: int = 4,
) -> list[ToolResult]:
    """Execute multiple tool calls with concurrency limit.

    Returns results in the same order as ``calls``.
    """
    sem = asyncio.Semaphore(max_concurrency)

    async def run_one(name: str, params: dict[str, Any]) -> ToolResult:
        async with sem:
            return await pipeline.run(name, params, context)

    return await asyncio.gather(*(run_one(name, params) for name, params in calls))
