"""
providers.py — Provider-neutral gateway abstraction for ZCoder

Maps the multi-agent router across native APIs, OpenAI-compatible hosted
gateways, local inference servers, and the deterministic offline stub.

Precedence:
  provider:  ZCODER_LOCAL_MODE=1 > --provider > ZCODER_PROVIDER env > "openai_compatible"
  api_key:   --api-key > provider-specific env var(s) > ""
  base_url:  --base-url > ZCODER_BASE_URL env > provider-specific env (OLLAMA_BASE_URL) > provider default

All provider base URLs are scheme-checked (http/https only) via
``safe_urlopen`` semantics — file/ftp/custom schemes are rejected.
Explicit operator-configured gateways are trusted for egress; only
untrusted model-chosen URLs go through SSRF-aware ``safe_external_urlopen``.

Gemini uses ``x-goog-api-key`` without placing secrets in request URLs.
OpenAI-compatible hosts use bearer tokens; local runtimes may omit keys.
"""

from __future__ import annotations

import os
import urllib.parse
from dataclasses import dataclass
from typing import Any

from zcoder.core.exceptions import ZCoderError

PROVIDER_CHOICES = (
    "gemini",
    "xai",
    "groq",
    "openrouter",
    "cerebras",
    "nvidia",
    "openai_compatible",
    "ollama",
    "local",
)

OPENAI_COMPATIBLE_PROVIDERS = frozenset(
    {"xai", "groq", "openrouter", "cerebras", "nvidia", "openai_compatible"}
)

PROVIDER_DEFAULTS: dict[str, dict] = {
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com",
        "path": "/v1beta/models/{model}:generateContent",
        "env_keys": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        "auth": "x-goog-api-key",
    },
    "xai": {
        "base_url": "https://api.x.ai",
        "path": "/v1/chat/completions",
        "env_keys": ("XAI_API_KEY",),
        "auth": "bearer",
    },
    "groq": {
        "base_url": "https://api.groq.com",
        "path": "/openai/v1/chat/completions",
        "env_keys": ("GROQ_API_KEY",),
        "auth": "bearer",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai",
        "path": "/api/v1/chat/completions",
        "env_keys": ("OPENROUTER_API_KEY",),
        "auth": "bearer",
    },
    "cerebras": {
        "base_url": "https://api.cerebras.ai",
        "path": "/v1/chat/completions",
        "env_keys": ("CEREBRAS_API_KEY",),
        "auth": "bearer",
    },
    "nvidia": {
        "base_url": "https://integrate.api.nvidia.com/v1",
        "path": "/chat/completions",
        "env_keys": ("NVIDIA_API_KEY", "NVIDIA_API_KEY_1", "NVIDIA_API_KEY_2"),
        "auth": "bearer",
    },
    "openai_compatible": {
        "base_url": "",
        "path": "/chat/completions",
        "env_keys": ("OPENAI_COMPATIBLE_API_KEY",),
        "auth": "bearer",
    },
    "ollama": {
        "base_url": "http://localhost:11434",
        "path": "/api/chat",
        "env_keys": (),
        "auth": "none",
    },
    "local": {
        "base_url": "",
        "path": "",
        "env_keys": (),
        "auth": "none",
    },
}


@dataclass(frozen=True)
class ProviderConnection:
    """Immutable, type-checked representation of a provider connection.

    Frozen so it cannot be mutated after construction, making it safe to
    share across adapters and consumers.
    """

    provider: str
    api_key: str
    base_url: str
    headers: dict[str, str]


class MissingCredentialError(ZCoderError):
    """Raised when a provider requires a credential but none can be resolved."""

    error_code = "MISSING_CREDENTIAL"
    RETRYABLE = False


def _providers_requiring_credential() -> frozenset[str]:
    """Providers that must have a non-empty API key to function."""
    return frozenset(
        {
            provider
            for provider, spec in PROVIDER_DEFAULTS.items()
            if spec.get("env_keys") and provider not in {"local", "ollama"}
        }
    )


