"""
zcoder.services.llm.definition — LLM service protocol (Service Definition).

Defines the capability seam between model consumers and provider adapters.
Consumers depend on this Protocol, not on any concrete adapter — enabling
provider swaps without touching consumer code (Capability Seam pattern,
deepseek-harness Section 4.1).

Adapter implementations are registered as effects at plugin load time
(Registrations Are Effects pattern, Section 4.2).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from zcoder.services.llm.types import GenerateOptions, GenerateResult


@runtime_checkable
class LLMProvider(Protocol):
    """Service Definition for an LLM provider adapter.

    All providers must implement this protocol. Consumers call ``generate``
    with typed options and receive a typed result — the underlying transport
    (HTTP, SSE, stdio, etc.) is hidden behind the seam.
    """

    @property
    def provider_name(self) -> str:
        """Human-readable provider identifier (e.g. ``"deepseek"``)."""

    async def generate(self, options: GenerateOptions) -> GenerateResult:
        """Send one generation request and return the full result.

        @param options - typed generation parameters including model,
            messages, temperature, max_tokens, etc.
        @returns the parsed generation result (content, usage, finish_reason).
        @raises LLMProviderError on transport, auth, or model errors.
        """

    async def generate_stream(self, options: GenerateOptions):
        """Stream generation results asynchronously.

        Yields stream chunks (token deltas, errors, done markers). The exact
        chunk type is defined by the adapter but should be compatible with
        :class:`zcoder.services.llm.types.StreamChunk`.
        """


class LLMProviderError(Exception):
    """Base error for all LLM provider operations."""

    error_code = "LLM_PROVIDER_ERROR"
    RETRYABLE = False

    def __init__(self, message: str, *, provider: str | None = None, details: dict | None = None) -> None:
        super().__init__(message)
        self.provider = provider
        self.details = details or {}
