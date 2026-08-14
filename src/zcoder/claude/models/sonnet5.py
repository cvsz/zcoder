"""
claude_sonnet5.py — Claude Sonnet 5 support (deep, model-specific module)
AI Model Coder CLI v1.34.0

Why this module exists: MODEL_CATALOG's claude-sonnet-5 row carries a
flat price_in/price_out entry. This module provides deeper per-model
validation that a flat catalog entry can't express as executable logic.

Pricing history (for cost-estimator accuracy):
  * Jun 30, 2026 launch: introductory $2/$10 per MTok promised through Aug 31.
  * Aug 10, 2026: Anthropic cancelled the planned Sep 1 price increase.
    The $2/$10 introductory rate is now the permanent standard price.
  * No future price change currently announced.
  This module's previous PROMO_PRICE_IN/OUT and PROMO_END_DATE constants
  are kept for backward compatibility but are no longer used by
  current_pricing() — the function always returns the permanent $2/$10 rate.

It also surfaces the two API-parameter support facts that are easy to get
backwards for this specific model: Sonnet 5 is the one current-tier model
that does NOT support service_tier / Priority Tier (grouped in the shared
catalog with the Mythos-class models, not with the other Opus/Sonnet
rows), while it DOES support inference_geo data residency (grouped with
the Opus rows there instead). Checked against
platform.claude.com/docs/en/api/service-tiers and
platform.claude.com/docs/en/manage-claude/data-residency, 2026-07-26.

Also added 2026-07-26 (found while re-validating this model against the
live release notes): Sonnet 5 returns a 400 error if temperature, top_p,
or top_k is set to any non-default value at all — a stricter behavior
than most current-tier models, which simply accept non-default sampling
values. Nothing in this module previously exposed or guarded against
these parameters; `validate_sampling_params()` now catches this
client-side before a request is built.

CLI flags:
  --sonnet5-info                Show Sonnet 5's capability table and current pricing
  --sonnet5 PROMPT               Call Claude Sonnet 5
  --sonnet5-geo                  Send inference_geo:"us" (supported; 1.1x price)
  --sonnet5-cost IN,OUT           Estimate cost in USD for IN input / OUT output
                                  tokens, using whichever rate applies today
"""

import json
import urllib.request
import urllib.error
from datetime import date, datetime
from typing import Optional

from claude_models import SERVICE_TIER_UNSUPPORTED, INFERENCE_GEO_SUPPORTED, INFERENCE_GEO_PRICING_MULTIPLIER
from exceptions import AICoderError
from resilience import CircuitBreaker, retry, urlopen_json

MESSAGES_ENDPOINT = "https://api.anthropic.com/v1/messages"
_breaker = CircuitBreaker(failure_threshold=5, reset_timeout=30)

SONNET5_MODEL_ID = "claude-sonnet-5"

# Pricing history:
#   Jun 30, 2026: launched at $2/$10 per MTok introductory rate
#   Aug 10, 2026: planned increase to $3/$15 cancelled; $2/$10 is permanent standard price
PROMO_PRICE_IN_USD      = 2.0   # historical
PROMO_PRICE_OUT_USD     = 10.0  # historical
STANDARD_PRICE_IN_USD   = 2.0   # permanent standard rate
STANDARD_PRICE_OUT_USD  = 10.0  # permanent standard rate
from datetime import date
PROMO_END_DATE = date(2026, 8, 31)  # obsolete — increase was cancelled permanently

SONNET5_INFO = {
    "display_name":      "Claude Sonnet 5",
    "tier":              "current",
    "context_window":    1_000_000,
    "max_output_tokens": 128_000,
    "thinking":          "adaptive",
    "effort_default":    "high",
    "service_tier_supported": SONNET5_MODEL_ID not in SERVICE_TIER_UNSUPPORTED,
    "inference_geo_supported": SONNET5_MODEL_ID in INFERENCE_GEO_SUPPORTED,
    "inference_geo_multiplier": INFERENCE_GEO_PRICING_MULTIPLIER,
    "notes": "Best speed/intelligence balance; builds on Sonnet 4.6. "
             "Standard pricing is $2/$10 per MTok permanently. "
             "Unlike most current-tier models, does NOT support "
             "service_tier / Priority Tier.",
}


def current_pricing(as_of=None) -> dict:
    """Return the {'price_in', 'price_out', 'promo_active'} dict for Sonnet 5.
    On August 10, 2026, Anthropic cancelled the planned price increase;
    the $2/$10 per MTok rate is now the permanent standard price."""
    return {"price_in": STANDARD_PRICE_IN_USD, "price_out": STANDARD_PRICE_OUT_USD, "promo_active": False}




def estimate_cost_usd(input_tokens: int, output_tokens: int,
                      as_of: Optional[date] = None, use_geo: bool = False) -> float:
    """Cost estimate using whichever pricing tier applies on `as_of`
    (default: today). Applies the data-residency multiplier on top if
    use_geo=True, since inference_geo="us" pricing is 1.1x on both
    input and output per claude_models.INFERENCE_GEO_PRICING_MULTIPLIER."""
    pricing = current_pricing(as_of)
    multiplier = INFERENCE_GEO_PRICING_MULTIPLIER if use_geo else 1.0
    return (input_tokens / 1_000_000 * pricing["price_in"] * multiplier +
            output_tokens / 1_000_000 * pricing["price_out"] * multiplier)