def _validate_base_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise ValueError(
            f"Unsupported provider base URL scheme: {scheme or '<missing>'} — expected http or https"
        )
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Provider base URL must have a host and no credentials, query, or fragment")


def resolve_provider(cli_provider: str | None = None) -> str:
    if os.getenv("ZCODER_LOCAL_MODE", "").strip().lower() in ("1", "true", "yes"):
        return "local"
    if cli_provider and cli_provider.strip():
        p = cli_provider.strip().lower()
        if p not in PROVIDER_CHOICES:
            raise ValueError(
                f"Unknown provider '{cli_provider}' — expected one of {', '.join(PROVIDER_CHOICES)}"
            )
        return p
    env_provider = os.getenv("ZCODER_PROVIDER", "").strip().lower()
    if env_provider:
        if env_provider not in PROVIDER_CHOICES:
            raise ValueError(
                f"Unknown ZCODER_PROVIDER '{env_provider}' — expected one of {', '.join(PROVIDER_CHOICES)}"
            )
        return env_provider
    return "openai_compatible"


def resolve_api_key(provider: str, cli_key: str | None = None) -> str:
    """Resolve the API key for *provider*.

    Returns the resolved key string, or ``""`` for providers that do not
    require a credential (``local``, ``ollama``). Raises
    :class:`MissingCredentialError` when a credential-requiring provider has
    no key available from CLI or environment — never silently returns ``""``.
    """
    if provider == "local":
        return ""
    if cli_key and cli_key.strip():
        return cli_key.strip()
    spec = PROVIDER_DEFAULTS.get(provider, {})
    for env_name in spec.get("env_keys", ()):
        v = os.getenv(env_name, "").strip()
        if v:
            return v
    if provider in _providers_requiring_credential():
        env_list = ", ".join(spec.get("env_keys", ())) or "<none configured>"
        raise MissingCredentialError(
            f"No API key configured for provider '{provider}'. " f"Set one of: {env_list} or pass --api-key.",
            details={"provider": provider, "env_keys": list(spec.get("env_keys", ()))},
        )
    return ""


def resolve_base_url(provider: str, cli_base_url: str | None = None) -> str:
    """Resolve the base URL for *provider*.

    Applies strict validation: scheme must be http/https, hostname must be
    present, and no credentials/query/fragment are allowed. Raises
    :class:`ValueError` on invalid input.
    """
    if cli_base_url and cli_base_url.strip():
        url = cli_base_url.strip().rstrip("/")
        _validate_base_url(url)
        return url
    if provider == "nvidia":
        nvidia_gateway = os.getenv("NVIDIA_BASE_URL", "").strip().rstrip("/")
        if nvidia_gateway:
            _validate_base_url(nvidia_gateway)
            return nvidia_gateway
    env_gateway = os.getenv("ZCODER_BASE_URL", "").strip().rstrip("/")
    if provider == "nvidia" and env_gateway:
        # Compose may inject the loopback llama.cpp URL for local services.
        # That URL is not an NVIDIA endpoint; use NVIDIA's default unless a
        # provider-specific URL or explicit CLI override was supplied.
        from urllib.parse import urlsplit

        if urlsplit(env_gateway).hostname in {"127.0.0.1", "localhost", "::1", "0.0.0.0"}:  # nosec B104
            env_gateway = ""
    if env_gateway:
        _validate_base_url(env_gateway)
        return env_gateway
    if provider == "ollama":
        ollama_env = os.getenv("OLLAMA_BASE_URL", "").strip().rstrip("/")
        if ollama_env:
            _validate_base_url(ollama_env)
            return ollama_env
        env_gateway = os.getenv("ZCODER_BASE_URL", "").strip().rstrip("/")
        if env_gateway:
            _validate_base_url(env_gateway)
            return env_gateway
    spec = PROVIDER_DEFAULTS.get(provider, {})
    default = spec.get("base_url", "")
    if provider == "openai_compatible" and not default:
        return os.getenv("ZCODER_BASE_URL", "http://127.0.0.1:11434/v1")
    return default


