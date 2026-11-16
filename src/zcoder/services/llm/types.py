"""
zcoder.services.llm.types — Typed data structures for LLM generation.

Defines GenerateOptions (input) and GenerateResult (output) used across all
provider adapters. These are plain dataclasses — no runtime validation,
consistent with the "Trust TypeScript at typed boundaries" pattern adapted
for Python (validate at parser/config/wire boundaries, not at typed interfaces).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GenerateOptions:
    """Typed generation parameters sent to a model provider.

    All fields are optional except ``model`` and ``messages``. Providers may
    ignore fields they don't support; missing fields use provider defaults.
    """

    model: str
    messages: list[dict[str, Any]]
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    top_k: int | None = None
    stream: bool = False
    system: str | None = None
    stop: list[str] | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GenerateResult:
    """Typed result returned by a provider adapter."""

    content: str
    model: str
    provider: str
    finish_reason: str | None = None
    usage: dict[str, int] | None = None
    request_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StreamChunk:
    """One chunk of a streaming model response.

    ``type`` is one of: ``"token"`` (content delta), ``"error"`` (error
    redirect), ``"done"`` (terminal).
    """

    type: str
    content: str = ""
    done: bool = False
    delta: str = ""
    model: str | None = None
    provider: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
