"""
openai_compatible.py — OpenAI-compatible provider adapter (Phase 2).

Handles xai, groq, openrouter, cerebras, nvidia, openai_compatible.
"""

from __future__ import annotations

from typing import Any

from .adapter import ProviderAdapter, ProviderResult


class OpenAICompatibleAdapter(ProviderAdapter):
    """Adapter for OpenAI-compatible chat/completions endpoints."""

    @classmethod
    def provider_id(cls) -> str:
        return "openai_compatible"

    def build_payload(
        self,
        model: str,
        messages: list[dict[str, Any]],
        system: str | None,
        max_tokens: int,
        sampling: dict[str, Any],
    ) -> dict[str, Any]:
        xai_messages: list[dict[str, Any]] = []
        if system:
            xai_messages.append({"role": "system", "content": system})
        xai_messages.extend(messages)
        payload: dict[str, Any] = {
            "model": model,
            "messages": xai_messages,
            "max_tokens": max_tokens,
        }
        if sampling:
            payload.update(sampling)
        return payload

    def parse_response(self, data: dict[str, Any]) -> str:
        choices = data.get("choices", [])
        if choices:
            msg = choices[0].get("message", {})
            content = msg.get("content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return "".join(p.get("text", "") for p in content if isinstance(p, dict))
        return ""

    def endpoint_for(self, base_url: str, model: str) -> str:
        return f"{base_url}/chat/completions"

    def headers_for(self, api_key: str) -> dict[str, str]:
        headers: dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

