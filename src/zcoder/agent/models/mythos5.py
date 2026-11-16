"""
zcoder_mythos5.py — ZCoder Pro support via Ollama (refactored from Claude Mythos 5)
ZCoder CLI v1.33.0

Refactored from claude_mythos5.py to work with ZCoder's own models running
locally on Ollama instead of Claude Mythos 5 via Anthropic API.

--mythos5 now maps to zcoder-pro (ZCoder's general-purpose model) via Ollama.
No API key or internet required.

CLI flags:
  --mythos5-info           Show ZCoder Pro capability table
  --mythos5 PROMPT         Call zcoder-pro via Ollama (replaces Claude Mythos 5)
"""

from __future__ import annotations

from typing import Any

from zcoder.agent.models.zcoder_model import (
    DEFAULT_OLLAMA_BASE_URL,
    ZCoderClient,
)
from zcoder.core.exceptions import ZCoderError
from zcoder.core.resilience import CircuitBreaker, retry

_breaker = CircuitBreaker(failure_threshold=5, reset_timeout=30)

# ── Mapping ──
# --mythos5 → zcoder-pro (general-purpose model)
MYTHOS5_MODEL_ID = "zcoder-pro"

MYTHOS5_INFO: dict[str, Any] = {
    "display_name": "ZCoder Pro (via Ollama)",
    "model_id": MYTHOS5_MODEL_ID,
    "tier": "current",
    "context_window": 32_768,
    "max_output_tokens": 8192,
    "size_gb": 4.7,
    "quant": "7B Q4_K",
    "effort_levels": ["low", "medium", "high", "max"],
    "fast_mode_supported": True,
    "notes": "Refactored from Claude Mythos 5 module. Now calls zcoder-pro "
    "via Ollama (local provider). No API key or internet required.",
}


class Mythos5Client:
    """ZCoder Pro client via Ollama (refactored from Claude Mythos 5 client).

    Same interface as before but calls local Ollama instead of Anthropic API.
    MythosAccessError is kept as a compatibility alias but will never be
    raised for local models.
    """

    def __init__(
        self,
        api_key: str | None = None,  # Ignored — Ollama doesn't need API key
        base_url: str = DEFAULT_OLLAMA_BASE_URL,
        max_tokens: int = 8192,
    ) -> None:
        self.base_url = base_url
        self.max_tokens = max_tokens
        self._client = ZCoderClient(
            model=MYTHOS5_MODEL_ID,
            base_url=base_url,
            max_tokens=max_tokens,
        )

    @retry(max_attempts=4, base_delay=1.0, max_delay=15.0, breaker=_breaker)
    def _call(self, payload: dict) -> dict:
        return self._client._call(payload)

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
    ) -> dict:
        """Build and send one request to zcoder-pro via Ollama."""
        return self._client.call(prompt, system=system)

    def call_text(self, prompt: str, system: str | None = None) -> str:
        return self._client.call_text(prompt, system=system)


class MythosAccessError(Exception):
    """Compatibility alias — never raised for local Ollama models."""

    pass


# ── Re-export for backward compatibility ─────────────────────────────────

__all__ = [
    "MYTHOS5_MODEL_ID",
    "MYTHOS5_INFO",
    "MythosAccessError",
    "Mythos5Client",
    "cmd_mythos5_info",
    "cmd_mythos5_call",
]


def cmd_mythos5_info():
    """Print ZCoder Pro capability table (refactored from Claude Mythos 5 info)."""
    print(f"\n\033[94mZCoder Pro (via Ollama)\033[0m  ({MYTHOS5_MODEL_ID})")
    print(f"  Model ID:          {MYTHOS5_MODEL_ID}")
    print(f"  Context window:    {MYTHOS5_INFO['context_window']:,} tokens")
    print(f"  Max output:        {MYTHOS5_INFO['max_output_tokens']:,} tokens")
    print(f"  Size:              {MYTHOS5_INFO['size_gb']} GB ({MYTHOS5_INFO['quant']})")
    print("  Pricing:           Free (local inference via Ollama)")
    print("\n  \033[93mNote:\033[0m Refactored from Claude Mythos 5 module.")
    print("    --mythos5 now calls zcoder-pro via Ollama (local provider).")
    print("    No API key or internet required. No access gate (Project Glasswing) needed.\n")


def cmd_mythos5_call(
    prompt: str,
    api_key: str | None = None,  # Ignored — Ollama doesn't need API key
    system: str | None = None,
):
    """Call zcoder-pro via Ollama (refactored from Claude Mythos 5 call)."""
    client = Mythos5Client(base_url=DEFAULT_OLLAMA_BASE_URL)
    try:
        text = client.call_text(prompt, system=system)
    except Exception as e:
        print(f"\033[91m✗ {e}\033[0m")
        return None
    print(text)
    return text
