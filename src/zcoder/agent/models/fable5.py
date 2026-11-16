"""
zcoder_fable5.py — ZCoder Flash support via Ollama (refactored from Claude Fable 5)
ZCoder CLI v1.33.0

Refactored from claude_fable5.py to work with ZCoder's own models running
locally on Ollama instead of Claude Fable 5 via Anthropic API.

--fable5 now maps to zcoder-flash (ZCoder's lightweight model) via Ollama.
No API key or internet required.

CLI flags:
  --fable5-info           Show ZCoder Flash capability table
  --fable5 PROMPT         Call zcoder-flash via Ollama (replaces Claude Fable 5)
  --fable5-effort LEVEL   Effort level (low/medium/high/max) — mapped to temperature
  --fable5-disable-thinking Accepted for compatibility, ignored (ZCoder models)
  --fable5-fast           Send faster inference (lower temperature)
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
# --fable5 → zcoder-flash (lightweight, fast model)
FABLE5_MODEL_ID = "zcoder-flash"

FABLE5_EFFORT_BUDGETS = {
    "low": 0.3,
    "medium": 0.5,
    "high": 0.7,
    "max": 0.9,
}
FABLE5_EFFORT_LEVELS = list(FABLE5_EFFORT_BUDGETS.keys())
FABLE5_THINKING_DISABLE_ALLOWED = {"low", "medium", "high", "max"}

FABLE5_INFO: dict[str, Any] = {
    "display_name": "ZCoder Flash (via Ollama)",
    "model_id": FABLE5_MODEL_ID,
    "tier": "current",
    "context_window": 32_768,
    "max_output_tokens": 8192,
    "size_gb": 1.1,
    "quant": "1.5B Q4_K",
    "effort_levels": FABLE5_EFFORT_LEVELS,
    "fast_mode_supported": True,
    "notes": "Refactored from Claude Fable 5 module. Now calls zcoder-flash "
    "via Ollama (local provider). No API key or internet required.",
}


def validate_effort_thinking(effort: str | None, disable_thinking: bool) -> str | None:
    """Validate effort/thinking combination for ZCoder Flash.

    ZCoder models don't have the same thinking restrictions as Claude Fable 5,
    so this is a compatibility shim that accepts all combinations.
    """
    if effort is not None and effort not in FABLE5_EFFORT_LEVELS:
        return f"unknown effort level '{effort}' for ZCoder Flash — choose from {', '.join(FABLE5_EFFORT_LEVELS)}"
    return None


def validate_inference_geo(use_geo: bool) -> str | None:
    """Inference geo is not applicable to local Ollama models."""
    return None


class Fable5Client:
    """ZCoder Flash client via Ollama (refactored from Claude Fable 5 client).

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
            model=FABLE5_MODEL_ID,
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
        """Build and send one request to zcoder-flash via Ollama.

        effort maps to temperature. disable_thinking and use_geo are
        accepted for compatibility but have no effect on local models.
        """
        err = validate_effort_thinking(effort, disable_thinking)
        if err:
            raise ValueError(err)

        temperature = FABLE5_EFFORT_BUDGETS.get(effort, 0.5) if effort else 0.5
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
    "FABLE5_MODEL_ID",
    "FABLE5_EFFORT_BUDGETS",
    "FABLE5_EFFORT_LEVELS",
    "FABLE5_THINKING_DISABLE_ALLOWED",
    "FABLE5_INFO",
    "validate_effort_thinking",
    "validate_inference_geo",
    "Fable5Client",
    "estimate_cost_usd",
    "cmd_fable5_info",
    "cmd_fable5_call",
    "parse_fallback_chain",
]


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    """Estimate cost — ZCoder models are free when run locally."""
    return 0.0


def cmd_fable5_info():
    """Print ZCoder Flash capability table (refactored from Claude Fable 5 info)."""
    info = FABLE5_INFO
    print(f"\n\033[94mZCoder Flash (via Ollama)\033[0m  ({FABLE5_MODEL_ID})")
    print(f"  Model ID:          {FABLE5_MODEL_ID}")
    print(f"  Context window:    {info['context_window']:,} tokens")
    print(f"  Max output:        {info['max_output_tokens']:,} tokens")
    print(f"  Size:              {info['size_gb']} GB ({info['quant']})")
    print("  Pricing:           Free (local inference via Ollama)")
    print(f"  Effort levels:     {', '.join(info['effort_levels'])}")
    print(f"  Fast mode:         {'supported' if info['fast_mode_supported'] else 'not supported'}")
    print("\n  \033[93mNote:\033[0m Refactored from Claude Fable 5 module.")
    print("    --fable5 now calls zcoder-flash via Ollama (local provider).")
    print("    No API key or internet required.\n")
    print(f"  Notes: {info['notes']}\n")


def cmd_fable5_call(
    prompt: str,
    api_key: str | None = None,  # Ignored — Ollama doesn't need API key
    fallback_model: str = "zcoder-pro",
    allow_fallback: bool = True,
    system: str | None = None,
    fallback_chain: list | None = None,
    effort: str | None = None,
    disable_thinking: bool = False,
    fast: bool = False,
    use_geo: bool = False,
):
    """Call zcoder-flash via Ollama (refactored from Claude Fable 5 call)."""
    client = Fable5Client(base_url=DEFAULT_OLLAMA_BASE_URL)
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


def parse_fallback_chain(raw: str | None):
    """Parse --fable5-fallback-chain CLI value (accepted for compatibility,
    but fallback chains are not applicable to local Ollama models)."""
    if not raw:
        return None
    chain = [m.strip() for m in raw.split(",") if m.strip()]
    return chain
