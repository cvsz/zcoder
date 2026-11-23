"""
zcoder_model.py — ZCoder model support via Ollama (local provider)
ZCoder CLI v1.33.0

Refactored from Claude model modules (opus5.py, fable5.py, etc.) to work with
ZCoder's own models (zcoder-pro, zcoder-flash, zcoder-promax, zcoder-max)
running on Ollama / local provider instead of Anthropic API.

No API key or internet required — uses the configured Ollama endpoint
(default: http://127.0.0.1:11434).

CLI flags:
  --zcoder-model MODEL    Select ZCoder model (zcoder-pro, zcoder-flash,
                          zcoder-promax, zcoder-max, llama3.2:1b)
  --zcoder-info           Show ZCoder model capability table
  --zcoder PROMPT         Call a ZCoder model via Ollama
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from zcoder.core.exceptions import ZCoderError
from zcoder.core.resilience import CircuitBreaker, retry, urlopen_json

# ── ZCoder model definitions (local, via Ollama) ──────────────────────────

ZCODER_MODELS: dict[str, dict[str, Any]] = {
    "zcoder-pro": {
        "display_name": "ZCoder Pro",
        "size_gb": 4.7,
        "quant": "7B Q4_K",
        "context_window": 32_768,
        "max_output": 8192,
        "notes": "General-purpose ZCoder model. Balanced speed and quality.",
    },
    "zcoder-flash": {
        "display_name": "ZCoder Flash",
        "size_gb": 1.1,
        "quant": "1.5B Q4_K",
        "context_window": 32_768,
        "max_output": 8192,
        "notes": "Fast, lightweight ZCoder model for simple tasks.",
    },
    "zcoder-promax": {
        "display_name": "ZCoder ProMax",
        "size_gb": 16.8,
        "quant": "27B Q4_K",
        "context_window": 32_768,
        "max_output": 8192,
        "notes": "Large ZCoder model for complex reasoning tasks.",
    },
    "zcoder-max": {
        "display_name": "ZCoder Max",
        "size_gb": 18.4,
        "quant": "9B BF16",
        "context_window": 32_768,
        "max_output": 8192,
        "notes": "Largest ZCoder model, BF16 precision for maximum quality.",
    },
    "llama3.2:1b": {
        "display_name": "Llama 3.2 1B",
        "size_gb": 1.3,
        "quant": "1B Q4_K",
        "context_window": 32_768,
        "max_output": 8192,
        "notes": "Base Llama 3.2 1B model (fallback).",
    },
}

DEFAULT_ZCODER_MODEL = "zcoder-pro"

# Default Ollama endpoint (matches docker-compose and .env)
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
OLLAMA_CHAT_ENDPOINT = "/api/chat"

_breaker = CircuitBreaker(failure_threshold=5, reset_timeout=30)


# ── ZCoder client ─────────────────────────────────────────────────────────


class ZCoderClient:
    """Ollama chat client for ZCoder models.

    Sends requests to a local Ollama instance. No API key required.
    Follows the same _post() pattern as Opus5Client / Fable5Client for
    consistency.
    """

    def __init__(
        self,
        model: str = DEFAULT_ZCODER_MODEL,
        base_url: str = DEFAULT_OLLAMA_BASE_URL,
        max_tokens: int = 8192,
        temperature: float = 0.7,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.max_tokens = max_tokens
        self.temperature = temperature

    @retry(max_attempts=4, base_delay=1.0, max_delay=15.0, breaker=_breaker)
    def _call(self, payload: dict) -> dict:
        headers = {
            "Content-Type": "application/json",
        }
        req = urllib.request.Request(
            self.base_url + OLLAMA_CHAT_ENDPOINT,
            data=json.dumps(payload).encode(),
            headers=headers,
            method="POST",
        )
        return urlopen_json(req, timeout=300)

    def _post(self, payload: dict) -> dict:
        try:
            return self._call(payload)
        except ZCoderError as e:
            return {"error": e.message, "status": getattr(e, "status_code", None)}
        except Exception as e:
            return {"error": str(e)}

    def call(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs,
    ) -> dict:
        """Build and send one chat request to Ollama."""
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["num_predict"] = max_tokens
        else:
            payload["num_predict"] = self.max_tokens

        return self._post(payload)

    def call_text(self, prompt: str, **kwargs) -> str:
        data = self.call(prompt, **kwargs)
        if "error" in data:
            return f"[ERROR] {data['error']}"
        # Ollama chat response: {"message": {"role": "assistant", "content": "..."}, ...}
        msg = data.get("message", {})
        if isinstance(msg, dict):
            return msg.get("content", "")
        # Fallback: some Ollama versions return "response" directly
        return data.get("response", "")


# ── Helper functions ─────────────────────────────────────────────────────


def list_zcoder_models() -> list[str]:
    """Return sorted list of known ZCoder model IDs."""
    return sorted(ZCODER_MODELS.keys())


def get_zcoder_model_info(model_id: str) -> dict[str, Any] | None:
    """Return info dict for a ZCoder model, or None if unknown."""
    return ZCODER_MODELS.get(model_id)


def cmd_zcoder_info():
    """Print capability table for all ZCoder models."""
    print("\n\033[94mZCoder Models (via Ollama / local provider)\033[0m")
    print(f"  Default Ollama endpoint: {DEFAULT_OLLAMA_BASE_URL}")
    print(f"  Default model: {DEFAULT_ZCODER_MODEL}\n")
    for model_id, info in ZCODER_MODELS.items():
        marker = " (default)" if model_id == DEFAULT_ZCODER_MODEL else ""
        print(f"  \033[92m{model_id}\033[0m{marker}")
        print(f"    Display:   {info['display_name']}")
        print(f"    Size:      {info['size_gb']} GB ({info['quant']})")
        print(f"    Context:   {info['context_window']:,} tokens")
        print(f"    Max out:   {info['max_output']:,} tokens")
        print(f"    Notes:     {info['notes']}")
        print()


def cmd_zcoder_call(
    prompt: str,
    model: str = DEFAULT_ZCODER_MODEL,
    system: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    base_url: str = DEFAULT_OLLAMA_BASE_URL,
):
    """Call a ZCoder model via Ollama and print the response."""
    if model not in ZCODER_MODELS:
        print(f"\033[91m✗ Unknown ZCoder model '{model}'.\033[0m")
        print(f"    Available: {', '.join(list_zcoder_models())}")
        return None

    client = ZCoderClient(
        model=model,
        base_url=base_url,
        max_tokens=max_tokens or 8192,
        temperature=temperature or 0.7,
    )
    try:
        data = client.call(
            prompt,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except ValueError as e:
        print(f"\033[91m✗ {e}\033[0m")
        return None

    if "error" in data:
        print(f"[ERROR] {data['error']}")
        return None

    text = client.call_text(prompt, system=system, temperature=temperature, max_tokens=max_tokens)
    print(text)
    return data
