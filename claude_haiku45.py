"""
claude_haiku45.py — Claude Haiku 4.5 support (deep, model-specific module)
AI Model Coder CLI v1.33.0

Why this module exists: MODEL_CATALOG's claude-haiku-4-5-20251001 row is
the one current-tier model whose thinking mode is "extended" rather than
"adaptive" — meaning a caller has to supply an explicit budget_tokens and
there is no model-decides-depth behavior to fall back on. Every generic
code path in this project that builds a `thinking` block by branching on
"is thinking supported" without also branching on *which kind* will send
Haiku 4.5 a request shaped for adaptive thinking, which this model does
not accept. This module makes that distinction load-bearing instead of a
one-line note: build_thinking_param() below is the one place that decides
the request shape for this model, so callers can't accidentally send the
wrong kind.

It also tracks the two other places Haiku 4.5 is the odd one out in the
shared catalogs: it is absent from claude_models.FAST_MODE_SUPPORTED
(fast mode is Opus-only) and absent from
claude_models.INFERENCE_GEO_SUPPORTED (data residency is Opus/Sonnet-5/
Mythos-class only, per the 2026-07-02 catalog check) — while it IS a
normal, unremarkable case for service_tier (not in
SERVICE_TIER_UNSUPPORTED, so Priority Tier works normally here, unlike
on Sonnet 5). Checked against platform.claude.com/docs, 2026-07-26.

CLI flags:
  --haiku45-info                  Show Haiku 4.5's capability table
  --haiku45 PROMPT                 Call Claude Haiku 4.5
  --haiku45-thinking-budget N       Enable extended thinking with an explicit
                                    budget_tokens=N (omit to call without thinking)
"""

import json
import urllib.request
import urllib.error
from typing import Optional

from claude_models import FAST_MODE_SUPPORTED, SERVICE_TIER_UNSUPPORTED, INFERENCE_GEO_SUPPORTED
from exceptions import AICoderError
from resilience import CircuitBreaker, retry, urlopen_json

MESSAGES_ENDPOINT = "https://api.anthropic.com/v1/messages"
_breaker = CircuitBreaker(failure_threshold=5, reset_timeout=30)

HAIKU45_MODEL_ID = "claude-haiku-4-5-20251001"
HAIKU45_ALIAS    = "claude-haiku-4-5"  # dateless alias, per claude_models.MODEL_ID_ALIASES

# Minimum budget_tokens the API accepts for extended thinking. Anthropic's
# docs specify 1024 as the floor for `thinking: {"type": "enabled", ...}`
# across models that support it in this manual-budget form.
MIN_THINKING_BUDGET = 1024

HAIKU45_INFO = {
    "display_name":      "Claude Haiku 4.5",
    "tier":              "current",
    "context_window":    200_000,
    "max_output_tokens": 64_000,
    "price_input_per_mtok_usd":  1.0,
    "price_output_per_mtok_usd": 5.0,
    "thinking":          "extended (manual budget_tokens — NOT adaptive)",
    "fast_mode_supported": HAIKU45_MODEL_ID in FAST_MODE_SUPPORTED,
    "service_tier_supported": HAIKU45_MODEL_ID not in SERVICE_TIER_UNSUPPORTED,
    "inference_geo_supported": HAIKU45_MODEL_ID in INFERENCE_GEO_SUPPORTED,
    "alias": HAIKU45_ALIAS,
    "notes": "Fastest, most cost-effective current-tier model. The only "
             "current model using extended (not adaptive) thinking — always "
             "pass an explicit budget_tokens, never type:'adaptive'.",
}


def resolve_model_id(model_id: str) -> str:
    """Normalize the dateless alias to the full ID this module's info
    table is keyed on, so callers can pass either form."""
    return HAIKU45_MODEL_ID if model_id == HAIKU45_ALIAS else model_id


def build_thinking_param(budget_tokens: Optional[int]) -> Optional[dict]:
    """Build the `thinking` request block for Haiku 4.5, or None to omit
    it entirely. Always returns the *extended* (manual-budget) shape —
    {"type": "enabled", "budget_tokens": N} — never {"type": "adaptive"},
    which this model does not support. Raises ValueError if budget_tokens
    is below the documented floor."""
    if budget_tokens is None:
        return None
    if budget_tokens < MIN_THINKING_BUDGET:
        raise ValueError(
            f"budget_tokens must be >= {MIN_THINKING_BUDGET} for extended thinking; got {budget_tokens}"
        )
    return {"type": "enabled", "budget_tokens": budget_tokens}


