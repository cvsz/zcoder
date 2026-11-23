"""
local.py — Local GGUF model server adapter (Phase 2).

Implements a local GGUF model provider adapter that talks to a running
Ollama instance over HTTP.  All inference happens on loopback; no
network egress to hosted model APIs is ever performed.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from zcoder.core.exceptions import APIError

from .adapter import ProviderAdapter, ProviderResult


class LocalAdapter(ProviderAdapter):
    """Adapter for a local GGUF model served via Ollama.

    Communicates with a locally-running Ollama server over HTTP.
    All inference happens on the loopback interface; no remote model
    API is ever contacted.
    """

    @classmethod
    def provider_id(cls) -> str:
        return "local"

    def build_payload(
        self,
        model: str,
        messages: list[dict[str, Any]],
        system: str | None,
        max_tokens: int,
        sampling: dict[str, Any],
    ) -> dict[str, Any]:
        """Build the Ollama OpenAI-compatible chat/completions request payload."""
        messages_list: list[dict[str, Any]] = []
        if system:
            messages_list.append({"role": "system", "content": system})
        messages_list.extend(messages)

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages_list,
            "max_tokens": max_tokens,
            "stream": False,
        }

        # Apply sampling parameters that Ollama understands
        if sampling.get("temperature") is not None:
            payload["temperature"] = sampling["temperature"]
        if sampling.get("top_p") is not None:
            payload["top_p"] = sampling["top_p"]
        if sampling.get("top_k") is not None:
            payload["top_k"] = sampling["top_k"]
        if sampling.get("stop") is not None:
            payload["stop"] = sampling["stop"]

        return payload

    def parse_response(self, data: dict[str, Any]) -> str:
        """Parse the Ollama chat/completions response."""
        choices = data.get("choices", [])
        if choices:
            message = choices[0].get("message", {})
            return message.get("content", "")
        return ""

    def endpoint_for(self, base_url: str, model: str) -> str:
        """Return the Ollama chat/completions endpoint URL."""
        base = base_url.rstrip("/")
        return f"{base}/v1/chat/completions"

    def headers_for(self, api_key: str) -> dict[str, str]:
        """Return HTTP headers for the request."""
        headers: dict[str, str] = {"Content-Type": "application/json"}
        # Ollama does not require authentication by default, but we
        # accept an API key if one is provided for compatibility.
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

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
        """Execute a single chat completion against the local Ollama server."""
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

        try:
            with urllib.request.urlopen(request, timeout=300) as resp:  # nosec B310
                raw = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode()
            if exc.code == 401:
                from zcoder.core.exceptions import AuthenticationError

                raise AuthenticationError("API key rejected (401)", details={"body": body[:300]}) from exc
            if exc.code == 429:
                from zcoder.core.exceptions import RateLimitError

                raise RateLimitError("Rate limited (429)", details={"body": body[:300]}) from exc
            if exc.code >= 500:
                from zcoder.core.exceptions import TransientAPIError

                raise TransientAPIError(
                    f"Server error ({exc.code})",
                    details={"body": body[:300]},
                ) from exc
            raise APIError(
                f"Request rejected ({exc.code})",
                status_code=exc.code,
                details={"body": body[:300]},
            ) from exc
        except (TimeoutError, OSError) as exc:
            from zcoder.core.exceptions import TransientAPIError

            raise TransientAPIError(f"Network error: {exc}") from exc

        content = self.parse_response(raw)
        return ProviderResult(
            content=content,
            raw=raw,
            provider=self.provider_id(),
            model=model,
        )
