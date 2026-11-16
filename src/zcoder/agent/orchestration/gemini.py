"""
gemini.py — Gemini provider adapter (Phase 2).
"""

from __future__ import annotations

from typing import Any

from .adapter import ProviderAdapter


class GeminiAdapter(ProviderAdapter):
    """Adapter for the Gemini generateContent API."""

    @classmethod
    def provider_id(cls) -> str:
        return "gemini"

    def build_payload(
        self,
        model: str,
        messages: list[dict[str, Any]],
        system: str | None,
        max_tokens: int,
        sampling: dict[str, Any],
    ) -> dict[str, Any]:
        contents: list[dict[str, Any]] = []
        for m in messages:
            role = m.get("role", "user")
            if role == "assistant":
                role = "model"
            text = m.get("content", "")
            contents.append({"role": role, "parts": [{"text": text}]})
        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": max_tokens},
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        if sampling.get("temperature") is not None:
            payload["generationConfig"]["temperature"] = sampling["temperature"]
        if sampling.get("top_p") is not None:
            payload["generationConfig"]["topP"] = sampling["top_p"]
        if sampling.get("top_k") is not None:
            payload["generationConfig"]["topK"] = sampling["top_k"]
        return payload

    def parse_response(self, data: dict[str, Any]) -> str:
        candidates = data.get("candidates", [])
        if candidates:
            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            return "".join(p.get("text", "") for p in parts)
        return ""

    def endpoint_for(self, base_url: str, model: str) -> str:
        return f"{base_url}/v1beta/models/{model}:generateContent"

    def headers_for(self, api_key: str) -> dict[str, str]:
        headers: dict[str, str] = {}
        if api_key:
            headers["x-goog-api-key"] = api_key
        return headers
