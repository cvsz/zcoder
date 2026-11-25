"""Tool execution pipeline — mirrors deepseek-harness @deepseek-ai/dsh-tools.

Provides a complete tool execution system with:
  * ToolExecutor interface (plugin-owned argument parsing, dispatch, scheduling, cancellation, logging)
  * ToolDefinition (schema + execution function + output definition + content projection)
  * ResolvedToolSet (step-time admitted registrations with dispose/view)
  * ToolBatchInput/ToolBatchResult (batch execution with concurrency control)
  * Tool activation conditions (when())
  * Tool restrictions (allow/deny lists)
  * Tool guards (post-policy denial)
  * Tool projection (projectContent/finalizeContent)
  * Structured error types (ToolBatchExecutionError, ToolActivationError, etc.)
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

# ── Types ─────────────────────────────────────────────────────────────────────

T = TypeVar("T")  # noqa: F841 — generic type var re-exported for typed consumers

ToolCallId = str
ContentBlock = dict[str, Any]
JsonValue = Any  # noqa: F841 — type alias re-exported for typed consumers


# ── Error types ───────────────────────────────────────────────────────────────


class ToolBatchExecutionError(Exception):
    """A drained batch failed internally; only the included results are committed."""

    def __init__(self, cause: Exception, partial: ToolBatchResult):
        super().__init__("Tool batch execution failed", cause)
        self.cause = cause
        self.partial = partial
        self.name = "ToolBatchExecutionError"


class ToolExecutorUnavailableError(Exception):
    """The selected provider is missing or unloaded."""

    def __init__(self):
        super().__init__(
            "The selected tool executor is unavailable. Load an executor in this composition before running the agent."
        )
        self.code = "TOOL_EXECUTOR_UNAVAILABLE"
        self.name = "ToolExecutorUnavailableError"


class ToolActivationError(Exception):
    """Failure to determine a tool's step-time availability."""

    def __init__(self, name: str, cause: Exception):
        super().__init__(f"cannot resolve availability of tool {name!r}", cause)
        self.name = name
        self.cause = cause
        self.code = "TOOL_ACTIVATION_FAILED"


class ToolNotFoundError(Exception):
    """Thrown when the model requests a tool that isn't registered."""

    def __init__(self, tool_name: str, reachable_from: str | None = None):
        if reachable_from is None:
            msg = f"unknown tool {tool_name!r}"
        else:
            msg = f"unknown tool {tool_name!r}: {reachable_from}"
        super().__init__(msg)
        self.tool_name = tool_name
        self.code = "UNKNOWN_TOOL"


class ToolContextUnavailableError(Exception):
    """Thrown by a tool body when its composition or call lacks required context."""

    def __init__(self, message: str):
        super().__init__(message)
        self.code = "TOOL_CONTEXT_UNAVAILABLE"


class ToolOutputError(Exception):
    """Thrown when a tool body or post-policy value violates its declared output."""

    def __init__(self, tool_name: str, violations: list[str]):
        super().__init__(f"tool {tool_name!r} returned invalid output: {'; '.join(violations)}")
        self.tool_name = tool_name
        self.violations = violations
        self.code = "INVALID_TOOL_OUTPUT"


# Canonical error codes
TOOL_ABORTED = "ABORTED"
TOOL_ABORTED_BEFORE_DISPATCH = "ABORTED_BEFORE_DISPATCH"
TOOL_CONTEXT_UNAVAILABLE = "TOOL_CONTEXT_UNAVAILABLE"


# ── ToolRunContext ────────────────────────────────────────────────────────────


