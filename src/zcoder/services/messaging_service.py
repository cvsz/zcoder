"""Bounded application boundary for one-turn core messaging.

This service is intentionally provider-agnostic.  It coordinates exactly one
injected messaging capability call per invocation and does not own polling,
retry, scheduling, or tool execution.  Provider-specific streaming and parsing
remain behind the injected capability.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class MessagingCapability(Protocol):
    """Minimal provider capability required by the messaging service."""

    def stream_with_tools(
        self,
        prompt: str,
        tools: list[dict[str, Any]],
        system: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class MessagingTurnResult:
    """Provider-neutral result for one bounded messaging turn."""

    text: str
    tool_calls: tuple[dict[str, Any], ...]
    stop_reason: str | None
    stop_details: Any = None


def run_messaging_turn_once(
    capability: MessagingCapability,
    prompt: str,
    *,
    tools: list[dict[str, Any]] | None = None,
    system: str | None = None,
) -> MessagingTurnResult:
    """Run exactly one provider messaging turn.

    Tool calls are returned as data only.  This boundary never executes tools,
    retries a provider call, sleeps, polls, or schedules follow-up work.  Raw
    malformed streamed tool input remains owned by the provider capability and
    is preserved in the returned tool-call dictionaries for caller validation.
    """

    response = capability.stream_with_tools(
        prompt,
        tools=list(tools or []),
        system=system,
        verbose=False,
    )
    return MessagingTurnResult(
        text=str(response.get("text", "")),
        tool_calls=tuple(response.get("tool_calls") or ()),
        stop_reason=response.get("stop_reason"),
        stop_details=response.get("stop_details"),
    )
