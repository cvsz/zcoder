"""Outbound AI provider policy shared by CLI and library entry points."""

from __future__ import annotations

import os
import urllib.parse

_HOSTED_MODEL_API_DOMAINS = frozenset(
    {
        "anthropic.com",
        "cerebras.ai",
        "generativelanguage.googleapis.com",
        "groq.com",
        "openai.com",
        "openrouter.ai",
        "voyageai.com",
        "x.ai",
    }
)


def local_only_enabled() -> bool:
    """Return whether the process has explicitly enabled local-only mode."""
    return os.getenv("ZCODER_LOCAL_MODE", "").strip().lower() in {"1", "true", "yes"}


def ensure_anthropic_api_allowed() -> None:
    """Fail before constructing an Anthropic SDK client in local-only mode."""
    if local_only_enabled():
        raise RuntimeError("Anthropic API access is disabled while ZCODER_LOCAL_MODE is enabled.")


def enforce_outbound_url_policy(url: str) -> None:
    """Block hosted model APIs at the shared urllib boundary in local mode."""
    if not local_only_enabled():
        return

    hostname = (urllib.parse.urlsplit(url).hostname or "").lower().rstrip(".")
    if any(hostname == domain or hostname.endswith(f".{domain}") for domain in _HOSTED_MODEL_API_DOMAINS):
        if hostname == "anthropic.com" or hostname.endswith(".anthropic.com"):
            raise RuntimeError("Anthropic API access is disabled while ZCODER_LOCAL_MODE is enabled.")
        raise RuntimeError("Hosted model API access is disabled while ZCODER_LOCAL_MODE is enabled.")


def create_anthropic_client(api_key: str):
    """Construct the optional Anthropic SDK client after enforcing local policy."""
    ensure_anthropic_api_allowed()
    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError(
            "Anthropic SDK is not installed. Install with 'pip install zcoder[anthropic]' "
            "or configure a different provider."
        ) from exc

    return anthropic.Anthropic(api_key=api_key)
