"""
providers.py — Provider-neutral gateway abstraction for ZCoder

Maps the router (and future CLI capabilities) across Anthropic,
Gemini, X.AI Grok, local Ollama, and the local-mode stub via an
explicit provider selection + gateway override contract.

Precedence:
  provider:  --provider > ZCODER_PROVIDER env > ZCODER_LOCAL_MODE=1 > "anthropic"
  api_key:   --api-key > provider-specific env var(s) > ""
  base_url:  --base-url > ZCODER_BASE_URL env > provider-specific env (OLLAMA_BASE_URL) > provider default

All provider base URLs are scheme-checked (http/https only) via
``safe_urlopen`` semantics — file/ftp/custom schemes are rejected.
Explicit operator-configured gateways are trusted for egress; only
untrusted model-chosen URLs go through SSRF-aware ``safe_external_urlopen``.

Gemini auth uses ``x-goog-api-key`` header (query-param form is NOT used
so keys do not leak into URLs/logs). X.AI uses OpenAI-compatible
``Authorization: Bearer``. Ollama and local require no key.
"""

from __future__ import annotations

import os
import urllib.parse

PROVIDER_CHOICES = ("anthropic", "gemini", "xai", "ollama", "local")

PROVIDER_DEFAULTS: dict[str, dict] = {
    "anthropic": {
        "base_url": "https://api.anthropic.com",
        "path": "/v1/messages",
        "env_keys": ("ANTHROPIC_API_KEY",),
        "auth": "x-api-key",
    },
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


def _validate_base_url(url: str) -> None:
    scheme = urllib.parse.urlparse(url).scheme.lower()
    if scheme not in {"http", "https"}:
        raise ValueError(
            f"Unsupported provider base URL scheme: {scheme or '<missing>'} — expected http or https"
        )


def resolve_provider(cli_provider: str | None = None) -> str:
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
    if os.getenv("ZCODER_LOCAL_MODE", "").strip().lower() in ("1", "true", "yes"):
        return "local"
    return "anthropic"


def resolve_api_key(provider: str, cli_key: str | None = None) -> str:
    if cli_key and cli_key.strip():
        return cli_key.strip()
    spec = PROVIDER_DEFAULTS.get(provider, {})
    for env_name in spec.get("env_keys", ()):
        v = os.getenv(env_name, "").strip()
        if v:
            return v
    # generic fallback for anthropic-compatible gateways
    if provider == "anthropic":
        v = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if v:
            return v
    return ""


def resolve_base_url(provider: str, cli_base_url: str | None = None) -> str:
    if cli_base_url and cli_base_url.strip():
        url = cli_base_url.strip().rstrip("/")
        _validate_base_url(url)
        return url
    env_gateway = os.getenv("ZCODER_BASE_URL", "").strip().rstrip("/")
    if env_gateway:
        _validate_base_url(env_gateway)
        return env_gateway
    if provider == "ollama":
        ollama_env = os.getenv("OLLAMA_BASE_URL", "").strip().rstrip("/")
        if ollama_env:
            _validate_base_url(ollama_env)
            return ollama_env
    spec = PROVIDER_DEFAULTS.get(provider, {})
    return spec.get("base_url", "")


def endpoint_for(provider: str, base_url: str, model: str) -> str:
    spec = PROVIDER_DEFAULTS[provider]
    path_tmpl: str = spec["path"]
    if provider == "gemini":
        # Gemini interpolates the model into the path
        path = path_tmpl.format(model=model)
        return f"{base_url}{path}"
    if provider in ("anthropic", "xai", "ollama"):
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
    messages: list[dict],
    system: str | None,
    max_tokens: int,
    sampling: dict,
) -> dict:
    if provider == "anthropic":
        payload: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            payload["system"] = system
        payload.update(sampling)
        return payload
    if provider == "xai":
        xai_messages: list[dict] = []
        if system:
            xai_messages.append({"role": "system", "content": system})
        xai_messages.extend(messages)
        payload = {
            "model": model,
            "messages": xai_messages,
            "max_tokens": max_tokens,
        }
        if sampling:
            payload.update(sampling)
        return payload
    if provider == "gemini":
        # Gemini uses "contents" with "parts"
        contents: list[dict] = []
        for m in messages:
            role = m.get("role", "user")
            # Gemini uses "user" and "model" roles
            if role == "assistant":
                role = "model"
            text = m.get("content", "")
            contents.append({"role": role, "parts": [{"text": text}]})
        payload = {
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
    if provider == "ollama":
        ollama_messages: list[dict] = []
        if system:
            ollama_messages.append({"role": "system", "content": system})
        ollama_messages.extend(messages)
        payload = {
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
    # local
    return {}


def parse_response(provider: str, data: dict) -> str:
    if provider == "anthropic":
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    if provider == "xai":
        choices = data.get("choices", [])
        if choices:
            msg = choices[0].get("message", {})
            return msg.get("content", "") or ""
        return ""
    if provider == "gemini":
        candidates = data.get("candidates", [])
        if candidates:
            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            return "".join(p.get("text", "") for p in parts)
        return ""
    if provider == "ollama":
        # Ollama chat: {"message": {"role": "assistant", "content": "..."}}
        msg = data.get("message", {})
        if isinstance(msg, dict) and "content" in msg:
            return msg.get("content", "") or ""
        # streaming-aggregated fallback
        return data.get("response", "") or ""
    if provider == "local":
        return data.get("text", "") or "[local mode] No upstream call — local stub response."
    return ""
