"""
zcoder.services.llm.gemini_adapter — Gemini LLM provider adapter.

Implements the LLMProvider protocol for Google's Generative Language API
using httpx. Gemini uses a different endpoint shape (generateContent) and
a different message format (contents array with parts).
Validates configuration at load time (Misconfiguration Fails Loud pattern).
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from zcoder.services.llm.definition import LLMProviderError
from zcoder.services.llm.types import GenerateOptions, GenerateResult, StreamChunk


class GeminiError(LLMProviderError):
    """Gemini-specific provider error."""

    error_code = "GEMINI_ERROR"


class GeminiAdapter:
    """LLM provider adapter for Google Gemini."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        if not self.api_key:
            raise GeminiError(
                "Gemini API key is required — set GEMINI_API_KEY or pass api_key",
                provider="gemini",
            )
        self.base_url = str(
            base_url or os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
        ).rstrip("/")
        self.timeout = timeout

    @property
    def provider_name(self) -> str:
        return "gemini"

    def _build_payload(self, options: GenerateOptions) -> dict[str, Any]:
        # Gemini uses "contents" with "parts" instead of "messages"
        contents = []
        system_instruction = options.system
        for msg in options.messages:
            role = msg.get("role", "user")
            if role == "system":
                if system_instruction is None:
                    system_instruction = msg.get("content", "")
                continue
            gemini_role = "model" if role == "assistant" else "user"
            parts = [{"text": msg.get("content", "")}]
            contents.append({"role": gemini_role, "parts": parts})

        payload: dict[str, Any] = {
            "contents": contents,
        }
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        generation_config: dict[str, Any] = {}
        if options.temperature is not None:
            generation_config["temperature"] = options.temperature
        if options.max_tokens is not None:
            generation_config["maxOutputTokens"] = options.max_tokens
        if options.top_p is not None:
            generation_config["topP"] = options.top_p
        if options.stop is not None:
            generation_config["stopSequences"] = options.stop
        if generation_config:
            payload["generationConfig"] = generation_config
        payload.update(options.extra)
        return payload

    def _model_endpoint(self, model: str) -> str:
        # Gemini model names may include "models/" prefix
        if model.startswith("models/"):
            model_name = model[7:]
        else:
            model_name = model
        return f"{self.base_url}/models/{model_name}:generateContent"

    async def generate(self, options: GenerateOptions) -> GenerateResult:
        """Send one generation request and return the full result."""
        payload = self._build_payload(options)
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": str(self.api_key),
        }
        url = self._model_endpoint(options.model)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            raise GeminiError(
                f"Gemini API error: {exc.response.status_code}",
                provider="gemini",
                details={"status_code": exc.response.status_code},
            ) from exc
        except httpx.RequestError as exc:
            raise GeminiError(
                f"Gemini request failed: {exc}",
                provider="gemini",
            ) from exc

        content = ""
        for candidate in data.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                if "text" in part:
                    content += part["text"]
        usage = data.get("usageMetadata")
        model = data.get("modelVersion", options.model)
        finish_reason = (
            data.get("candidates", [{}])[0].get("finishReason") if data.get("candidates") else None
        )

        return GenerateResult(
            content=content,
            model=model,
            provider="gemini",
            finish_reason=finish_reason,
            usage=usage if isinstance(usage, dict) else None,
            request_id=None,
        )

    async def generate_stream(self, options: GenerateOptions):
        """Stream generation results asynchronously."""
        payload = self._build_payload(options)
        # Gemini uses streamGenerateContent endpoint for streaming
        model_name = options.model[7:] if options.model.startswith("models/") else options.model
        url = f"{self.base_url}/models/{model_name}:streamGenerateContent"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": str(self.api_key),
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            import json

                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        for candidate in data.get("candidates", []):
                            for part in candidate.get("content", {}).get("parts", []):
                                if "text" in part:
                                    yield StreamChunk(
                                        type="token",
                                        content=part["text"],
                                        delta=part["text"],
                                        provider="gemini",
                                    )
                        if data.get("done"):
                            yield StreamChunk(type="done", done=True, provider="gemini")
                            break
        except httpx.HTTPStatusError as exc:
            yield StreamChunk(
                type="error",
                content=f"Gemini API error: {exc.response.status_code}",
                provider="gemini",
            )
        except httpx.RequestError as exc:
            yield StreamChunk(
                type="error",
                content=f"Gemini request failed: {exc}",
                provider="gemini",
            )
