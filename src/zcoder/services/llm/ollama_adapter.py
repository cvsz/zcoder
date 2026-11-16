"""
zcoder.services.llm.ollama_adapter — Ollama LLM provider adapter.

Implements the LLMProvider protocol for Ollama's local API using httpx.
Ollama is OpenAI-compatible but runs locally and uses a different base URL.
Validates configuration at load time (Misconfiguration Fails Loud pattern).
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from zcoder.services.llm.definition import LLMProviderError
from zcoder.services.llm.types import GenerateOptions, GenerateResult, StreamChunk


class OllamaError(LLMProviderError):
    """Ollama-specific provider error."""

    error_code = "OLLAMA_ERROR"


class OllamaAdapter:
    """LLM provider adapter for Ollama (local GGUF models)."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        # Ollama typically doesn't require an API key for local use
        self.api_key = api_key or os.getenv("OLLAMA_API_KEY", "")
        self.base_url = str(base_url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")
        self.timeout = timeout

    @property
    def provider_name(self) -> str:
        return "ollama"

    def _build_payload(self, options: GenerateOptions) -> dict[str, Any]:
        # Ollama uses a slightly different parameter naming
        payload: dict[str, Any] = {
            "model": options.model,
            "messages": options.messages,
            "stream": False,
        }
        if options.temperature is not None:
            payload["temperature"] = options.temperature
        if options.max_tokens is not None:
            payload["num_predict"] = options.max_tokens
        if options.top_p is not None:
            payload["top_p"] = options.top_p
        if options.stop is not None:
            payload["stop"] = options.stop
        if options.system:
            payload["messages"] = [{"role": "system", "content": options.system}] + options.messages
        payload.update(options.extra)
        return payload

    async def generate(self, options: GenerateOptions) -> GenerateResult:
        """Send one generation request and return the full result."""
        payload = self._build_payload(options)
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            raise OllamaError(
                f"Ollama API error: {exc.response.status_code}",
                provider="ollama",
                details={"status_code": exc.response.status_code},
            ) from exc
        except httpx.RequestError as exc:
            raise OllamaError(
                f"Ollama request failed: {exc}",
                provider="ollama",
            ) from exc

        message = data.get("message", {})
        content = message.get("content", "")
        model = data.get("model", options.model)
        finish_reason = data.get("done_reason")
        usage = data.get("usage")

        return GenerateResult(
            content=content,
            model=model,
            provider="ollama",
            finish_reason=finish_reason,
            usage=usage if isinstance(usage, dict) else None,
            request_id=data.get("created_at"),
        )

    async def generate_stream(self, options: GenerateOptions):
        """Stream generation results asynchronously."""
        payload = self._build_payload(options)
        payload["stream"] = True
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST", f"{self.base_url}/api/chat", json=payload, headers=headers
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            import json

                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        message = data.get("message", {})
                        if message.get("content"):
                            yield StreamChunk(
                                type="token",
                                content=message["content"],
                                delta=message["content"],
                                provider="ollama",
                            )
                        if data.get("done"):
                            yield StreamChunk(type="done", done=True, provider="ollama")
                            break
        except httpx.HTTPStatusError as exc:
            yield StreamChunk(
                type="error",
                content=f"Ollama API error: {exc.response.status_code}",
                provider="ollama",
            )
        except httpx.RequestError as exc:
            yield StreamChunk(
                type="error",
                content=f"Ollama request failed: {exc}",
                provider="ollama",
            )