def endpoint_for(provider: str, base_url: str, model: str) -> str:
    spec = PROVIDER_DEFAULTS[provider]
    path_tmpl: str = spec["path"]
    if provider == "gemini":
        # Gemini interpolates the model into the path
        path = path_tmpl.format(model=model)
        return f"{base_url}{path}"
    if provider in ("anthropic", "ollama") or provider in OPENAI_COMPATIBLE_PROVIDERS:
        return f"{base_url}{path_tmpl}"
    # local has no endpoint
    return ""


def headers_for(provider: str, api_key: str) -> dict:
    spec = PROVIDER_DEFAULTS[provider]
    auth = spec.get("auth", "none")
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if auth == "x-api-key":
        if api_key:
            headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
    elif auth == "x-goog-api-key":
        if api_key:
            headers["x-goog-api-key"] = api_key
    elif auth == "bearer":
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
    # ollama/local: no auth header
    return headers


def build_payload(
    provider: str,
    model: str,
    messages: list[dict[str, str]],
    system: str | None = None,
    max_tokens: int = 4096,
    sampling: dict[str, Any] | None = None,
) -> dict:
    """Build a provider-specific request payload.

    Args:
        provider: Provider name (gemini, ollama, openai_compatible, etc.)
        model: Model identifier
        messages: Chat messages list
        system: System prompt
        max_tokens: Maximum output tokens
        sampling: Sampling parameters (temperature, top_p, etc.)

    Returns:
        Provider-specific payload dict
    """
    sampling = sampling or {}
    if provider == "gemini":
        contents = []
        for msg in messages:
            role = "model" if msg.get("role") == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": msg.get("content", "")}]})
        payload: dict = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": sampling.get("temperature", 0.7),
                "topP": sampling.get("top_p", 1.0),
            },
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        return payload
    if provider == "ollama":
        ollama_messages = [{"role": "system", "content": system}] if system else []
        ollama_messages.extend(messages)
        return {
            "model": model,
            "messages": ollama_messages,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": sampling.get("temperature", 0.7),
                "top_p": sampling.get("top_p", 1.0),
            },
        }
    # openai_compatible and others: OpenAI chat completions format
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": sampling.get("temperature", 0.7),
        "top_p": sampling.get("top_p", 1.0),
    }
    if system:
        payload["messages"].insert(0, {"role": "system", "content": system})
    for key in ("top_k", "frequency_penalty", "presence_penalty", "stop"):
        if key in sampling:
            payload[key] = sampling[key]
    return payload


def parse_response(provider: str, data: dict) -> str:
    """Parse a provider-specific response into plain text.

    Args:
        provider: Provider name
        data: Parsed JSON response dict

    Returns:
        Extracted text content
    """
    if provider == "gemini":
        candidates = data.get("candidates", [])
        if candidates:
            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            if parts:
                return parts[0].get("text", "")
        return ""
    if provider == "local":
        return "[local mode] No upstream call — local stub response."
    if provider == "ollama":
        return data.get("message", {}).get("content", "")
    # openai_compatible and others: OpenAI chat completions format
    choices = data.get("choices", [])
    if choices:
        message = choices[0].get("message", {})
        return message.get("content", "")
    return ""


__all__ = [
    "PROVIDER_CHOICES",
    "OPENAI_COMPATIBLE_PROVIDERS",
    "PROVIDER_DEFAULTS",
    "ProviderConnection",
    "MissingCredentialError",
    "resolve_provider",
    "resolve_api_key",
    "resolve_base_url",
    "endpoint_for",
    "headers_for",
    "build_payload",
    "parse_response",
]
