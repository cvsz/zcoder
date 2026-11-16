"""
zcoder_haiku45.py — ZCoder Max support via Ollama (refactored from Claude Haiku 4.5)
ZCoder CLI v1.33.0

Refactored from claude_haiku45.py to work with ZCoder's own models running
locally on Ollama instead of Claude Haiku 4.5 via Anthropic API.

--haiku45 now maps to zcoder-max (ZCoder's largest model, BF16 precision)
via Ollama.
No API key or internet required.

CLI flags:
  --haiku45-info           Show ZCoder Max capability table
  --haiku45 PROMPT         Call zcoder-max via Ollama (replaces Claude Haiku 4.5)
  --haiku45-effort LEVEL   Effort level (low/medium/high/max) — mapped to temperature
  --haiku45-disable-thinking Accepted for compatibility, ignored (ZCoder models)
  --haiku45-fast           Send faster inference (lower temperature)
  --haiku45-thinking-budget Accepted for compatibility, ignored (ZCoder models)
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
# --haiku45 → zcoder-max (largest model, BF16 precision, highest quality)
HAIKU45_MODEL_ID = "zcoder-max"

HAIKU45_EFFORT_BUDGETS = {
    "low": 0.3,
    "medium": 0.5,
    "high": 0.7,
    "max": 0.9,
}
HAIKU45_EFFORT_LEVELS = list(HAIKU45_EFFORT_BUDGETS.keys())
HAIKU45_THINKING_DISABLE_ALLOWED = {"low", "medium", "high", "max"}

HAIKU45_INFO: dict[str, Any] = {
    "display_name": "ZCoder Max (via Ollama)",
    "model_id": HAIKU45_MODEL_ID,
    "tier": "current",
    "context_window": 32_768,
    "max_output_tokens": 8192,
    "size_gb": 18.4,
    "quant": "9B BF16",
    "effort_levels": HAIKU45_EFFORT_LEVELS,
    "fast_mode_supported": True,
    "notes": "Refactored from Claude Haiku 4.5 module. Now calls zcoder-max "
    "via Ollama (local provider). No API key or internet required.",
}


def validate_effort_thinking(effort: str | None, disable_thinking: bool) -> str | None:
    """Validate effort/thinking combination for ZCoder Max.

    ZCoder models don't have the same thinking restrictions as Claude Haiku 4.5,
    so this is a compatibility shim that accepts all combinations.
    """
    if effort is not None and effort not in HAIKU45_EFFORT_LEVELS:
        return (
            f"unknown effort level '{effort}' for ZCoder Max — choose from {', '.join(HAIKU45_EFFORT_LEVELS)}"
        )
    return None


def validate_inference_geo(use_geo: bool) -> str | None:
    """Inference geo is not applicable to local Ollama models."""
    return None


class Haiku45Client:
    """ZCoder Max client via Ollama (refactored from Claude Haiku 4.5 client).

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
            model=HAIKU45_MODEL_ID,
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
        thinking_budget: int | None = None,  # Accepted for compatibility, ignored
    ) -> dict:
        """Build and send one request to zcoder-max via Ollama.

        effort maps to temperature. disable_thinking, use_geo, and
        thinking_budget are accepted for compatibility but have no effect
        on local models.
        """
        err = validate_effort_thinking(effort, disable_thinking)
        if err:
            raise ValueError(err)

        temperature = HAIKU45_EFFORT_BUDGETS.get(effort, 0.7) if effort else 0.7
        if fast:
            temperature = min(temperature, 0.3)

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
    "HAIKU45_MODEL_ID",
    "HAIKU45_EFFORT_BUDGETS",
    "HAIKU45_EFFORT_LEVELS",
    "HAIKU45_THINKING_DISABLE_ALLOWED",
    "HAIKU45_INFO",
    "validate_effort_thinking",
    "validate_inference_geo",
    "Haiku45Client",
    "estimate_cost_usd",
    "cmd_haiku45_info",
    "cmd_haiku45_call",
]


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    """Estimate cost — ZCoder models are free when run locally."""
    return 0.0


def cmd_haiku45_info():
    """Print ZCoder Max capability table (refactored from Claude Haiku 4.5 info)."""
    info = HAIKU45_INFO
    print(f"\n\033[94mZCoder Max (via Ollama)\033[0m  ({HAIKU45_MODEL_ID})")
    print(f"  Model ID:          {HAIKU45_MODEL_ID}")
    print(f"  Context window:    {info['context_window']:,} tokens")
    print(f"  Max output:        {info['max_output_tokens']:,} tokens")
    print(f"  Size:              {info['size_gb']} GB ({info['quant']})")
    print("  Pricing:           Free (local inference via Ollama)")
    print(f"  Effort levels:     {', '.join(info['effort_levels'])}")
    print(f"  Fast mode:         {'supported' if info['fast_mode_supported'] else 'not supported'}")
    print("\n  \033[93mNote:\033[0m Refactored from Claude Haiku 4.5 module.")
    print("    --haiku45 now calls zcoder-max via Ollama (local provider).")
    print("    No API key or internet required.\n")
    print(f"  Notes: {info['notes']}\n")


def cmd_haiku45_call(
    prompt: str,
    api_key: str | None = None,  # Ignored — Ollama doesn't need API key
    effort: str | None = None,
    disable_thinking: bool = False,
    fast: bool = False,
    use_geo: bool = False,
    thinking_budget: int | None = None,
    system: str | None = None,
):
    """Call zcoder-max via Ollama (refactored from Claude Haiku 4.5 call)."""
    client = Haiku45Client(base_url=DEFAULT_OLLAMA_BASE_URL)
    try:
        data = client.call(
            prompt,
            system=system,
            effort=effort,
            disable_thinking=disable_thinking,
            fast=fast,
            use_geo=use_geo,
            thinking_budget=thinking_budget,
        )
    except ValueError as e:
        print(f"\033[91m✗ {e}\033[0m")
        return None

    if "error" in data:
        print(f"[ERROR] {data['error']}")
        return None

    # Extract text from already-fetched data (avoid double API call)
    msg = data.get("message", {})
    if isinstance(msg, dict):
        text = msg.get("content", "")
    else:
        text = data.get("response", "")
    print(text)
    return data
