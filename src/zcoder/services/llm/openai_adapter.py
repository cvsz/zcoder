"""
zcoder.services.llm.openai_adapter — OpenAI-compatible LLM provider adapter.

Implements the LLMProvider protocol for OpenAI and OpenAI-compatible APIs
using httpx. Follows the Capability Seam pattern (Section 4.1).
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from zcoder.services.llm.definition import LLMProviderError
from zcoder.services.llm.types import GenerateOptions, GenerateResult, StreamChunk


class OpenAIError(LLMProviderError):
    """OpenAI-specific provider error."""

    error_code = "OPENAI_ERROR"


class OpenAIAdapter:
    """LLM provider adapter for OpenAI and OpenAI-compatible APIs."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        if not self.api_key:
            raise OpenAIError(
                "OpenAI API key is required — set OPENAI_API_KEY or pass api_key",
                provider="openai",
            )
        raw_base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1") or "https://api.openai.com/v1"
        self.base_url = raw_base_url.rstrip("/")
        self.timeout = timeout

    @property
    def provider_name(self) -> str:
        return "openai"

    async def generate(self, options: GenerateOptions) -> GenerateResult:
        """Send one generation request and return the full result."""
        payload = self._build_payload(options)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            raise OpenAIError(
                f"OpenAI API error: {exc.response.status_code}",
                provider="openai",
                details={"status_code": exc.response.status_code},
            ) from exc
        except httpx.RequestError as exc:
            raise OpenAIError(
                f"OpenAI request failed: {exc}",
                provider="openai",
            ) from exc

        content = ""
        choices = data.get("choices", [])
        if choices:
            message = choices[0].get("message", {})
            content = message.get("content", "")
        usage = data.get("usage")
        model = data.get("model", options.model)
        finish_reason = choices[0].get("finish_reason") if choices else None
        request_id = data.get("id")

        return GenerateResult(
            content=content,
            model=model,
            provider="openai",
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
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
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
                                yield StreamChunk(type="done", done=True, provider="openai")
                                continue
                            try:
                                import json

                                data = json.loads(data_str)
                            except json.JSONDecodeError:
                                continue
                            choices = data.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                content_delta = delta.get("content", "")
                                if content_delta:
                                    yield StreamChunk(
                                        type="token",
                                        content=content_delta,
                                        delta=content_delta,
                                        provider="openai",
                                    )
        except httpx.HTTPStatusError as exc:
            yield StreamChunk(
                type="error",
                content=f"OpenAI API error: {exc.response.status_code}",
                provider="openai",
            )
        except httpx.RequestError as exc:
            yield StreamChunk(
                type="error",
                content=f"OpenAI request failed: {exc}",
                provider="openai",
            )

    def _build_payload(self, options: GenerateOptions) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": options.model,
            "messages": options.messages,
            "stream": False,
        }
        if options.temperature is not None:
            payload["temperature"] = options.temperature
        if options.max_tokens is not None:
            payload["max_tokens"] = options.max_tokens
        if options.top_p is not None:
            payload["top_p"] = options.top_p
        if options.stop is not None:
            payload["stop"] = options.stop
        if options.system:
            payload["messages"] = [{"role": "system", "content": options.system}] + options.messages
        payload.update(options.extra)
        return payload
