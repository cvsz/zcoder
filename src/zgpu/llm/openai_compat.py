"""OpenAI-compatible chat adapter for zGPU's local model registry."""

from __future__ import annotations

import base64
import binascii
import re
import time
import uuid
from collections.abc import Callable
from typing import Any, Protocol


class RegistryProtocol(Protocol):
    def list_models(self) -> list[dict[str, Any]]: ...

    def tokenize(self, model_name: str, text: str) -> list[int]: ...

    def generate(
        self,
        prompt: str,
        model_name: str | None = None,
        max_tokens: int = 16,
        token_callback: Callable[[str], None] | None = None,
    ) -> dict[str, Any]: ...


class CompletionRequestError(ValueError):
    """Invalid or unsupported OpenAI-compatible completion input."""


class ProviderPool:
    """Combine optional local and remote providers under one model namespace."""

    def __init__(self, providers: list[Any]):
        self.providers = [provider for provider in providers if provider is not None]
        self._routes: dict[str, Any] = {}

    def list_models(self) -> list[dict[str, Any]]:
        routes: dict[str, Any] = {}
        models: list[dict[str, Any]] = []
        for provider in self.providers:
            for model in provider.list_models():
                model_id = model.get("id") if isinstance(model, dict) else None
                if not isinstance(model_id, str) or not model_id or model_id in routes:
                    raise CompletionRequestError(
                        "configured providers returned invalid or duplicate model identifiers"
                    )
                routes[model_id] = provider
                models.append(model)
        self._routes = routes
        return models

    def create_completion(
        self,
        payload: dict[str, Any],
        event_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any] | None:
        model_id = payload.get("model")
        provider = self._routes.get(model_id) if isinstance(model_id, str) else None
        if provider is None:
            self.list_models()
            provider = self._routes.get(model_id) if isinstance(model_id, str) else None
        if provider is None:
            raise CompletionRequestError("the selected provider model is unavailable")
        return provider.create_completion(payload, event_callback=event_callback)


