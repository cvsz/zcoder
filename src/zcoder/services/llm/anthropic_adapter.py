"""
zcoder.services.llm.anthropic_adapter — Anthropic LLM provider adapter.

Implements the LLMProvider protocol for the Anthropic API using httpx.
Anthropic uses a different message format (no "system" role in messages array;
system is a top-level parameter) and a different response shape.
Validates configuration at load time (Misconfiguration Fails Loud pattern).
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from zcoder.services.llm.definition import LLMProviderError
from zcoder.services.llm.types import GenerateOptions, GenerateResult, StreamChunk


class AnthropicError(LLMProviderError):
    """Anthropic-specific provider error."""

    error_code = "ANTHROPIC_ERROR"


class AnthropicAdapter:
    """LLM provider adapter for Anthropic (Claude models)."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        if not self.api_key:
            raise AnthropicError(
                "Anthropic API key is required — set ANTHROPIC_API_KEY or pass api_key",
                provider="anthropic",
            )
        self.base_url = str(
            base_url or os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1")
        ).rstrip("/")
        self.timeout = timeout

    @property
    def provider_name(self) -> str:
        return "anthropic"

    def _build_payload(self, options: GenerateOptions) -> dict[str, Any]:
        # Anthropic separates system from messages
        messages = []
        system = options.system
        for msg in options.messages:
            role = msg.get("role", "user")
            if role == "system":
                if system is None:
                    system = msg.get("content", "")
                continue
            messages.append(msg)

        payload: dict[str, Any] = {
            "model": options.model,
            "messages": messages,
            "stream": False,
        }
        if system:
            payload["system"] = system
        if options.temperature is not None:
            payload["temperature"] = options.temperature
        if options.max_tokens is not None:
            payload["max_tokens"] = options.max_tokens
        if options.top_p is not None:
            payload["top_p"] = options.top_p
        if options.stop is not None:
            payload["stop_sequences"] = options.stop
        payload.update(options.extra)
        return payload

    async def generate(self, options: GenerateOptions) -> GenerateResult:
        """Send one generation request and return the full result."""
        payload = self._build_payload(options)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/messages",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            raise AnthropicError(
                f"Anthropic API error: {exc.response.status_code}",
                provider="anthropic",
                details={"status_code": exc.response.status_code},
            ) from exc
        except httpx.RequestError as exc:
            raise AnthropicError(
                f"Anthropic request failed: {exc}",
                provider="anthropic",
            ) from exc

        content = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")
        usage = data.get("usage")
        model = data.get("model", options.model)
        finish_reason = data.get("stop_reason")
        request_id = data.get("id")

        return GenerateResult(
            content=content,
            model=model,
            provider="anthropic",
            finish_reason=finish_reason,
            usage=usage if isinstance(usage, dict) else None,
            request_id=request_id,
        )

    async def generate_stream(self, options: GenerateOptions):
        """Stream generation results asynchronously."""
        payload = self._build_payload(options)
        payload["stream"] = True
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/messages",
                    json=payload,
                    headers=headers,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str.strip() == "[DONE]":
                                yield StreamChunk(type="done", done=True, provider="anthropic")
                                continue
                            try:
                                import json

                                data = json.loads(data_str)
                            except json.JSONDecodeError:
                                continue
                            event_type = data.get("type", "")
                            if event_type == "content_block_delta":
                                delta = data.get("delta", {})
                                if delta.get("type") == "text_delta":
                                    text_delta = delta.get("text", "")
                                    if text_delta:
                                        yield StreamChunk(
                                            type="token",
                                            content=text_delta,
                                            delta=text_delta,
                                            provider="anthropic",
                                        )
                            elif event_type == "message_stop":
                                yield StreamChunk(type="done", done=True, provider="anthropic")
                                break
        except httpx.HTTPStatusError as exc:
            yield StreamChunk(
                type="error",
                content=f"Anthropic API error: {exc.response.status_code}",
                provider="anthropic",
            )
        except httpx.RequestError as exc:
            yield StreamChunk(
                type="error",
                content=f"Anthropic request failed: {exc}",
                provider="anthropic",
            )