def validate_service_tier(service_tier: Optional[str]) -> Optional[str]:
    """Return None if service_tier is safe to send for Sonnet 5 (i.e. not
    set at all), or a warning string if the caller is trying to use
    Priority Tier on a model that doesn't support it."""
    if service_tier is None:
        return None
    if SONNET5_MODEL_ID in SERVICE_TIER_UNSUPPORTED:
        return (f"claude-sonnet-5 does not support service_tier (grouped with the "
                f"Mythos-class models in claude_models.SERVICE_TIER_UNSUPPORTED). "
                f"Sending service_tier='{service_tier}' will likely be ignored or 400 — "
                f"omit it for this model.")
    return None


def validate_sampling_params(temperature: Optional[float] = None,
                             top_p: Optional[float] = None,
                             top_k: Optional[int] = None) -> Optional[str]:
    """Sonnet 5 returns a 400 error if temperature, top_p, or top_k is set
    to a non-default value at all — unlike most other current-tier models,
    where non-default sampling values are simply accepted. Per the
    release note checked 2026-07-26: 'setting sampling parameters
    (temperature, top_p, top_k) to non-default values returns a 400
    error' on Claude Sonnet 5. This was a genuine gap: nothing in this
    module (or `Sonnet5Client.call()`) previously exposed or guarded
    against these parameters at all. Returns None if none were passed
    (the only safe way to call this model), or a message string
    identifying which parameter(s) would 400."""
    offending = []
    if temperature is not None:
        offending.append(f"temperature={temperature}")
    if top_p is not None:
        offending.append(f"top_p={top_p}")
    if top_k is not None:
        offending.append(f"top_k={top_k}")
    if not offending:
        return None
    return (f"claude-sonnet-5 returns a 400 error if any sampling parameter is set "
            f"to a non-default value — {', '.join(offending)} would fail. Omit "
            f"these parameters entirely for this model (do not rely on it accepting "
            f"defaults passed explicitly).")


class Sonnet5Client:
    """Messages API client for claude-sonnet-5. Follows the same _post()
    pattern as the other claude_*.py per-model modules."""

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
             use_geo: bool = False, service_tier: Optional[str] = None,
             temperature: Optional[float] = None, top_p: Optional[float] = None,
             top_k: Optional[int] = None) -> dict:
        warning = validate_service_tier(service_tier)
        sampling_error = validate_sampling_params(temperature, top_p, top_k)
        if sampling_error:
            return {"error": sampling_error, "status": None}
        payload = {
            "model": SONNET5_MODEL_ID,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            payload["system"] = system
        if use_geo:
            payload["inference_geo"] = "us"
        if service_tier:
            payload["service_tier"] = service_tier
        data = self._post(payload)
        if warning and "error" not in data:
            data["_service_tier_warning"] = warning
        return data


def cmd_sonnet5_info():
    info = SONNET5_INFO
    pricing = current_pricing()
    print(f"\n\033[94mClaude Sonnet 5\033[0m  ({SONNET5_MODEL_ID})")
    print(f"  Context window:    {info['context_window']:,} tokens")
    print(f"  Max output:        {info['max_output_tokens']:,} tokens")
    print(f"  Thinking:          {info['thinking']} (effort default: {info['effort_default']})")
    print(f"  Priority Tier:     {'supported' if info['service_tier_supported'] else 'NOT supported'}")
    print(f"  Data residency:    {'supported' if info['inference_geo_supported'] else 'not supported'}"
          f" ({info['inference_geo_multiplier']}x pricing when used)")
    print(f"\n  Pricing today ({date.today().isoformat()}):")
    print(f"    ${pricing['price_in']}/${pricing['price_out']} per MTok (permanent standard rate)")
    print(f"    Note: the planned Sep 1, 2026 price increase was permanently cancelled "
          f"on Aug 7, 2026; ${STANDARD_PRICE_IN_USD}/${STANDARD_PRICE_OUT_USD} is the final standard price.")
    print(f"\n  Notes: {info['notes']}\n")


def cmd_sonnet5_call(prompt: str, api_key: str, use_geo: bool = False,
                     service_tier: Optional[str] = None, system: Optional[str] = None):
    client = Sonnet5Client(api_key=api_key)
    data = client.call(prompt, system=system, use_geo=use_geo, service_tier=service_tier)
    if "error" in data:
        print(f"[ERROR] {data['error']}")
        return None
    if data.get("_service_tier_warning"):
        print(f"\033[93mℹ {data['_service_tier_warning']}\033[0m\n")
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    print(text)
    return data


def cmd_sonnet5_cost(spec: str):
    """Parse 'IN,OUT' token counts and print a cost estimate at the current permanent rate."""
    try:
        in_tok, out_tok = (int(x.strip()) for x in spec.split(","))
    except ValueError:
        print("[ERROR] --sonnet5-cost expects 'INPUT_TOKENS,OUTPUT_TOKENS', e.g. 10000,2000")
        return
    cost = estimate_cost_usd(in_tok, out_tok)
    pricing = current_pricing()
    print(f"\n  {in_tok:,} input + {out_tok:,} output tokens on Sonnet 5")
    print(f"  at standard rate (${pricing['price_in']}/${pricing['price_out']} per MTok): "
          f"\033[1m${cost:.4f}\033[0m\n")
