"""
types.py — Streaming types (Phase 3 of Big Upgrade).

Defines ``StreamChunk`` for streaming model responses and ``GenerateOptions``
for typed generation parameters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class StreamChunk:
    """One chunk of a streaming model response.

    ``type`` is one of: ``"token"`` (content delta), ``"error"`` (error
    redirect), ``"done"`` (terminal). ``done`` is ``True`` only for the final
    chunk.
    """

    type: str
    content: str
    done: bool = False
    delta: str = ""
    model: str | None = None
    provider: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GenerateOptions:
    """Typed generation parameters sent to a model provider."""

    model: str
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    top_k: int | None = None
    stream: bool = False
    system: str | None = None
    messages: list[dict[str, Any]] = field(default_factory=list)