class ToolRunContext:
    """Runtime context handed to a tool implementation after the executor accepts
    a ToolExecution."""

    def __init__(
        self,
        call_id: ToolCallId,
        name: str,
        arguments: Any,
        signal: Any,
        agent: Any = None,
        root_call_id: ToolCallId | None = None,
    ):
        self.call_id = call_id
        self.name = name
        self.arguments = arguments
        self.signal = signal
        self.agent = agent
        self.root_call_id = root_call_id or call_id
        self._deferred_contexts: list[dict[str, Any]] = []
        self._conclude_turn = False

    def defer_context(self, context: dict[str, Any]) -> None:
        """Defer one context until this tool's final result reaches the agent loop."""
        self._deferred_contexts.append(context)

    def conclude_turn(self) -> None:
        """Mark a successful final result as terminal for the current agent turn."""
        self._conclude_turn = True

    @property
    def deferred_contexts(self) -> list[dict[str, Any]]:
        return self._deferred_contexts

    @property
    def concludes_turn(self) -> bool:
        return self._conclude_turn


# ── ToolDefinition ────────────────────────────────────────────────────────────


@dataclass
class ToolOutputDefinition:
    """Tool-owned canonical output contract."""

    schema: Any  # JSON Schema node
    render: Callable[[Any, Any], list[ContentBlock]]
    presentation_meta: Callable[[Any, Any], Any] | None = None


@dataclass
class ToolDefinition:
    """A registered tool: its schema plus the execution function."""

    name: str
    description: str
    parameters: dict[str, Any]
    output: ToolOutputDefinition
    execute: Callable[[Any, ToolRunContext], Any]
    project_content: Callable[[ToolRunContext, Any], list[ContentBlock] | None] | None = None
    finalize_content: Callable[[ToolRunContext, Any], list[ContentBlock] | None] | None = None
    timeout_ms: int | None = None
    is_concurrency_safe: Callable[[Any], bool] | None = None
    present_call: Callable[[Any], dict[str, Any] | None] | None = None
    present_result: Callable[[Any, Any], dict[str, Any] | None] | None = None


# ── ToolActivationContext / RegistrationOptions ───────────────────────────────


@dataclass
class ToolActivationContext:
    """Inputs for a tool's step-time activation condition."""

    agent: Any
    model_selection: dict[str, Any]
    signal: Any


@dataclass
class ToolRegistrationOptions:
    """Lifecycle-owned conditions for a registered tool."""

    when: Callable[[ToolActivationContext], bool | None] | None = None


# ── PreToolDecision / PostToolDecision ────────────────────────────────────────


class PreToolDecision:
    """Pre-dispatch decision."""

    def __init__(self, kind: str, reason: str = "", info: Any = None, display_reason: Any = None):
        self.kind = kind  # 'allow' | 'deny' | 'cancel' | 'ask'
        self.reason = reason
        self.info = info
        self.display_reason = display_reason


class PostToolDecision:
    """Post-dispatch decision."""

    def __init__(
        self,
        kind: str,
        content: list[ContentBlock] | None = None,
        value: Any = None,
        additional_contexts: list[dict[str, Any]] | None = None,
        feedback: list[ContentBlock] | None = None,
        info: Any = None,
    ):
        self.kind = kind  # 'accept' | 'block'
        self.content = content
        self.value = value
        self.additional_contexts = additional_contexts or []
        self.feedback = feedback
        self.info = info


# ── ToolRestriction ───────────────────────────────────────────────────────────


@dataclass
class ToolRestriction:
    """Per-scope filter over global tools."""

    allow: list[str] | None = None
    deny: list[str] | None = None


# ── ToolGuard ─────────────────────────────────────────────────────────────────

ToolGuard = Callable[[Any], str | None]


# ── ToolExecutionResult ───────────────────────────────────────────────────────


@dataclass
class ToolExecutionSuccess:
    """Successful canonical tool execution."""

    value: Any
    content: list[ContentBlock]
    meta: Any | None = None
    additional_contexts: list[dict[str, Any]] = field(default_factory=list)
    concludes_turn: bool = False


@dataclass
class ToolExecutionFailure:
    """Failed canonical tool execution."""

    error: dict[str, Any]
    content: list[ContentBlock]
    meta: Any | None = None
    additional_contexts: list[dict[str, Any]] = field(default_factory=list)


