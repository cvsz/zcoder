"""
zcoder_opus5.py — ZCoder Pro support via Ollama (refactored from Claude Opus 5)
ZCoder CLI v1.33.0

Refactored from claude_opus5.py to work with ZCoder's own models running
locally on Ollama instead of Claude Opus 5 via Anthropic API.

No API key or internet required — uses the configured Ollama endpoint.

The --opus5 CLI flag now calls zcoder-pro (ZCoder's flagship model) via
Ollama, preserving the same CLI interface but using local inference.

CLI flags:
  --opus5-info           Show ZCoder Pro capability table
  --opus5 PROMPT         Call zcoder-pro via Ollama (replaces Claude Opus 5)
  --opus5-effort LEVEL   Effort level (low/medium/high/max) — mapped to
                         temperature for ZCoder models
  --opus5-disable-thinking Not applicable to ZCoder models (accepted for
                         compatibility, ignored)
  --opus5-fast           Send faster inference (mapped to lower temperature)
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

# ── Backward-compatible aliases ──────────────────────────────────────────

# --opus5 now maps to zcoder-pro
OPUS5_MODEL_ID = "zcoder-pro"

# Effort levels mapped to temperature for ZCoder models
OPUS5_EFFORT_BUDGETS = {
    "low": 0.3,
    "medium": 0.5,
    "high": 0.7,
    "max": 0.9,
}
OPUS5_EFFORT_LEVELS = list(OPUS5_EFFORT_BUDGETS.keys())

# All effort levels allow "thinking disabled" (ignored for ZCoder models)
OPUS5_THINKING_DISABLE_ALLOWED = {"low", "medium", "high", "max"}


OPUS5_INFO: dict[str, Any] = {
    "display_name": "ZCoder Pro (via Ollama)",
    "model_id": OPUS5_MODEL_ID,
    "tier": "current",
    "context_window": 32_768,
    "max_output_tokens": 8192,
    "size_gb": 4.7,
    "quant": "7B Q4_K",
    "effort_levels": OPUS5_EFFORT_LEVELS,
    "fast_mode_supported": True,
    "notes": "Refactored from Claude Opus 5 module. Now calls zcoder-pro "
    "via Ollama (local provider). No API key or internet required.",
}


def validate_effort_thinking(effort: str | None, disable_thinking: bool) -> str | None:
    """Validate effort/thinking combination for ZCoder models.

    ZCoder models don't have the same thinking restrictions as Claude Opus 5,
    so this is a compatibility shim that accepts all combinations.
    """
    if effort is not None and effort not in OPUS5_EFFORT_LEVELS:
        return (
            f"unknown effort level '{effort}' for ZCoder Pro — choose from {', '.join(OPUS5_EFFORT_LEVELS)}"
        )
    # disable_thinking is accepted but ignored for ZCoder models
    return None


def validate_inference_geo(use_geo: bool) -> str | None:
    """Inference geo is not applicable to local Ollama models."""
    return None


class Opus5Client:
    """ZCoder Pro client via Ollama (refactored from Claude Opus 5 client).

    Same interface as before but calls local Ollama instead of Anthropic API.
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
            model=OPUS5_MODEL_ID,
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
        effort: str | None = None,
        disable_thinking: bool = False,
        fast: bool = False,
        use_geo: bool = False,
    ) -> dict:
        """Build and send one request to zcoder-pro via Ollama.

        effort maps to temperature. disable_thinking and use_geo are
        accepted for compatibility but have no effect on local models.
        """
        err = validate_effort_thinking(effort, disable_thinking)
        if err:
            raise ValueError(err)

        temperature = OPUS5_EFFORT_BUDGETS.get(effort, 0.7) if effort else 0.7
        if fast:
            temperature = min(temperature, 0.3)  # Lower temperature for fast mode

        return self._client.call(
            prompt,
            system=system,
            temperature=temperature,
            max_tokens=self.max_tokens,
        )

    def call_text(self, prompt: str, **kwargs) -> str:
        return self._client.call_text(prompt, **kwargs)


# ── Re-export for backward compatibility ─────────────────────────────────


__all__ = [
    "OPUS5_MODEL_ID",
    "OPUS5_EFFORT_BUDGETS",
    "OPUS5_EFFORT_LEVELS",
    "OPUS5_THINKING_DISABLE_ALLOWED",
    "OPUS5_INFO",
    "validate_effort_thinking",
    "validate_inference_geo",
    "Opus5Client",
    "estimate_cost_usd",
    "cmd_opus5_info",
    "cmd_opus5_call",
]


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    """Estimate cost — ZCoder models are free when run locally."""
    return 0.0


def cmd_opus5_info():
    """Print ZCoder Pro capability table (refactored from Claude Opus 5 info)."""
    info = OPUS5_INFO
    print(f"\n\033[94mZCoder Pro (via Ollama)\033[0m  ({OPUS5_MODEL_ID})")
    print(f"  Model ID:          {OPUS5_MODEL_ID}")
    print(f"  Context window:    {info['context_window']:,} tokens")
    print(f"  Max output:        {info['max_output_tokens']:,} tokens")
    print(f"  Size:              {info['size_gb']} GB ({info['quant']})")
    print("  Pricing:           Free (local inference via Ollama)")
    print(f"  Effort levels:     {', '.join(info['effort_levels'])}")
    print(f"  Fast mode:         {'supported' if info['fast_mode_supported'] else 'not supported'}")
    print("\n  \033[93mNote:\033[0m Refactored from Claude Opus 5 module.")
    print("    --opus5 now calls zcoder-pro via Ollama (local provider).")
    print("    No API key or internet required.\n")
    print(f"  Notes: {info['notes']}\n")


def cmd_opus5_call(
    prompt: str,
    api_key: str | None = None,  # Ignored — Ollama doesn't need API key
    effort: str | None = None,
    disable_thinking: bool = False,
    fast: bool = False,
    use_geo: bool = False,
    system: str | None = None,
):
    """Call zcoder-pro via Ollama (refactored from Claude Opus 5 call)."""
    client = Opus5Client(base_url=DEFAULT_OLLAMA_BASE_URL)
    try:
        data = client.call(
            prompt,
            system=system,
            effort=effort,
            disable_thinking=disable_thinking,
            fast=fast,
            use_geo=use_geo,
        )
    except ValueError as e:
        print(f"\033[91m✗ {e}\033[0m")
        return None

    if "error" in data:
        print(f"[ERROR] {data['error']}")
        return None

    # Extract text from the already-fetched data (avoid double API call)
    msg = data.get("message", {})
    if isinstance(msg, dict):
        text = msg.get("content", "")
    else:
        text = data.get("response", "")
    print(text)
    return data
