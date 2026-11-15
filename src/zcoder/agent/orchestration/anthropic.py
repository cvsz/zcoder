"""
anthropic.py — Anthropic provider adapter (Phase 2).
"""

from __future__ import annotations

from typing import Any

from .adapter import ProviderAdapter, ProviderResult


class AnthropicAdapter(ProviderAdapter):
    """Adapter for the Anthropic Messages API."""

    @classmethod
    def provider_id(cls) -> str:
        return "anthropic"

    def build_payload(
        self,
        model: str,
        messages: list[dict[str, Any]],
        system: str | None,
        max_tokens: int,
        sampling: dict[str, Any],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            payload["system"] = system
        payload.update(sampling)
        return payload

    def parse_response(self, data: dict[str, Any]) -> str:
        return "".join(
            b.get("text", "")
            for b in data.get("content", [])
            if b.get("type") == "text"
        )

    def endpoint_for(self, base_url: str, model: str) -> str:
        return f"{base_url}/v1/messages"

    def headers_for(self, api_key: str) -> dict[str, str]:
        headers: dict[str, str] = {}
        if api_key:
            headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
        return headers
