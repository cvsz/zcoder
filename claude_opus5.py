"""
claude_opus5.py — Claude Opus 5 support (deep, model-specific module)
AI Model Coder CLI v1.33.0

Why this module exists: claude_models.py's MODEL_CATALOG carries a single
short entry for claude-opus-5 (context window, price, one "notes" string),
the same shallow shape every other row gets. That's fine as an index, but
it under-serves Opus 5 specifically, because Opus 5 shipped with a real
breaking change baked into its request validation that a flat notes string
can't express as executable logic: effort and thinking interact in a way
they didn't on Opus 4.8, and getting it wrong is a 400, not a silent
downgrade. This module gives Opus 5 the same treatment claude_fable5.py /
claude_mythos5.py already get — a dedicated info table, a client that
validates requests before sending them, and CLI commands — rather than
leaving callers to discover the effort/thinking interaction via a failed
API call.

Source: platform.claude.com/docs/en/about-claude/models/overview and the
2026-07-24 Opus 5 release notes, checked 2026-07-26. Opus 5 launched
2026-07-24 (two days before this module was written), so treat anything
here as newer and less battle-tested than the Opus 4.8 module it
supersedes — re-verify against the live docs before relying on this for
billing- or correctness-sensitive decisions.

What's specific to Opus 5, concretely:
  • Thinking is ON by default (unlike Opus 4.8, where adaptive thinking is
    on but effort_default is "high" with no stated always-on behavior).
  • A full five-rung effort ladder: low / medium / high / xhigh / max.
    claude_models.EFFORT_BUDGETS only defines low/medium/high/max — it
    predates Opus 5 and has no "xhigh" entry. OPUS5_EFFORT_BUDGETS below
    is the authoritative table for this model; use it instead of (not
    blended with) the shared table when the model is Opus 5.
  • BREAKING CHANGE vs. Opus 4.8: disabling thinking
    (`thinking: {"type": "disabled"}`) is only accepted at effort "high"
    or below. Sending `effort: "xhigh"` or `effort: "max"` together with
    thinking disabled returns HTTP 400 — this is not a documented
    graceful downgrade to standard thinking, it's a hard rejection.
    validate_effort_thinking() below catches this client-side so callers
    get a clear message instead of an opaque 400 from the API.
  • Fast mode (`speed: "fast"`) is supported on Opus 5 — it's one of the
    two models in claude_models.FAST_MODE_SUPPORTED. Imported here rather
    than redefined, so the two modules can't drift out of sync.
  • service_tier ("auto" / "standard_only"): Opus 5 is NOT in
    claude_models.SERVICE_TIER_UNSUPPORTED, so Priority Tier capacity
    (for orgs with an existing commitment) applies normally.
  • inference_geo ("us" / "global"): as of this catalog's last check,
    claude-opus-5 is NOT listed in claude_models.INFERENCE_GEO_SUPPORTED.
    That set was last updated 2026-07-02, three weeks before Opus 5
    existed, so this is very plausibly a documentation gap rather than a
    deliberate exclusion — but until it's confirmed one way or the other,
    this module treats `inference_geo` on Opus 5 as UNCONFIRMED and warns
    rather than silently allowing or silently blocking it.

CLI flags:
  --opus5-info                  Show Opus 5's capability table (effort ladder,
                                 thinking rules, fast mode, service tier, geo)
  --opus5 PROMPT                Call Claude Opus 5
  --opus5-effort LEVEL          low|medium|high|xhigh|max (default: model default,
                                 i.e. adaptive with thinking on)
  --opus5-disable-thinking      Turn thinking off. Rejected client-side (not sent
                                 to the API) if combined with --opus5-effort xhigh
                                 or max — see breaking-change note above.
  --opus5-fast                  Send speed:"fast" (supported on this model)
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

OPUS5_MODEL_ID = "claude-opus-5"

# Authoritative for Opus 5 — do not fall back to claude_models.EFFORT_BUDGETS,
# which has no "xhigh" rung and predates this model.
OPUS5_EFFORT_BUDGETS = {
    "low":    2_000,
    "medium": 8_000,
    "high":   16_000,
    "xhigh":  24_000,
    "max":    32_000,
}
OPUS5_EFFORT_LEVELS = list(OPUS5_EFFORT_BUDGETS.keys())

# Effort levels at which thinking MAY be disabled. xhigh/max + disabled = 400.
OPUS5_THINKING_DISABLE_ALLOWED = {"low", "medium", "high"}

OPUS5_INFO = {
    "display_name":       "Claude Opus 5",
    "tier":               "current",
    "launched":           "2026-07-24",
    "context_window":     1_000_000,
    "max_output_tokens":  128_000,
    "price_input_per_mtok_usd":  5.0,
    "price_output_per_mtok_usd": 25.0,
    "thinking_default":   "on (adaptive)",
    "effort_levels":      OPUS5_EFFORT_LEVELS,
    "fast_mode_supported": OPUS5_MODEL_ID in FAST_MODE_SUPPORTED,
    "service_tier_supported": OPUS5_MODEL_ID not in SERVICE_TIER_UNSUPPORTED,
    "inference_geo_supported": OPUS5_MODEL_ID in INFERENCE_GEO_SUPPORTED,
    "notes": "A step-change over Opus 4.8 at the same per-token price. "
             "Breaking change vs. Opus 4.8: thinking can only be disabled "
             "at effort high or below.",
}


def validate_effort_thinking(effort: Optional[str], disable_thinking: bool) -> Optional[str]:
    """Return None if this effort/thinking combination is safe to send to
    Opus 5, or a human-readable reason string if the API would 400 it.
    Callers should treat a non-None return as a hard stop, not a warning —
    unlike validate_fast_mode()'s REMOVED_SILENT case, there's no graceful
    degradation here."""
    if not disable_thinking:
        return None
    if effort is None:
        # No effort given at all defaults toward the low end in practice,
        # but we don't know the API's exact default resolution — be
        # conservative and only clear combinations we can confirm are safe.
        return None
    if effort not in OPUS5_EFFORT_LEVELS:
        return (f"unknown effort level '{effort}' for Opus 5 — choose from "
                f"{', '.join(OPUS5_EFFORT_LEVELS)}")
    if effort not in OPUS5_THINKING_DISABLE_ALLOWED:
        return (f"Opus 5 rejects thinking disabled at effort '{effort}' (HTTP 400). "
                f"Thinking can only be disabled at effort {', '.join(sorted(OPUS5_THINKING_DISABLE_ALLOWED))}. "
                f"Either drop --opus5-disable-thinking or lower --opus5-effort.")
    return None


def validate_inference_geo(use_geo: bool) -> Optional[str]:
    """Opus 5 is absent from claude_models.INFERENCE_GEO_SUPPORTED as of
    the 2026-07-02 catalog check, which predates this model's 2026-07-24
    launch — so treat this as unconfirmed rather than a confident yes/no."""
    if not use_geo:
        return None
    if OPUS5_MODEL_ID in INFERENCE_GEO_SUPPORTED:
        return None
    return ("inference_geo support for claude-opus-5 is unconfirmed (the shared "
            "INFERENCE_GEO_SUPPORTED list predates this model's launch by three "
            "weeks and has not been re-checked against live docs). Sending "
            "inference_geo may 400. Verify at platform.claude.com/docs before relying on this.")


class Opus5Client:
    """Messages API client for claude-opus-5 with client-side validation of
    the effort/thinking interaction, so a bad combination fails fast with a
    clear message instead of a bare 400 from the API. Follows the same
    _post() pattern as Fable5Client / Mythos5Client for consistency."""

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
             effort: Optional[str] = None, disable_thinking: bool = False,
             fast: bool = False, use_geo: bool = False) -> dict:
        """Build and send one request. Raises ValueError client-side for
        combinations the API is documented to reject, rather than sending
        a request known in advance to 400."""
        err = validate_effort_thinking(effort, disable_thinking)
        if err:
            raise ValueError(err)
        if fast and OPUS5_MODEL_ID not in FAST_MODE_SUPPORTED:
            raise ValueError("fast mode is not supported on claude-opus-5 per the shared catalog")
        geo_warning = validate_inference_geo(use_geo)

        payload = {
            "model": OPUS5_MODEL_ID,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            payload["system"] = system
        if effort:
            payload["effort"] = effort
        if disable_thinking:
            payload["thinking"] = {"type": "disabled"}
        if fast:
            payload["speed"] = "fast"
        if use_geo:
            payload["inference_geo"] = "us"

        data = self._post(payload)
        if geo_warning and "error" not in data:
            data["_geo_warning"] = geo_warning
        return data

    def call_text(self, prompt: str, **kwargs) -> str:
        data = self.call(prompt, **kwargs)
        if "error" in data:
            return f"[ERROR] {data['error']}"
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens / 1_000_000 * OPUS5_INFO["price_input_per_mtok_usd"] +
            output_tokens / 1_000_000 * OPUS5_INFO["price_output_per_mtok_usd"])


def cmd_opus5_info():
    info = OPUS5_INFO
    print(f"\n\033[94mClaude Opus 5\033[0m  ({OPUS5_MODEL_ID})")
    print(f"  Launched:          {info['launched']}")
    print(f"  Context window:    {info['context_window']:,} tokens")
    print(f"  Max output:        {info['max_output_tokens']:,} tokens")
    print(f"  Pricing:           ${info['price_input_per_mtok_usd']}/MTok in, "
          f"${info['price_output_per_mtok_usd']}/MTok out")
    print(f"  Thinking default:  {info['thinking_default']}")
    print(f"  Effort ladder:     {', '.join(info['effort_levels'])}")
    print(f"  Fast mode:         {'supported' if info['fast_mode_supported'] else 'not supported'}")
    print(f"  Priority Tier:     {'supported' if info['service_tier_supported'] else 'not supported'}")
    print(f"  Data residency:    {'supported' if info['inference_geo_supported'] else 'unconfirmed — see module notes'}")
    print(f"\n  \033[93m⚠ Breaking change vs Opus 4.8:\033[0m thinking can only be disabled")
    print(f"    at effort high or below. --opus5-disable-thinking + --opus5-effort")
    print(f"    xhigh/max is rejected client-side here rather than sent as a 400.")
    print(f"\n  Notes: {info['notes']}\n")


def cmd_opus5_call(prompt: str, api_key: str, effort: Optional[str] = None,
                   disable_thinking: bool = False, fast: bool = False,
                   use_geo: bool = False, system: Optional[str] = None):
    client = Opus5Client(api_key=api_key)
    try:
        data = client.call(prompt, system=system, effort=effort,
                           disable_thinking=disable_thinking, fast=fast, use_geo=use_geo)
    except ValueError as e:
        print(f"\033[91m✗ {e}\033[0m")
        return None

    if "error" in data:
        print(f"[ERROR] {data['error']}")
        return None
    if data.get("_geo_warning"):
        print(f"\033[93mℹ {data['_geo_warning']}\033[0m\n")
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    print(text)
    return data