def validate_fast_mode(want_fast: bool) -> Optional[str]:
    if not want_fast:
        return None
    if HAIKU45_MODEL_ID in FAST_MODE_SUPPORTED:
        return None
    return ("fast mode (speed:\"fast\") is restricted to Opus models per "
            "claude_models.FAST_MODE_SUPPORTED — not available on Haiku 4.5.")


def validate_inference_geo(use_geo: bool) -> Optional[str]:
    if not use_geo:
        return None
    if HAIKU45_MODEL_ID in INFERENCE_GEO_SUPPORTED:
        return None
    return ("inference_geo data residency is not supported on Haiku 4.5 per "
            "claude_models.INFERENCE_GEO_SUPPORTED (Opus/Sonnet-5/Mythos-class "
            "only as of the 2026-07-02 catalog check) — sending it will 400.")


class Haiku45Client:
    """Messages API client for claude-haiku-4-5-20251001. Follows the same
    _post() pattern as the other claude_*.py per-model modules."""

    def __init__(self, api_key: str, max_tokens: int = 4096):
        self.api_key = api_key
        self.max_tokens = max_tokens

    @retry(max_attempts=4, base_delay=1.0, max_delay=15.0, breaker=_breaker)
    def _call(self, payload: dict) -> dict:
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }
        req = urllib.request.Request(
            MESSAGES_ENDPOINT, data=json.dumps(payload).encode(),
            headers=headers, method="POST",
        )
        return urlopen_json(req, timeout=300)

    def _post(self, payload: dict) -> dict:
        try:
            return self._call(payload)
        except AICoderError as e:
            return {"error": e.message, "status": getattr(e, "status_code", None)}
        except Exception as e:
            return {"error": str(e)}

    def call(self, prompt: str, system: Optional[str] = None,
             thinking_budget: Optional[int] = None, fast: bool = False,
             use_geo: bool = False) -> dict:
        fast_err = validate_fast_mode(fast)
        if fast_err:
            raise ValueError(fast_err)
        geo_err = validate_inference_geo(use_geo)
        if geo_err:
            raise ValueError(geo_err)

        thinking = build_thinking_param(thinking_budget)  # raises ValueError on bad budget

        payload = {
            "model": HAIKU45_MODEL_ID,
            "max_tokens": max(self.max_tokens, (thinking_budget or 0) + 1024),
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            payload["system"] = system
        if thinking:
            payload["thinking"] = thinking
        return self._post(payload)

    def call_text(self, prompt: str, **kwargs) -> str:
        data = self.call(prompt, **kwargs)
        if "error" in data:
            return f"[ERROR] {data['error']}"
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens / 1_000_000 * HAIKU45_INFO["price_input_per_mtok_usd"] +
            output_tokens / 1_000_000 * HAIKU45_INFO["price_output_per_mtok_usd"])


def cmd_haiku45_info():
    info = HAIKU45_INFO
    print(f"\n\033[94mClaude Haiku 4.5\033[0m  ({HAIKU45_MODEL_ID}, alias: {info['alias']})")
    print(f"  Context window:    {info['context_window']:,} tokens")
    print(f"  Max output:        {info['max_output_tokens']:,} tokens")
    print(f"  Pricing:           ${info['price_input_per_mtok_usd']}/MTok in, "
          f"${info['price_output_per_mtok_usd']}/MTok out")
    print(f"  Thinking:          {info['thinking']}")
    print(f"  Fast mode:         {'supported' if info['fast_mode_supported'] else 'NOT supported (Opus-only)'}")
    print(f"  Priority Tier:     {'supported' if info['service_tier_supported'] else 'not supported'}")
    print(f"  Data residency:    {'supported' if info['inference_geo_supported'] else 'NOT supported'}")
    print(f"\n  Notes: {info['notes']}\n")


def cmd_haiku45_call(prompt: str, api_key: str, thinking_budget: Optional[int] = None,
                     fast: bool = False, use_geo: bool = False, system: Optional[str] = None):
    client = Haiku45Client(api_key=api_key)
    try:
        data = client.call(prompt, system=system, thinking_budget=thinking_budget,
                           fast=fast, use_geo=use_geo)
    except ValueError as e:
        print(f"\033[91m✗ {e}\033[0m")
        return None
    if "error" in data:
        print(f"[ERROR] {data['error']}")
        return None
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    print(text)
    return data