class OpenAICompatibleAdapter:
    """Translate OpenAI chat-completion requests to the zGPU model registry."""

    MAX_PROMPT_CHARS = 16_000
    MAX_COMPLETION_TOKENS = 4096
    MAX_IMAGE_BYTES = 524_288

    def __init__(self, registry: RegistryProtocol, external_provider: Any | None = None):
        self.registry = registry
        self.external_provider = external_provider

    def list_models(self) -> dict[str, Any]:
        models = [
            {"id": model["name"], "object": "model", "created": 0, "owned_by": "zgpu"}
            for model in self.registry.list_models()
        ]
        if self.external_provider is not None:
            models.extend(self.external_provider.list_models())
        return {
            "object": "list",
            "data": models,
        }

    def create_completion(
        self,
        payload: dict[str, Any],
        event_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any] | None:
        model = payload.get("model")
        if model is not None and (not isinstance(model, str) or not model.strip()):
            raise CompletionRequestError("'model' must be a non-empty string")

        # Remote providers implement their own OpenAI-compatible request contract.
        # Dispatch before applying the simulator's text-only and token-count limits
        # so tools, structured content, and larger completions can pass through.
        local_models = {entry["name"] for entry in self.registry.list_models()}
        target_model = model or "zgpu-thai"
        external_models = set()
        if self.external_provider is not None and target_model not in local_models:
            external_models = {entry["id"] for entry in self.external_provider.list_models()}
        if target_model in external_models:
            self._validate_remote_images(payload)
            return self.external_provider.create_completion(payload, event_callback=event_callback)

        messages = payload.get("messages")
        if not isinstance(messages, list) or not messages:
            raise CompletionRequestError("'messages' must be a non-empty array")

        prompt_parts: list[str] = []
        for index, message in enumerate(messages):
            if not isinstance(message, dict):
                raise CompletionRequestError(f"'messages[{index}]' must be an object")
            role = message.get("role")
            content = message.get("content")
            if role not in {"system", "user", "assistant"}:
                raise CompletionRequestError(f"'messages[{index}].role' must be system, user, or assistant")
            if not isinstance(content, str):
                raise CompletionRequestError(f"'messages[{index}].content' must be plain text")
            prompt_parts.append(f"{role}: {content}")

        prompt = "\n".join(prompt_parts) + "\nassistant:"
        if len(prompt) > self.MAX_PROMPT_CHARS:
            raise CompletionRequestError(f"prompt exceeds {self.MAX_PROMPT_CHARS} characters")

        max_tokens = payload.get("max_completion_tokens", payload.get("max_tokens", 16))
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int):
            raise CompletionRequestError("'max_tokens' must be an integer")
        if not 1 <= max_tokens <= self.MAX_COMPLETION_TOKENS:
            raise CompletionRequestError(f"'max_tokens' must be between 1 and {self.MAX_COMPLETION_TOKENS}")

        stream = payload.get("stream", False)
        if not isinstance(stream, bool):
            raise CompletionRequestError("'stream' must be a boolean")

        available_models = local_models
        available_models.update(external_models)
        if target_model not in available_models:
            raise CompletionRequestError(f"unknown model '{target_model}'")

        prompt_tokens = len(self.registry.tokenize(target_model, prompt))
        completion_id = f"chatcmpl-{uuid.uuid4().hex}"
        created = int(time.time())
        if stream and event_callback:
            event_callback(self._chunk(completion_id, created, target_model, {"role": "assistant"}, None))

        def emit_content(text: str) -> None:
            if stream and event_callback and text:
                event_callback(self._chunk(completion_id, created, target_model, {"content": text}, None))

        generated = self.registry.generate(
            prompt,
            model_name=target_model,
            max_tokens=max_tokens,
            token_callback=emit_content if stream else None,
        )
        if stream and event_callback:
            event_callback(self._chunk(completion_id, created, target_model, {}, generated["finish_reason"]))
        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": created,
            "model": generated["model"],
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": generated["text"]},
                    "finish_reason": generated["finish_reason"],
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": generated["tokens_generated"],
                "total_tokens": prompt_tokens + generated["tokens_generated"],
            },
        }

    @classmethod
    def _validate_remote_images(cls, payload: dict[str, Any]) -> None:
        """Allow at most one bounded, signature-checked inline image per request."""
        messages = payload.get("messages")
        if not isinstance(messages, list):
            return
        image_count = 0
        pattern = re.compile(r"data:(image/(?:jpeg|png|webp|gif));base64,([A-Za-z0-9+/]*={0,2})")
        signatures = {
            "image/jpeg": lambda data: data.startswith(b"\xff\xd8\xff"),
            "image/png": lambda data: data.startswith(b"\x89PNG\r\n\x1a\n"),
            "image/gif": lambda data: data.startswith((b"GIF87a", b"GIF89a")),
            "image/webp": lambda data: len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP",
        }
        for message in messages:
            if not isinstance(message, dict) or not isinstance(message.get("content"), list):
                continue
            for part in message["content"]:
                if not isinstance(part, dict) or part.get("type") != "image_url":
                    continue
                image_count += 1
                image_url = part.get("image_url")
                url = image_url.get("url") if isinstance(image_url, dict) else None
                match = pattern.fullmatch(url) if isinstance(url, str) else None
                if not match:
                    raise CompletionRequestError(
                        "image attachments must use supported inline base64 data URLs"
                    )
                media_type, encoded = match.groups()
                if len(encoded) > ((cls.MAX_IMAGE_BYTES + 2) // 3) * 4:
                    raise CompletionRequestError("image attachment exceeds 512 KiB")
                try:
                    image_data = base64.b64decode(encoded, validate=True)
                except (binascii.Error, ValueError) as exc:
                    raise CompletionRequestError("image attachment contains invalid base64 data") from exc
                if not image_data or len(image_data) > cls.MAX_IMAGE_BYTES:
                    raise CompletionRequestError("image attachment must contain 1 to 524288 bytes")
                if not signatures[media_type](image_data):
                    raise CompletionRequestError("image content does not match its declared media type")
        if image_count > 1:
            raise CompletionRequestError("at most one image attachment is supported per request")

    @staticmethod
    def _chunk(
        completion_id: str,
        created: int,
        model: str,
        delta: dict[str, str],
        finish_reason: str | None,
    ) -> dict[str, Any]:
        return {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
        }