ToolExecutionResult = ToolExecutionSuccess | ToolExecutionFailure


# ── ToolBatchInput / ToolBatchResult ──────────────────────────────────────────


@dataclass
class ToolCallBlock:
    """One model-requested tool call."""

    call_id: ToolCallId
    name: str
    arguments: Any
    agent: Any = None
    tool_set: Any = None
    signal: Any = None


@dataclass
class ToolCallResult:
    """One settled result correlated with its original model call."""

    call_id: ToolCallId
    result: ToolExecutionResult


@dataclass
class ToolBatchInput:
    """Raw model calls with optional Agent ownership and model-step logging."""

    calls: list[ToolCallBlock]
    signal: Any
    max_parallel_tool_calls: int | None = None
    agent: Any = None
    tool_set: Any = None
    log: dict[str, int] | None = None  # {'turn': int, 'step': int}


@dataclass
class ToolBatchResult:
    """Model-ordered outcomes and context accepted for the next step."""

    results: list[ToolCallResult]
    additional_contexts: list[dict[str, Any]]
    concluded: bool


# ── ToolPromptSection ─────────────────────────────────────────────────────────


@dataclass
class ToolPromptSection:
    """Executor-owned guidance registered through the system-prompt section API."""

    name: str
    order: int
    interpolate: bool
    text: str | Callable[[list[ToolDefinition]], str]


# ── ToolExecutor interface ────────────────────────────────────────────────────


class ToolExecutor:
    """A plugin owns argument parsing, dispatch, scheduling, cancellation, and logging."""

    def __init__(self, sections: list[ToolPromptSection] | None = None):
        self.sections = sections or []

    def describe(self, tools: list[ToolDefinition]) -> dict[str, Any]:
        """Describe the model's callable tools."""
        schemas = []
        known_names = []
        for tool in tools:
            schemas.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                }
            )
            known_names.append(tool.name)
        return {"schemas": schemas, "known_names": known_names}

    async def execute(self, input: ToolBatchInput) -> ToolBatchResult:
        """Execute a complete batch.

        Subclasses must implement this. Returns one outcome per input call.
        """
        raise NotImplementedError("subclasses must implement execute()")


# ── ResolvedToolSet ───────────────────────────────────────────────────────────


class ResolvedToolSet:
    """One step's admitted registrations, also used by nested PTC calls."""

    def __init__(self, tools: dict[str, ToolDefinition], scope_key: Any = None):
        self._tools = tools
        self._scope_key = scope_key
        self._disposed = False

    def dispose(self) -> None:
        """Close admission after the step's tool batch settles."""
        self._disposed = True
        self._tools = {}

    def view(self, scope_key: Any = None) -> dict[str, ToolDefinition]:
        """Read admitted registrations visible in their original scope."""
        if self._disposed:
            return {}
        if scope_key is not None and scope_key != self._scope_key:
            return {}
        return dict(self._tools)


# ── Default executor implementation ───────────────────────────────────────────


