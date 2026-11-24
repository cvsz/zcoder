"""
adapter.py — Provider adapter pattern (Phase 2 of Big Upgrade).

Defines the abstract ``ProviderAdapter`` and ``ProviderResult`` that every
model provider must implement, decoupling provider-specific request/response
logic from the router.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from zcoder.core.resilience import urlopen_json


@dataclass(frozen=True)
class ProviderResult:
    """Normalised result returned by every provider adapter."""

    content: str
    raw: dict[str, Any]
    provider: str
    model: str


class ProviderAdapter(ABC):
    """Abstract base class for a model provider adapter.

    Each concrete adapter is responsible for building the provider-specific
    request payload and parsing the provider-specific response into a
    :class:`ProviderResult`.
    """

    @abstractmethod
    def build_payload(
        self,
        model: str,
        messages: list[dict[str, Any]],
        system: str | None,
        max_tokens: int,
        sampling: dict[str, Any],
    ) -> dict[str, Any]:
        """Build the provider-specific request payload."""

    @abstractmethod
    def parse_response(self, data: dict[str, Any]) -> str:
        """Parse the provider-specific response into plain text."""

    @abstractmethod
    def endpoint_for(self, base_url: str, model: str) -> str:
        """Return the full chat/completions endpoint URL for *model*."""

    @abstractmethod
    def headers_for(self, api_key: str) -> dict[str, str]:
        """Return the HTTP headers to send with the request."""

    def execute(
        self,
        *,
        base_url: str,
        model: str,
        messages: list[dict[str, Any]],
        system: str | None,
        max_tokens: int,
        sampling: dict[str, Any],
        api_key: str,
    ) -> ProviderResult:
        """Execute a single chat completion against this provider.

        Builds the provider-specific payload, performs an HTTP POST to the
        provider endpoint, parses the response, and returns a
        :class:`ProviderResult`. Subclasses may override to add
        provider-specific transport logic (e.g. retries, streaming).
        """
        payload = self.build_payload(
            model=model,
            messages=messages,
            system=system,
            max_tokens=max_tokens,
            sampling=sampling,
        )
        headers = self.headers_for(api_key=api_key)
        headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.endpoint_for(base_url, model),
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        import sys

        router = sys.modules.get("zcoder.agent.orchestration.router")
        runner = getattr(router, "urlopen_json", urlopen_json) if router is not None else urlopen_json
        raw = runner(request, timeout=300)

        content = self.parse_response(raw)
        return ProviderResult(
            content=content,
            raw=raw,
            provider=self.provider_id(),
            model=model,
        )

    @classmethod
    @abstractmethod
    def provider_id(cls) -> str:
        """Stable identifier for this provider (e.g. ``"openai_compatible"``)."""
