"""Bounded Claude caller adapter for the Upgrade-44 messaging service.

This module is deliberately narrow: one invocation constructs one existing
``StreamCoder`` capability and delegates exactly once through
``run_messaging_turn_once``.  It does not own retries, polling, scheduling,
sleep/backoff, recursive agent execution, or tool execution.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from zcoder.claude.capabilities.stream import StreamCoder
from zcoder.services.messaging_service import MessagingTurnResult, run_messaging_turn_once


def run_claude_messaging_turn_once(
    api_key: str,
    prompt: str,
    *,
    model: str = "claude-sonnet-5",
    max_tokens: int = 4096,
    tools: list[dict[str, Any]] | None = None,
    system: str | None = None,
    verbose: bool = False,
    capability_factory: Callable[..., StreamCoder] = StreamCoder,
) -> MessagingTurnResult:
    """Run one bounded Claude messaging turn through the service boundary.

    The existing ``StreamCoder.stream_with_tools`` entry point remains intact.
    Tool calls are returned as data by ``run_messaging_turn_once`` and are not
    executed here.  ``verbose`` defaults to the existing quiet application
    boundary but may be enabled explicitly by an interactive caller that must
    preserve provider streaming output.  ``capability_factory`` is injectable
    solely for deterministic regression tests; production callers use the
    existing ``StreamCoder`` class.
    """

    capability = capability_factory(api_key=api_key, model=model, max_tokens=max_tokens)
    return run_messaging_turn_once(
        capability,
        prompt,
        tools=list(tools or []),
        system=system,
        verbose=verbose,
    )