class DefaultToolExecutor(ToolExecutor):
    """Default tool executor that calls tool functions directly."""

    async def execute(self, input: ToolBatchInput) -> ToolBatchResult:
        results: list[ToolCallResult] = []
        additional_contexts: list[dict[str, Any]] = []
        concluded = False

        semaphore = asyncio.Semaphore(input.max_parallel_tool_calls or 1)

        async def execute_one(call: ToolCallBlock) -> ToolCallResult:
            async with semaphore:
                if input.signal and getattr(input.signal, "aborted", False):
                    return ToolCallResult(
                        call_id=call.call_id,
                        result=ToolExecutionFailure(
                            error={"message": "aborted", "code": TOOL_ABORTED_BEFORE_DISPATCH},
                            content=[{"type": "text", "text": "Call aborted before dispatch"}],
                        ),
                    )

                # Find the tool definition
                tool_def = input.tool_set.view(input.agent) if input.tool_set else {}
                if call.name not in tool_def:
                    return ToolCallResult(
                        call_id=call.call_id,
                        result=ToolExecutionFailure(
                            error={"message": f"unknown tool {call.name!r}", "code": "UNKNOWN_TOOL"},
                            content=[{"type": "text", "text": f"Unknown tool: {call.name}"}],
                        ),
                    )

                tool = tool_def[call.name]
                exec_ctx = ToolRunContext(
                    call_id=call.call_id,
                    name=call.name,
                    arguments=call.arguments,
                    signal=call.signal or input.signal,
                    agent=input.agent,
                )

                try:
                    if asyncio.iscoroutinefunction(tool.execute):
                        value = await tool.execute(call.arguments, exec_ctx)
                    else:
                        value = tool.execute(call.arguments, exec_ctx)

                    # Apply project_content if available
                    content = [{"type": "text", "text": str(value)}]
                    if tool.project_content:
                        projected = tool.project_content(
                            exec_ctx, ToolExecutionSuccess(value=value, content=content)
                        )
                        if projected is not None:
                            content = projected

                    # Apply finalize_content if available
                    if tool.finalize_content:
                        finalized = tool.finalize_content(
                            exec_ctx, ToolExecutionSuccess(value=value, content=content)
                        )
                        if finalized is not None:
                            content = finalized

                    success = ToolExecutionSuccess(
                        value=value,
                        content=content,
                        additional_contexts=exec_ctx.deferred_contexts,
                        concludes_turn=exec_ctx.concludes_turn,
                    )
                    if exec_ctx.concludes_turn:
                        nonlocal concluded
                        concluded = True

                    return ToolCallResult(call_id=call.call_id, result=success)

                except Exception as exc:
                    failure = ToolExecutionFailure(
                        error={
                            "message": str(exc),
                            "code": getattr(exc, "code", "UNKNOWN"),
                        },
                        content=[{"type": "text", "text": str(exc)}],
                    )
                    return ToolCallResult(call_id=call.call_id, result=failure)

        # Execute all calls
        task_results = await asyncio.gather(
            *[execute_one(call) for call in input.calls], return_exceptions=True
        )

        for result in task_results:
            if isinstance(result, Exception):
                # Wrap unexpected exceptions
                results.append(
                    ToolCallResult(
                        call_id="unknown",
                        result=ToolExecutionFailure(
                            error={"message": str(result), "code": "UNKNOWN"},
                            content=[{"type": "text", "text": str(result)}],
                        ),
                    )
                )
            else:
                if isinstance(result, ToolCallResult):
                    results.append(result)
                    if isinstance(result.result, ToolExecutionSuccess):
                        additional_contexts.extend(result.result.additional_contexts)

        return ToolBatchResult(
            results=results,
            additional_contexts=additional_contexts,
            concluded=concluded,
        )


__all__ = [
    # Error types
    "ToolBatchExecutionError",
    "ToolExecutorUnavailableError",
    "ToolActivationError",
    "ToolNotFoundError",
    "ToolContextUnavailableError",
    "ToolOutputError",
    # Canonical codes
    "TOOL_ABORTED",
    "TOOL_ABORTED_BEFORE_DISPATCH",
    "TOOL_CONTEXT_UNAVAILABLE",
    # Context
    "ToolRunContext",
    # Tool definition
    "ToolOutputDefinition",
    "ToolDefinition",
    # Activation
    "ToolActivationContext",
    "ToolRegistrationOptions",
    # Decisions
    "PreToolDecision",
    "PostToolDecision",
    # Restriction / Guard
    "ToolRestriction",
    "ToolGuard",
    # Results
    "ToolExecutionSuccess",
    "ToolExecutionFailure",
    "ToolExecutionResult",
    # Batch
    "ToolCallBlock",
    "ToolCallResult",
    "ToolBatchInput",
    "ToolBatchResult",
    # Prompt section
    "ToolPromptSection",
    # Executor
    "ToolExecutor",
    "DefaultToolExecutor",
    # Resolved tool set
    "ResolvedToolSet",
]
