"""
zcoder_sonnet5.py — ZCoder ProMax support via Ollama (refactored from Claude Sonnet 5)
ZCoder CLI v1.33.0

Refactored from claude_sonnet5.py to work with ZCoder's own models running
locally on Ollama instead of Claude Sonnet 5 via Anthropic API.

--sonnet5 now maps to zcoder-promax (ZCoder's large reasoning model) via Ollama.
No API key or internet required.

CLI flags:
  --sonnet5-info           Show ZCoder ProMax capability table
  --sonnet5 PROMPT         Call zcoder-promax via Ollama (replaces Claude Sonnet 5)
  --sonnet5-effort LEVEL   Effort level (low/medium/high/max) — mapped to temperature
  --sonnet5-disable-thinking Accepted for compatibility, ignored (ZCoder models)
  --sonnet5-geo            Accepted for compatibility, ignored (local model)
  --sonnet5-fast           Send faster inference (lower temperature)
  --sonnet5-cost IN,OUT    Estimate cost — always 0 (free, local inference)
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
# --sonnet5 → zcoder-promax (large reasoning model)
SONNET5_MODEL_ID = "zcoder-promax"

SONNET5_EFFORT_BUDGETS = {
    "low": 0.3,
    "medium": 0.5,
    "high": 0.7,
    "max": 0.9,
}
SONNET5_EFFORT_LEVELS = list(SONNET5_EFFORT_BUDGETS.keys())
SONNET5_THINKING_DISABLE_ALLOWED = {"low", "medium", "high", "max"}

SONNET5_INFO: dict[str, Any] = {
    "display_name": "ZCoder ProMax (via Ollama)",
    "model_id": SONNET5_MODEL_ID,
    "tier": "current",
    "context_window": 32_768,
    "max_output_tokens": 8192,
    "size_gb": 16.8,
    "quant": "27B Q4_K",
    "effort_levels": SONNET5_EFFORT_LEVELS,
    "fast_mode_supported": True,
    "notes": "Refactored from Claude Sonnet 5 module. Now calls zcoder-promax "
    "via Ollama (local provider). No API key or internet required.",
}


def validate_effort_thinking(effort: str | None, disable_thinking: bool) -> str | None:
    """Validate effort/thinking combination for ZCoder ProMax.

    ZCoder models don't have the same thinking restrictions as Claude Sonnet 5,
    so this is a compatibility shim that accepts all combinations.
    """
    if effort is not None and effort not in SONNET5_EFFORT_LEVELS:
        return f"unknown effort level '{effort}' for ZCoder ProMax — choose from {', '.join(SONNET5_EFFORT_LEVELS)}"
    return None


def validate_inference_geo(use_geo: bool) -> str | None:
    """Inference geo is not applicable to local Ollama models."""
    return None


class Sonnet5Client:
    """ZCoder ProMax client via Ollama (refactored from Claude Sonnet 5 client).

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
            model=SONNET5_MODEL_ID,
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
        """Build and send one request to zcoder-promax via Ollama.

        effort maps to temperature. disable_thinking and use_geo are
        accepted for compatibility but have no effect on local models.
        """
        err = validate_effort_thinking(effort, disable_thinking)
        if err:
            raise ValueError(err)

        temperature = SONNET5_EFFORT_BUDGETS.get(effort, 0.7) if effort else 0.7
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
    "SONNET5_MODEL_ID",
    "SONNET5_EFFORT_BUDGETS",
    "SONNET5_EFFORT_LEVELS",
    "SONNET5_THINKING_DISABLE_ALLOWED",
    "SONNET5_INFO",
    "validate_effort_thinking",
    "validate_inference_geo",
    "Sonnet5Client",
    "estimate_cost_usd",
    "STANDARD_PRICE_IN_USD",
    "STANDARD_PRICE_OUT_USD",
    "current_pricing",
    "cmd_sonnet5_cost",
    "cmd_sonnet5_info",
    "cmd_sonnet5_call",
]

# ราคาอ้างอิงของ catalog claude-sonnet-5 (USD ต่อ MTok) สำหรับ conformance และ
# compatibility เท่านั้น ไม่ได้ใช้คิดค่าใช้จ่าย local inference (ดู estimate_cost_usd)
STANDARD_PRICE_IN_USD = 2.0
STANDARD_PRICE_OUT_USD = 10.0


def current_pricing() -> dict[str, Any]:
    """Return reference catalog pricing for claude-sonnet-5 (ไม่มี network call)."""
    return {"price_in": STANDARD_PRICE_IN_USD, "price_out": STANDARD_PRICE_OUT_USD, "promo_active": False}


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    """Estimate cost — ZCoder models are free when run locally."""
    return 0.0


def cmd_sonnet5_cost(spec: str) -> None:
    """Parse 'IN,OUT' token counts; print local cost (0) and the catalog reference cost."""
    try:
        in_tok, out_tok = (int(x.strip()) for x in spec.split(","))
    except ValueError:
        print("[ERROR] --sonnet5-cost expects 'INPUT_TOKENS,OUTPUT_TOKENS', e.g. 10000,2000")
        return
    if in_tok < 0 or out_tok < 0:
        print("[ERROR] token counts must be non-negative")
        return
    pricing = current_pricing()
    reference = (in_tok * pricing["price_in"] + out_tok * pricing["price_out"]) / 1_000_000
    print(f"\n  {in_tok:,} input + {out_tok:,} output tokens")
    print(f"  local ({SONNET5_MODEL_ID} via Ollama): \033[1m${estimate_cost_usd(in_tok, out_tok):.4f}\033[0m")
    print(
        f"  reference catalog rate (${pricing['price_in']}/${pricing['price_out']} per MTok): ${reference:.4f}\n"
    )


def cmd_sonnet5_info():
    """Print ZCoder ProMax capability table (refactored from Claude Sonnet 5 info)."""
    info = SONNET5_INFO
    print(f"\n\033[94mZCoder ProMax (via Ollama)\033[0m  ({SONNET5_MODEL_ID})")
    print(f"  Model ID:          {SONNET5_MODEL_ID}")
    print(f"  Context window:    {info['context_window']:,} tokens")
    print(f"  Max output:        {info['max_output_tokens']:,} tokens")
    print(f"  Size:              {info['size_gb']} GB ({info['quant']})")
    print("  Pricing:           Free (local inference via Ollama)")
    print(f"  Effort levels:     {', '.join(info['effort_levels'])}")
    print(f"  Fast mode:         {'supported' if info['fast_mode_supported'] else 'not supported'}")
    print("\n  \033[93mNote:\033[0m Refactored from Claude Sonnet 5 module.")
    print("    --sonnet5 now calls zcoder-promax via Ollama (local provider).")
    print("    No API key or internet required.\n")
    print(f"  Notes: {info['notes']}\n")


def cmd_sonnet5_call(
    prompt: str,
    api_key: str | None = None,  # Ignored — Ollama doesn't need API key
    effort: str | None = None,
    disable_thinking: bool = False,
    fast: bool = False,
    use_geo: bool = False,
    system: str | None = None,
):
    """Call zcoder-promax via Ollama (refactored from Claude Sonnet 5 call)."""
    client = Sonnet5Client(base_url=DEFAULT_OLLAMA_BASE_URL)
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

    # Extract text from already-fetched data (avoid double API call)
    msg = data.get("message", {})
    if isinstance(msg, dict):
        text = msg.get("content", "")
    else:
        text = data.get("response", "")
    print(text)
    return data
