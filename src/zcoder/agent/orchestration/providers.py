"""
providers.py — Provider-neutral gateway abstraction for ZCoder

Maps the router (and future CLI capabilities) across local Ollama
and llama.cpp via an
explicit provider selection + gateway override contract.

Precedence:
  provider:  --provider > ZCODER_PROVIDER env > ZCODER_LOCAL_MODE=1 > "local"
  api_key:   --api-key > provider-specific env var(s) > ""
  base_url:  --base-url > ZCODER_BASE_URL env > provider-specific env (OLLAMA_BASE_URL) > provider default

All provider base URLs are scheme-checked (http/https only) via
``safe_urlopen`` semantics — file/ftp/custom schemes are rejected.
Explicit operator-configured gateways are trusted for egress; only
untrusted model-chosen URLs go through SSRF-aware ``safe_external_urlopen``.

Local providers do not require cloud credentials.
"""

from __future__ import annotations

import os
import urllib.parse

PROVIDER_CHOICES = ("local", "llama_cpp")

PROVIDER_DEFAULTS: dict[str, dict] = {
    "local": {
        "base_url": "http://127.0.0.1:8080",
        "path": "/v1/chat/completions",
        "env_keys": (),
        "auth": "none",
    },
}
PROVIDER_DEFAULTS["llama_cpp"] = PROVIDER_DEFAULTS["local"]

MODEL_ALIASES = {
    "zcoder-qwen2.5-coder-7b": "zcoder-qwen2.5-coder-7b",
    "zcoder-qwen2.5-coder-1.5b": "zcoder-qwen2.5-coder-1.5b",
    "local": "zcoder-qwen2.5-coder-7b",
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
        if p == "llama_cpp":
            return "local"
        if p not in PROVIDER_CHOICES:
            raise ValueError(
                f"Unknown provider '{cli_provider}' — expected one of {', '.join(PROVIDER_CHOICES)}"
            )
        return p
    env_provider = os.getenv("ZCODER_PROVIDER", "").strip().lower()
    if env_provider:
        if env_provider == "llama_cpp":
            return "local"
        if env_provider not in PROVIDER_CHOICES:
            raise ValueError(
                f"Unknown ZCODER_PROVIDER '{env_provider}' — expected one of {', '.join(PROVIDER_CHOICES)}"
            )
        return env_provider
    if os.getenv("ZCODER_LOCAL_MODE", "").strip().lower() in ("1", "true", "yes"):
        return "local"
    return "local"


def resolve_api_key(provider: str, cli_key: str | None = None) -> str:
    del provider, cli_key
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
    spec = PROVIDER_DEFAULTS.get(provider, {})
    return spec.get("base_url", "")


def endpoint_for(provider: str, base_url: str, model: str) -> str:
    spec = PROVIDER_DEFAULTS[provider]
    path_tmpl: str = spec["path"]
    if provider == "local":
        return f"{base_url}{path_tmpl}"
    raise ValueError(f"Unsupported provider: {provider}")


def resolve_model(model: str | None) -> str:
    """Resolve a public zCoder model ID to the local server model alias."""
    if model is None:
        return MODEL_ALIASES["zcoder-qwen2.5-coder-7b"]
    try:
        return MODEL_ALIASES[model]
    except KeyError as exc:
        raise ValueError(f"Unsupported local model '{model}'") from exc


def headers_for(provider: str, api_key: str) -> dict:
    del api_key
    if provider not in PROVIDER_DEFAULTS:
        raise ValueError(f"Unsupported provider: {provider}")
    headers: dict[str, str] = {"Content-Type": "application/json"}
    # Local providers do not attach credentials.
    return headers


def build_payload(
    provider: str,
    model: str,
    messages: list[dict],
    system: str | None,
    max_tokens: int,
    sampling: dict,
) -> dict:
    if provider != "local":
        raise ValueError(f"Unsupported provider: {provider}")
    local_messages: list[dict] = []
    if system:
        local_messages.append({"role": "system", "content": system})
    local_messages.extend(messages)
    payload = {"model": model, "messages": local_messages, "max_tokens": max_tokens, "stream": False}
    payload.update(sampling)
    return payload


def parse_response(provider: str, data: dict) -> str:
    if provider == "local":
        choices = data.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "") or ""
        return ""
    raise ValueError(f"Unsupported provider: {provider}")
