"""
zcoder.services.llm.streaming — Async streaming service for LLM providers.

Wraps LLMProvider adapters with AbortSignal support (Phase 3 of Big Upgrade).
Provides:
- StreamableLLMProvider — adapter wrapper that honors AbortSignal
- collect_stream — helper to consume a stream into a full GenerateResult
- stream_to_session — helper to log stream chunks as session events
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from zcoder.agent.orchestration.cancellation import AbortSignal
from zcoder.services.llm.definition import LLMProvider
from zcoder.services.llm.types import GenerateOptions, GenerateResult, StreamChunk


class StreamableLLMProvider:
    """Wraps an LLMProvider with AbortSignal support.

    Provides generate_stream() that checks the abort signal between chunks
    and stops yielding when cancelled.
    """

    def __init__(self, provider: LLMProvider, abort_signal: AbortSignal) -> None:
        self._provider = provider
        self._abort_signal = abort_signal

    @property
    def provider_name(self) -> str:
        return self._provider.provider_name

    async def generate(self, options: GenerateOptions) -> GenerateResult:
        """Delegate to the wrapped provider's generate()."""
        return await self._provider.generate(options)

    async def generate_stream(self, options: GenerateOptions) -> AsyncIterator[StreamChunk]:
        """Stream generation results, honoring the abort signal.

        Yields StreamChunk items from the wrapped provider. After each chunk,
        checks the abort signal — if aborted, yields a final ``done`` chunk
        and stops.
        """
        async for chunk in self._provider.generate_stream(options):
            yield chunk
            if self._abort_signal.aborted:
                yield StreamChunk(
                    type="done",
                    content="",
                    done=True,
                    provider=self.provider_name,
                    extra={"aborted": True},
                )
                return
            if chunk.done:
                return

    def check_aborted(self) -> None:
        """Raise asyncio.CancelledError if the abort signal is set."""
        self._abort_signal.check()


async def collect_stream(
    stream: AsyncIterator[StreamChunk],
) -> GenerateResult:
    """Consume a stream of StreamChunk items into a single GenerateResult.

    Concatenates token deltas and captures the final done chunk's metadata.
    """
    content_parts: list[str] = []
    model: str | None = None
    provider: str | None = None
    finish_reason: str | None = None
    request_id: str | None = None
    usage: dict[str, int] | None = None
    extra: dict[str, Any] = {}

    async for chunk in stream:
        if chunk.type == "token":
            content_parts.append(chunk.delta or chunk.content)
            if chunk.model:
                model = chunk.model
            if chunk.provider:
                provider = chunk.provider
            extra.update(chunk.extra)
        elif chunk.type == "done":
            if chunk.extra:
                extra.update(chunk.extra)
            # done chunk may carry finish_reason or request_id in extra
            finish_reason = chunk.extra.get("finish_reason")
            request_id = chunk.extra.get("request_id")
            if chunk.model:
                model = chunk.model
            if chunk.provider:
                provider = chunk.provider
            break
        elif chunk.type == "error":
            raise RuntimeError(f"Stream error from {chunk.provider or 'unknown'}: {chunk.content}")

    return GenerateResult(
        content="".join(content_parts),
        model=model or "",
        provider=provider or "",
        finish_reason=finish_reason,
        usage=usage,
        request_id=request_id,
        extra=extra,
    )
