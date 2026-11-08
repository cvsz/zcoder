"""
adapters.py — Fail-closed provider client adapters for ZCoder.

Implements thin HTTP client adapters for the providers declared in
``zcoder.agent.orchestration.providers``:

- gemini      — Generative Language API (x-goog-api-key auth)
- ollama      — Local Ollama chat API (no auth)
- vllm        — OpenAI-compatible vLLM server (bearer auth)
- nvidia      — NVIDIA NIM / integrate.api.nvidia.com (bearer auth)
- anthropic   — Anthropic Messages API (blocked under ZCODER_LOCAL_MODE)

Design principles:
- Fail closed: unknown provider, missing key, or network error raises;
  never silently falls back to a paid hosted model.
- Local-first: ZCODER_LOCAL_MODE=1 blocks all hosted provider calls at the
  provider_policy boundary before any adapter is reached.
- No credentials in URLs: API keys are passed via headers only.
- All timeouts bounded; all responses validated before return.
"""

from __future__ import annotations

import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from zcoder.agent.orchestration.providers import (
    PROVIDER_DEFAULTS,
    build_payload,
    endpoint_for,
    headers_for,
    parse_response,
    resolve_api_key,
    resolve_base_url,
)
from zcoder.core.provider_policy import (
    create_anthropic_client,
    enforce_outbound_url_policy,
    local_only_enabled,
)

_PROVIDER_ADAPTER_CACHE: dict[str, BaseProviderAdapter] = {}
_CREDENTIAL_CACHE_IDS: dict[str, str] = {}


def _credential_cache_id(api_key: str) -> str:
    """Return an opaque per-process identifier for a provider credential.

    Adapter cache keys must not embed the credential itself. The identifier
    only needs to be stable inside this process, so a random surrogate is
    used instead of deriving anything from the credential value.
    """
    cache_id = _CREDENTIAL_CACHE_IDS.get(api_key)
    if cache_id is None:
        cache_id = secrets.token_hex(8)
        _CREDENTIAL_CACHE_IDS[api_key] = cache_id
    return cache_id


class ProviderAdapterError(RuntimeError):
    """Raised when a provider adapter cannot complete a request."""


class BaseProviderAdapter:
    """Base class for provider-specific HTTP clients."""

    provider: str
    base_url: str
    api_key: str
    timeout_seconds: float = 30.0

    def __init__(
        self,
        provider: str,
        base_url: str,
        api_key: str,
        *,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def chat_complete(
        self,
        model: str,
        messages: list[dict[str, Any]],
        system: str | None = None,
        max_tokens: int = 128_000,
        sampling: dict[str, Any] | None = None,
    ) -> str:
        """Send a chat completion request and return the response text.

        Raises ProviderAdapterError on any failure — never falls back
        silently to another provider.
        """
        enforce_outbound_url_policy(self.base_url)
        url = endpoint_for(self.provider, self.base_url, model)
        if not url:
            raise ProviderAdapterError(
                f"No endpoint configured for provider {self.provider!r} and model {model!r}"
            )
        payload = build_payload(self.provider, model, messages, system, max_tokens, sampling or {})
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers=headers_for(self.provider, self.api_key),
            method="POST",
        )
        try:
            scheme = urllib.parse.urlsplit(url).scheme
            if scheme not in ("http", "https"):
                raise ProviderAdapterError(f"Unsupported URL scheme: {scheme}")
            with urllib.request.urlopen(
                req, timeout=self.timeout_seconds
            ) as resp:  # nosec B310  # scheme validated above
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            try:
                body = exc.read().decode("utf-8")[:500]
            except Exception:
                body = ""
            raise ProviderAdapterError(f"{self.provider} returned HTTP {exc.code}: {body}") from exc
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise ProviderAdapterError(f"{self.provider} network error: {exc}") from exc
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ProviderAdapterError(f"{self.provider} returned invalid JSON: {exc}") from exc
        return parse_response(self.provider, parsed)


def get_adapter(
    provider: str,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    timeout_seconds: float = 30.0,
) -> BaseProviderAdapter:
    """Build (and cache) a fail-closed provider adapter.

    Raises ProviderAdapterError if the provider is unknown, lacks credentials
    when required, or has no endpoint configured.
    """
    if provider not in PROVIDER_DEFAULTS:
        raise ProviderAdapterError(
            f"Unknown provider {provider!r} — expected one of {', '.join(PROVIDER_DEFAULTS)}"
        )

    if local_only_enabled() and provider != "ollama":
        # Local-only mode blocks all hosted provider calls; ollama is local-only
        # by default (base_url http://localhost:11434).
        raise ProviderAdapterError(f"Provider {provider!r} is blocked while ZCODER_LOCAL_MODE is enabled")

    if api_key is None:
        api_key = resolve_api_key(provider)
    spec = PROVIDER_DEFAULTS[provider]
    auth = spec.get("auth", "none")
    if auth != "none" and not api_key:
        raise ProviderAdapterError(
            f"Provider {provider!r} requires an API key (env: {', '.join(spec.get('env_keys', ()))})"
        )

    resolved_base = resolve_base_url(provider, base_url)
    if not resolved_base:
        raise ProviderAdapterError(f"No base URL configured for provider {provider!r}")

    credential_id = _credential_cache_id(api_key)
    key = f"{provider}:{resolved_base}:{credential_id}:{timeout_seconds}"

    if key in _PROVIDER_ADAPTER_CACHE:
        return _PROVIDER_ADAPTER_CACHE[key]

    adapter = BaseProviderAdapter(
        provider=provider,
        base_url=resolved_base,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
    )
    _PROVIDER_ADAPTER_CACHE[key] = adapter
    return adapter


def anthropic_available() -> bool:
    """Return whether the Anthropic SDK client can be constructed.

    Returns False (not an error) when local-only mode blocks Anthropic or
    the SDK is not installed — callers should treat this as "unavailable",
    not as a failure to be retried.
    """
    if local_only_enabled():
        return False
    try:
        create_anthropic_client(os.getenv("ANTHROPIC_API_KEY", ""))
        return True
    except Exception:
        return False


__all__ = [
    "BaseProviderAdapter",
    "ProviderAdapterError",
    "get_adapter",
    "anthropic_available",
]
