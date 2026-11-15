"""
ollama.py — Ollama provider adapter (Phase 2).
"""

from __future__ import annotations

from typing import Any

from .adapter import ProviderAdapter, ProviderResult


class OllamaAdapter(ProviderAdapter):
    """Adapter for the Ollama chat API."""

    @classmethod
    def provider_id(cls) -> str:
        return "ollama"

    def build_payload(
        self,
        model: str,
        messages: list[dict[str, Any]],
        system: str | None,
        max_tokens: int,
        sampling: dict[str, Any],
    ) -> dict[str, Any]:
        ollama_messages: list[dict[str, Any]] = []
        if system:
            ollama_messages.append({"role": "system", "content": system})
        ollama_messages.extend(messages)
        payload: dict[str, Any] = {
            "model": model,
            "messages": ollama_messages,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        if sampling.get("temperature") is not None:
            payload["options"]["temperature"] = sampling["temperature"]
        if sampling.get("top_p") is not None:
            payload["options"]["top_p"] = sampling["top_p"]
        return payload

    def parse_response(self, data: dict[str, Any]) -> str:
        msg = data.get("message", {})
        if isinstance(msg, dict) and "content" in msg:
            return msg.get("content", "") or ""
        return data.get("response", "") or ""

    def endpoint_for(self, base_url: str, model: str) -> str:
        return f"{base_url}/api/chat"

    def headers_for(self, api_key: str) -> dict[str, str]:
        return {}
