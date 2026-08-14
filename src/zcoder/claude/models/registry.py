"""
claude_models.py — Models API + Computer Use + Adaptive/Interleaved Thinking
AI Model Coder CLI v1.37.0

Covers:
  • Models API  — list available models, get model info
  • Model catalog — local capability/pricing table for current + legacy tiers,
    used as an offline fallback and to enrich --model-info with fields the
    live API's basic response doesn't always echo back in one place
  • Computer Use — control virtual desktop (screenshot, click, type)
  • Adaptive Thinking — model decides thinking depth automatically
  • Interleaved Thinking — think between tool calls (beta)
  • Fast mode — reduced latency mode for supported models
  • Effort levels — low / medium / high / max

CLI flags:
  --list-models            List all available Claude models
  --list-models-legacy     Include superseded (still-callable) models in the list
  --model-info ID          Get capabilities and context window for a model
                           (also checks the retired- and deprecated-model registries first)
  --check-deprecated PATH  Scan a file or directory for retired AND deprecated
                           (announced, not-yet-retired) model ID strings
  --computer-use PROMPT    Run a computer use task
  --adaptive-thinking      Enable adaptive thinking (model decides depth)
  --interleaved-thinking   Enable thinking between tool calls
  --fast-mode              Enable fast/reduced-latency mode
  --effort LEVEL           Set effort: low|medium|high|max
"""

import json
import urllib.error
import urllib.request
from typing import Optional

from exceptions import AICoderError
from resilience import CircuitBreaker, retry, urlopen_json

MODELS_ENDPOINT = "https://api.anthropic.com/v1/models"
MESSAGES_ENDPOINT = "https://api.anthropic.com/v1/messages"
_breaker = CircuitBreaker(failure_threshold=5, reset_timeout=30)


# ── Local model catalog ─────────────────────────────────────────────────────
# Source: platform.claude.com/docs/en/about-claude/models/overview, checked
# 2026-07-02. This is a convenience cache for offline use / enrichment —
# GET /v1/models/{id} on your own account is always the source of truth,
# since it reflects what your account can actually call right now.
#
# thinking: "adaptive" | "extended" | "both" | None
# tier:     "mythos" (above Opus) | "current" | "legacy" (superseded, still callable)

MODEL_CATALOG: dict = {
    "claude-opus-5": {
        "display_name": "Claude Opus 5",
        "tier": "current",
        "context_window": 1_000_000,
        "max_output": 128_000,
        "price_in": 5.0,
        "price_out": 25.0,
        "thinking": "adaptive",
        "effort_default": None,
        "notes": "Launched 2026-07-24, a step-change over Opus 4.8 at the same "
        "price. Thinking on by default. Full effort ladder (low/medium/"
        "high/xhigh/max). Breaking change vs. Opus 4.8: disabling thinking "
        "(thinking.type='disabled') is only allowed at effort high or "
        "below -- xhigh or max with thinking disabled returns a 400.",
    },
    "claude-mythos-5": {
        "display_name": "Claude Mythos 5",
        "tier": "mythos",
        "context_window": 1_000_000,
        "max_output": 128_000,
        "price_in": 10.0,
        "price_out": 50.0,
        "thinking": "adaptive",
        "effort_default": None,
        "notes": "Same underlying model as Fable 5, no safety classifiers. "
        "Project Glasswing invitation-only access.",
    },
    "claude-fable-5": {
        "display_name": "Claude Fable 5",
        "tier": "mythos",
        "context_window": 1_000_000,
        "max_output": 128_000,
        "price_in": 10.0,
        "price_out": 50.0,
        "thinking": "adaptive",
        "effort_default": None,
        "notes": "Anthropic's most capable widely-released model. Thinking is "
        "always on and returned encrypted — omit `thinking` rather "
        'than passing type:"disabled" (that returns a 400). Has '
        'safety classifiers that can return stop_reason="refusal".',
    },
    "claude-opus-4-8": {
        "display_name": "Claude Opus 4.8",
        "tier": "current",
        "context_window": 1_000_000,
        "max_output": 128_000,
        "price_in": 5.0,
        "price_out": 25.0,
        "thinking": "adaptive",
        "effort_default": "high",
        "notes": "Best for complex agentic coding and enterprise work. "
        "Adaptive thinking only — manual budget_tokens returns 400.",
    },
    "claude-sonnet-5": {
        "display_name": "Claude Sonnet 5",
        "tier": "current",
        "context_window": 1_000_000,
        "max_output": 128_000,
        "price_in": 2.0,
        "price_out": 10.0,
        "thinking": "adaptive",
        "effort_default": "high",
        "notes": "Best speed/intelligence balance; builds on Sonnet 4.6. "
        "Pricing $2/$10 per MTok (permanent — the planned Sep 1 "
        "increase was cancelled on 2026-08-10; the introductory rate is "
        "now the permanent standard price).",
    },
    "claude-haiku-4-5-20251001": {
        "display_name": "Claude Haiku 4.5",
        "tier": "current",
        "context_window": 200_000,
        "max_output": 64_000,
        "price_in": 1.0,
        "price_out": 5.0,
        "thinking": "extended",
        "effort_default": None,
        "notes": "Fastest, most cost-effective. Extended (manual budget_tokens) "
        "thinking, not adaptive. Alias: claude-haiku-4-5.",
    },
    # Legacy — still callable, superseded by the row above in the same tier.
    "claude-opus-4-7": {
        "display_name": "Claude Opus 4.7",
        "tier": "legacy",
        "context_window": 1_000_000,
        "max_output": 128_000,
        "price_in": 5.0,
        "price_out": 25.0,
        "thinking": "adaptive",
        "effort_default": None,
        "notes": "Superseded by Opus 4.8 (drop-in model-ID swap).",
    },
    "claude-opus-4-6": {
        "display_name": "Claude Opus 4.6",
        "tier": "legacy",
        "context_window": 1_000_000,
        "max_output": 128_000,
        "price_in": 5.0,
        "price_out": 25.0,
        "thinking": "adaptive",
        "effort_default": None,
        "notes": "Superseded by Opus 4.7 / 4.8.",
    },
    "claude-opus-4-5": {
        "display_name": "Claude Opus 4.5",
        "tier": "legacy",
        "context_window": 1_000_000,
        "max_output": 64_000,
        "price_in": 5.0,
        "price_out": 25.0,
        "thinking": "adaptive",
        "effort_default": None,
        "notes": "Superseded by later Opus releases.",
    },
    "claude-sonnet-4-6": {
        "display_name": "Claude Sonnet 4.6",
        "tier": "legacy",
        "context_window": 1_000_000,
        "max_output": 64_000,
        "price_in": 3.0,
        "price_out": 15.0,
        "thinking": "adaptive",
        "effort_default": None,
        "notes": "Superseded by Sonnet 5.",
    },
    "claude-sonnet-4-5": {
        "display_name": "Claude Sonnet 4.5",
        "tier": "legacy",
        "context_window": 1_000_000,
        "max_output": 64_000,
        "price_in": 3.0,
        "price_out": 15.0,
        "thinking": "adaptive",
        "effort_default": None,
        "notes": "Superseded by Sonnet 4.6 / 5.",
    },
}

TIER_ORDER = ["mythos", "current", "legacy"]

# ── Fast mode (research preview) ────────────────────────────────────────────
# Was referenced only in this module's docstring/CLI-flag list with no actual
# code path — `--fast-mode` wasn't a real argparse flag anywhere and nothing
# ever sent `speed: "fast"`. Per platform.claude.com/docs (checked
# 2026-07-02): fast mode sends `speed: "fast"` on the request, is currently
# restricted to Opus models, and is billed at a premium rate ($10/$50 per
# MTok on Opus 4.8 vs. its $5/$25 standard rate). Not available on the
# Batch API.
#
# Fast mode's *removal* behavior differs by model, checked against the
# July 24, 2026 and June 29, 2026 release notes:
#   - Opus 4.7 (removed 2026-07-24): speed:"fast" now returns an ERROR.
#     Unlike Opus 4.6, it does NOT fall back to standard speed.
#   - Opus 4.6 (removed 2026-06-29): speed:"fast" is silently ignored --
#     the request runs at standard speed/pricing with no error.
# Both sets used to be represented by a single unused FAST_MODE_DEPRECATED
# constant that nothing ever actually checked against — coder.py sent
# speed:"fast" unconditionally whenever --fast-mode was passed, regardless
# of model. See validate_fast_mode() below, wired into coder.Coder.generate().
FAST_MODE_SUPPORTED = {"claude-opus-5", "claude-opus-4-8"}
FAST_MODE_REMOVED_ERROR = {"claude-opus-4-7"}
FAST_MODE_REMOVED_SILENT = {"claude-opus-4-6"}


def validate_fast_mode(model_id: str) -> Optional[str]:
    """Return None if `speed: "fast"` is safe to send for model_id, or a
    human-readable reason string if it isn't (or won't do what the caller
    expects). Callers should treat FAST_MODE_REMOVED_ERROR as a hard stop
    (don't send the request — it will 400) and FAST_MODE_REMOVED_SILENT as
    a warning (safe to send, but it silently runs at standard speed/price,
    not fast)."""
    if model_id in FAST_MODE_REMOVED_ERROR:
        return (
            f"fast mode was removed for {model_id} on 2026-07-24 and now "
            f"returns an error (unlike Opus 4.6, it does not fall back to "
            f"standard speed) -- use claude-opus-5 or claude-opus-4-8 instead"
        )
    if model_id in FAST_MODE_REMOVED_SILENT:
        return (
            f"fast mode was removed for {model_id} on 2026-06-29 -- the "
            f"request will run at standard speed and standard pricing, "
            f"not fast, with no error"
        )
    if model_id not in FAST_MODE_SUPPORTED:
        return f"fast mode is not supported on {model_id}"
    return None


# ── Priority Tier / service_tier ────────────────────────────────────────────
# Was entirely absent from the project. Per platform.claude.com/docs/en/
# api/service-tiers (checked 2026-07-02): service_tier accepts "auto"
# (default — use Priority Tier capacity if your org has a commitment,
# falling back to standard) or "standard_only". Priority Tier capacity
# commitments are no longer available for purchase, but organizations with
# an existing commitment can keep using it through their contract end date.
# Supported on all available models EXCEPT Claude Sonnet 5, Claude Mythos
# Preview, and Claude Mythos 5.
SERVICE_TIER_UNSUPPORTED = {"claude-sonnet-5", "claude-mythos-preview", "claude-mythos-5"}

# ── Data residency / inference_geo ──────────────────────────────────────────
# Per platform.claude.com/docs/en/manage-claude/data-residency (checked
# 2026-07-02, re-confirmed 2026-08-13): inference_geo accepts "us" (inference
# stays in US data centers, 1.1x pricing on input+output) or "global"
# (default, standard pricing). Supported on Opus 4.6, Sonnet 4.6, and later
# models — including claude-opus-5 (confirmed 2026-08-13 via live docs search).
# Earlier models (Haiku 4.5 / Opus 4.5) 400 if it's set at all.
# claude_opus5.py's old note "inference_geo support for claude-opus-5 is
# unconfirmed" is now superseded; Opus 5 is confirmed supported at 1.1x.
INFERENCE_GEO_SUPPORTED = {
    "claude-opus-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-sonnet-5",
    "claude-sonnet-4-6",
    "claude-fable-5",
    "claude-mythos-5",
    "claude-mythos-preview",
}
INFERENCE_GEO_PRICING_MULTIPLIER = 1.1


# ── Retired models ──────────────────────────────────────────────────────────
# Unlike MODEL_CATALOG's "legacy" tier (superseded but still callable), these
# IDs now return API errors. Kept here so --model-info on an old pinned
# string gives a migration path instead of a bare 404, and so a codebase
# grep for these strings has a maintained reference for what to replace them
# with. Retirement dates per platform.claude.com/docs/en/about-claude/model-deprecations,
# checked 2026-08-13.
RETIRED_MODELS: dict = {
    "claude-opus-4-1-20250805": {
        "display_name": "Claude Opus 4.1",
        "retired": "2026-08-05",
        "replacement": "claude-opus-4-8",
        "notes": "Original Opus 4.1 release, retired after the 4.8 rollout.",
    },
    "claude-opus-4-20250514": {
        "display_name": "Claude Opus 4 (original 4.0)",
        "retired": "2026-06-15",
        "replacement": "claude-opus-4-8",
        "notes": "Dateless alias claude-opus-4-0 retired alongside it.",
    },
    "claude-opus-4-0": {
        "display_name": "Claude Opus 4 (original 4.0, dateless alias)",
        "retired": "2026-06-15",
        "replacement": "claude-opus-4-8",
        "notes": "Alias for claude-opus-4-20250514.",
    },
    "claude-sonnet-4-20250514": {
        "display_name": "Claude Sonnet 4 (original 4.0)",
        "retired": "2026-06-15",
        "replacement": "claude-sonnet-5",
        "notes": "Dateless alias claude-sonnet-4-0 retired alongside it. Anthropic's "
        "own migration notes point to claude-sonnet-4-6; claude-sonnet-5 is "
        "the current recommendation as of this catalog's last check.",
    },
    "claude-sonnet-4-0": {
        "display_name": "Claude Sonnet 4 (original 4.0, dateless alias)",
        "retired": "2026-06-15",
        "replacement": "claude-sonnet-5",
        "notes": "Alias for claude-sonnet-4-20250514.",
    },
    "claude-haiku-3-20240307": {
        "display_name": "Claude Haiku 3",
        "retired": "2026-02-19",
        "replacement": "claude-haiku-4-5-20251001",
        "notes": "Retired well before this catalog's other entries; flagged in case "
        "of very old pinned config.",
    },
}


def check_retired(model_id: str) -> Optional[dict]:
    """Return the retirement record for model_id, or None if it isn't a
    known-retired ID. Matched against RETIRED_MODELS only — an unknown ID
    that isn't in MODEL_CATALOG either is just unrecognized, not retired."""
    return RETIRED_MODELS.get(model_id)


# ── Deprecated (announced, not yet retired) models ──────────────────────────
# Distinct from RETIRED_MODELS: these IDs still work today but Anthropic has
# published a future retirement date for them. Added v1.37.0 after the
# project's own model catalog was found to have no way to represent this
# state at all — check_retired() only covers "already 404s".
# Per platform.claude.com/docs/en/about-claude/model-deprecations, checked
# 2026-07-27, re-verified 2026-08-13.
#
# v1.40.0 audit note: claude-opus-4-1-20250805 had retirement_scheduled
# 2026-08-05, which has now passed (today is 2026-08-13). Moved to
# RETIRED_MODELS below. This dict now has no entries but is kept for
# forward-compatibility with callers that read it.
DEPRECATED_MODELS: dict = {
    # (empty — all previously-deprecated models have now passed their
    # retirement dates; see RETIRED_MODELS for their entries)
}


def check_deprecated(model_id: str) -> Optional[dict]:
    """Return the deprecation record for model_id if Anthropic has announced
    a future retirement date for it, or None. A model can appear here and
    still work fine today — this is an early-warning check, not a block.
    Once the retirement date passes, move the entry to RETIRED_MODELS
    instead (this dict is not auto-expired)."""
    return DEPRECATED_MODELS.get(model_id)


# ── Models API ─────────────────────────────────────────────────────────────


class ModelsAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key

    @retry(max_attempts=4, base_delay=1.0, max_delay=15.0, breaker=_breaker)
    def _call(self, req: "urllib.request.Request") -> dict:
        return urlopen_json(req, timeout=30)

    def _get(self, url: str) -> dict:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            return self._call(req)
        except AICoderError as e:
            raise RuntimeError(f"Models API error: {e.message}") from e

    def list_models(self) -> list:
        data = self._get(MODELS_ENDPOINT)
        return data.get("data", [])

    def get_model(self, model_id: str) -> dict:
        return self._get(f"{MODELS_ENDPOINT}/{model_id}")


def cmd_list_models(api_key: str, include_legacy: bool = False):
    ma = ModelsAPI(api_key=api_key)
    try:
        models = ma.list_models()
        print(f"\n{'MODEL ID':<35}{'DISPLAY NAME':<35}{'CONTEXT'}")
        print("─" * 85)
        for m in models:
            mid = m.get("id", "")
            name = m.get("display_name", "")[:34]
            ctx = m.get("context_window", 0)
            ctx_str = f"{ctx//1000}K" if ctx else "—"
            print(f"{mid:<35}{name:<35}{ctx_str}")
        print(f"\n{len(models)} models available")
    except RuntimeError as e:
        # Offline: show the local catalog
        print(f"\n\033[93m⚠ Could not reach Models API: {e}\033[0m")
        print("\nKnown models (local catalog, verify against --model-info when online):")
        tiers = TIER_ORDER if include_legacy else ["mythos", "current"]
        for tier in tiers:
            rows = [(mid, info) for mid, info in MODEL_CATALOG.items() if info["tier"] == tier]
            if not rows:
                continue
            label = {
                "mythos": "Mythos-class (above Opus)",
                "current": "Current",
                "legacy": "Legacy (superseded, still callable)",
            }[tier]
            print(f"\n  \033[1m{label}\033[0m")
            for mid, info in rows:
                ctx = f"{info['context_window']//1000}K"
                print(
                    f"    {mid:<32}{info['display_name']:<24}{ctx:<7}"
                    f"${info['price_in']}/${info['price_out']} per MTok"
                )
        if not include_legacy:
            print("\n  (legacy models hidden — pass --list-models-legacy to include them)")
        print("\n  Mythos-tier note: Fable 5 and Mythos 5 share the same underlying model;")
        print("  Fable 5 additionally has safety classifiers for bio/cyber/LLM-R&D topics.")
        print("  Both were briefly suspended 2026-06-12 -> 2026-07-01 for US export-control")
        print("  compliance; access is restored. See anthropic.com/news/fable-mythos-access.")
        print("\n  Run --fable5-info / --mythos5-info for pricing, retention, and refusal-handling details.")


def cmd_model_info(model_id: str, api_key: str):
    retired = check_retired(model_id)
    if retired:
        print(f"\n  \033[91m✗ {model_id} was retired on {retired['retired']}\033[0m")
        print(f"    Was:         {retired['display_name']}")
        print(f"    Migrate to:  {retired['replacement']}")
        print(f"    Notes:       {retired['notes']}")
        print(
            "\n  API calls to this ID will fail — this isn't a live lookup, "
            "just the local retirement record. Continuing to check the live "
            "API and local catalog below in case the record above is stale:\n"
        )

    deprecated = check_deprecated(model_id)
    if deprecated:
        print(
            f"\n  \033[93m⚠ {model_id} is deprecated, retiring "
            f"{deprecated['retirement_scheduled']}\033[0m"
        )
        print(f"    Was:            {deprecated['display_name']}")
        print(f"    Announced:      {deprecated['deprecation_announced']}")
        print(f"    Migrate to:     {deprecated['replacement']}")
        print(f"    Notes:          {deprecated['notes']}")
        print("\n  Still works today — this is an early warning, not a failure. " "Continuing below:\n")

    ma = ModelsAPI(api_key=api_key)
    try:
        m = ma.get_model(model_id)
        print(f"\n  ID:             {m.get('id')}")
        print(f"  Display name:   {m.get('display_name')}")
        print(f"  Context window: {m.get('context_window', 0):,} tokens")
        print(f"  Created:        {m.get('created_at','')[:10]}")
        caps = m.get("capabilities")
        if caps:
            print("  Capabilities:")
            print(f"    Vision:              {caps.get('image_input', {}).get('supported')}")
            think = caps.get("thinking", {})
            types = think.get("types", {})
            print(f"    Adaptive thinking:    {types.get('adaptive', {}).get('supported', False)}")
            print(f"    Extended thinking:    {types.get('enabled', {}).get('supported', False)}")
            print(f"    Structured outputs:   {caps.get('structured_outputs', {}).get('supported')}")
            effort = caps.get("effort")
            if effort:
                levels = effort.get("levels") or effort.get("supported_levels")
                default = effort.get("default")
                if levels:
                    print(
                        f"    Effort levels:       {', '.join(levels)}"
                        f"{f' (default: {default})' if default else ''}"
                    )
                elif default:
                    print(f"    Effort default:      {default}")
    except RuntimeError as e:
        # Offline / unrecognized ID via API — fall back to the local catalog
        info = MODEL_CATALOG.get(model_id)
        if not info:
            if retired:
                # Already printed the retirement record above; the live-API
                # error here is expected (retired IDs 404/400), not new info.
                return
            print(f"[ERROR] {e}")
            return
        print("\n  \033[93m⚠ Live API unreachable — showing local catalog entry\033[0m")
        print(f"  ID:              {model_id}")
        print(f"  Display name:    {info['display_name']}")
        print(f"  Tier:            {info['tier']}")
        print(f"  Context window:  {info['context_window']:,} tokens")
        print(f"  Max output:      {info['max_output']:,} tokens")
        print(f"  Pricing:         ${info['price_in']}/MTok in, ${info['price_out']}/MTok out")
        print(f"  Thinking mode:   {info['thinking']}")
        if info["effort_default"]:
            print(f"  Effort default:  {info['effort_default']}")
        print(f"  Notes:           {info['notes']}")


def cmd_check_deprecated(path: str):
    """Scan a file or directory for retired model ID strings and report
    migration targets. Text-based grep, not an AST — matches Anthropic's
    own documented migration advice to grep the whole codebase (API calls,
    env files, CI configs), not just the primary call site.

    Also flags DEPRECATED_MODELS hits (v1.37.0) — IDs with an announced
    future retirement date that still work today. These are reported
    separately from RETIRED_MODELS hits since they aren't a build-breaking
    problem yet, just a heads-up before they become one."""
    import os
    import re

    retired_targets = list(RETIRED_MODELS.keys())
    deprecated_targets = list(DEPRECATED_MODELS.keys())
    all_targets = retired_targets + deprecated_targets
    pattern = re.compile("|".join(re.escape(t) for t in all_targets))

    if os.path.isfile(path):
        files = [path]
    else:
        files = []
        for root, _dirs, fnames in os.walk(path):
            if any(part.startswith(".") for part in root.split(os.sep)):
                continue
            for fn in fnames:
                files.append(os.path.join(root, fn))

    hits: dict = {}
    for fp in files:
        try:
            with open(fp, encoding="utf-8", errors="ignore") as fh:
                for lineno, line in enumerate(fh, 1):
                    for m in pattern.finditer(line):
                        hits.setdefault(m.group(0), []).append((fp, lineno))
        except (IsADirectoryError, PermissionError):
            continue

    retired_hits = {k: v for k, v in hits.items() if k in RETIRED_MODELS}
    deprecated_hits = {k: v for k, v in hits.items() if k in DEPRECATED_MODELS}

    if not retired_hits and not deprecated_hits:
        print(f"\n\033[92m✓ No retired or deprecated model IDs found under {path}\033[0m")
        return

    if retired_hits:
        print(f"\n\033[91m⚠ Retired model IDs found under {path}\033[0m\n")
        for model_id, locations in retired_hits.items():
            rec = RETIRED_MODELS[model_id]
            print(
                f"  \033[1m{model_id}\033[0m — retired {rec['retired']}, "
                f"migrate to \033[92m{rec['replacement']}\033[0m"
            )
            for fp, lineno in locations[:5]:
                print(f"    {fp}:{lineno}")
            if len(locations) > 5:
                print(f"    ... and {len(locations) - 5} more")
            print()

    if deprecated_hits:
        print(
            f"\n\033[93m⚠ Deprecated model IDs found under {path} "
            f"(still work today, retiring soon)\033[0m\n"
        )
        for model_id, locations in deprecated_hits.items():
            rec = DEPRECATED_MODELS[model_id]
            print(
                f"  \033[1m{model_id}\033[0m — retiring "
                f"{rec['retirement_scheduled']}, migrate to "
                f"\033[92m{rec['replacement']}\033[0m"
            )
            for fp, lineno in locations[:5]:
                print(f"    {fp}:{lineno}")
            if len(locations) > 5:
                print(f"    ... and {len(locations) - 5} more")
            print()


# ── Upgrade all ─────────────────────────────────────────────────────────────
# New feature: cmd_check_deprecated (above) only *flags* retired IDs and
# never touches the filesystem — it can't fix anything, and it has no
# concept of "upgrade every model reference to the best model available"
# (it wouldn't rewrite a perfectly-callable claude-sonnet-4-6 or
# claude-haiku-4-5-20251001 reference, since neither is retired). This adds
# that: point it at a file or directory and it rewrites *every* known Claude
# model ID it finds — retired, legacy-but-still-callable, or just a
# lower/different current-tier model — to a single target: Fable 5 or
# Opus 4.8. Dry-run by default; writes a .bak alongside every changed file
# unless told not to.

UPGRADE_TARGETS = {
    "fable5": "claude-fable-5",
    "opus": "claude-opus-4-8",
}

# Known alternate spellings that aren't literal MODEL_CATALOG/RETIRED_MODELS
# keys but are documented elsewhere in this project as valid — e.g.
# claude_models.py's own MODEL_CATALOG note for claude-haiku-4-5-20251001:
# "Alias: claude-haiku-4-5." Included so --upgrade-all catches the alias
# form too, not just the dated ID.
MODEL_ID_ALIASES = {
    "claude-haiku-4-5": "claude-haiku-4-5-20251001",
}


def _upgrade_source_ids(target_id: str) -> list:
    """Every model ID string this project knows about except the target
    itself, longest-first so no shorter alias can partially shadow a
    longer one when both would otherwise match at the same position.
    Includes DEPRECATED_MODELS (v1.37.0) — a still-callable-but-announced
    ID like claude-opus-4-1-20250805 is exactly the kind of reference
    --upgrade-all exists to clear out before it becomes a RETIRED_MODELS
    problem instead."""
    ids = (
        set(RETIRED_MODELS.keys())
        | set(MODEL_CATALOG.keys())
        | set(MODEL_ID_ALIASES.keys())
        | set(DEPRECATED_MODELS.keys())
    )
    ids.discard(target_id)
    return sorted(ids, key=len, reverse=True)


def _walk_upgrade_candidates(path: str):
    import os

    if os.path.isfile(path):
        yield path
        return
    for root, dirs, fnames in os.walk(path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fn in fnames:
            if fn.endswith(".bak"):
                continue
            yield os.path.join(root, fn)


def cmd_upgrade_all(path: str, target: str = "fable5", apply: bool = False, no_backup: bool = False):
    """Rewrite every known Claude model ID under `path` to the chosen
    target (claude-fable-5 or claude-opus-4-8). Dry-run (report only)
    unless apply=True. Skips files that aren't valid UTF-8 text (so binary
    files, e.g. in a PyInstaller dist/ output, are left untouched rather
    than corrupted) and never rewrites *.bak files it may have written on
    a previous run."""
    import re

    if target not in UPGRADE_TARGETS:
        print(f"[ERROR] Unknown upgrade target '{target}'. Choose from: " f"{', '.join(UPGRADE_TARGETS)}")
        return

    target_id = UPGRADE_TARGETS[target]
    old_ids = _upgrade_source_ids(target_id)
    pattern = re.compile(r"(?<![\w-])(" + "|".join(re.escape(i) for i in old_ids) + r")(?![\w-])")

    files_changed = 0
    total_hits = 0
    per_file_report = []

    for fp in _walk_upgrade_candidates(path):
        try:
            with open(fp, encoding="utf-8", errors="strict") as fh:
                text = fh.read()
        except (UnicodeDecodeError, PermissionError, IsADirectoryError):
            continue  # binary / unreadable — skip rather than risk corrupting it

        matches = pattern.findall(text)
        if not matches:
            continue

        counts: dict = {}
        for m in matches:
            counts[m] = counts.get(m, 0) + 1
        per_file_report.append((fp, counts))
        total_hits += len(matches)

        if apply:
            new_text = pattern.sub(target_id, text)
            if not no_backup:
                with open(fp + ".bak", "w", encoding="utf-8") as bak:
                    bak.write(text)
            with open(fp, "w", encoding="utf-8") as fh:
                fh.write(new_text)
            files_changed += 1

    if not per_file_report:
        print(f"\n\033[92m✓ No known model IDs found under {path} — nothing to upgrade\033[0m")
        return

    verb = "Upgraded" if apply else "Would upgrade"
    print(
        f"\n\033[94mℹ {verb} {total_hits} model reference(s) across "
        f"{len(per_file_report)} file(s) to \033[1m{target_id}\033[0m\n"
    )
    for fp, counts in per_file_report:
        detail = ", ".join(f"{mid} ×{n}" for mid, n in sorted(counts.items()))
        print(f"  {fp}: {detail}")

    if apply:
        backup_note = "" if no_backup else " (.bak backup written alongside each changed file)"
        print(f"\n\033[92m✓ {files_changed} file(s) updated{backup_note}\033[0m")
    else:
        print(
            "\n\033[93m⚠ Dry run — no files were changed. Re-run with --upgrade-yes to "
            "apply (add --upgrade-no-backup to skip .bak files).\033[0m"
        )


# ── Computer Use ───────────────────────────────────────────────────────────

COMPUTER_USE_TOOLS = [
    {
        "type": "computer_20250124",
        "name": "computer",
        "display_width_px": 1024,
        "display_height_px": 768,
        "display_number": 1,
    },
    {
        "type": "bash_20250124",
        "name": "bash",
    },
    {
        "type": "text_editor_20250124",
        "name": "str_replace_based_edit_tool",
    },
]

COMPUTER_USE_BETA = "computer-use-2025-01-24"


class ComputerUseCoder:
    """Claude with computer use tools."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-5",
        max_tokens: int = 4096,
        width: int = 1024,
        height: int = 768,
    ):
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.width = width
        self.height = height

    @retry(max_attempts=4, base_delay=1.0, max_delay=15.0, breaker=_breaker)
    def _call(self, payload: dict) -> dict:
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "anthropic-beta": COMPUTER_USE_BETA,
        }
        req = urllib.request.Request(
            MESSAGES_ENDPOINT,
            data=json.dumps(payload).encode(),
            headers=headers,
            method="POST",
        )
        return urlopen_json(req, timeout=120)

    def _post(self, payload: dict) -> dict:
        try:
            return self._call(payload)
        except AICoderError as e:
            return {"error": e.message, "status": getattr(e, "status_code", None)}
        except Exception as e:
            return {"error": str(e)}

    def run_task(self, task: str, system: str = None) -> dict:
        """Submit a computer use task. Returns tool calls for execution."""
        tools = [dict(t) for t in COMPUTER_USE_TOOLS]
        tools[0]["display_width_px"] = self.width
        tools[0]["display_height_px"] = self.height

        system_prompt = system or (
            "You have access to a computer with a display. "
            "Use the computer and bash tools to complete the task. "
            "Describe each action you take."
        )

        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system_prompt,
            "tools": tools,
            "messages": [{"role": "user", "content": task}],
        }
        data = self._post(payload)
        if "error" in data:
            return {"text": f"[ERROR] {data['error']}", "tool_calls": []}

        text = ""
        tool_calls = []
        for block in data.get("content", []):
            bt = block.get("type", "")
            if bt == "text":
                text += block.get("text", "")
            elif bt == "tool_use":
                tool_calls.append(
                    {
                        "name": block.get("name"),
                        "input": block.get("input", {}),
                        "id": block.get("id"),
                    }
                )

        return {"text": text, "tool_calls": tool_calls, "stop_reason": data.get("stop_reason")}


def cmd_computer_use(task: str, api_key: str, model: str):
    print("\033[94mℹ Computer Use mode\033[0m")
    print("\033[93m⚠ Note: Actual execution requires a virtual display environment.\033[0m\n")
    cu = ComputerUseCoder(api_key=api_key, model=model)
    result = cu.run_task(task)
    print(result["text"])
    if result["tool_calls"]:
        print("\n\033[90m── Tool calls planned ─────────────────\033[0m")
        for tc in result["tool_calls"]:
            print(f"  {tc['name']}: {json.dumps(tc['input'])[:120]}")
    return result


# ── Adaptive + Interleaved Thinking ───────────────────────────────────────

EFFORT_BUDGETS = {"low": 2000, "medium": 8000, "high": 16000, "max": 32000}


class AdaptiveThinkingCoder:
    """Extended thinking with adaptive / interleaved modes."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-5", max_tokens: int = 8000):
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens

    @retry(max_attempts=4, base_delay=1.0, max_delay=15.0, breaker=_breaker)
    def _call(self, payload: dict, betas: list[str] = None) -> dict:
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }
        if betas:
            headers["anthropic-beta"] = ",".join(betas)
        req = urllib.request.Request(
            MESSAGES_ENDPOINT,
            data=json.dumps(payload).encode(),
            headers=headers,
            method="POST",
        )
        return urlopen_json(req, timeout=300)

    def _post(self, payload: dict, betas: list[str] = None) -> dict:
        try:
            return self._call(payload, betas)
        except AICoderError as e:
            return {"error": e.message, "status": getattr(e, "status_code", None)}
        except Exception as e:
            return {"error": str(e)}

    def adaptive(self, prompt: str, budget: int = 8000, effort: str = None, system: str = None) -> str:
        """Adaptive thinking — model decides depth."""
        if effort:
            budget = EFFORT_BUDGETS.get(effort, budget)
        payload = {
            "model": self.model,
            "max_tokens": max(self.max_tokens, budget + 1000),
            "thinking": {"type": "adaptive", "budget_tokens": budget},
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            payload["system"] = system
        data = self._post(payload)
        if "error" in data:
            return f"[ERROR] {data['error']}"
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")

    def interleaved(self, prompt: str, tools: list[dict], budget: int = 8000, system: str = None) -> str:
        """Interleaved thinking — think between tool calls."""
        payload = {
            "model": self.model,
            "max_tokens": max(self.max_tokens, budget + 1000),
            "thinking": {"type": "enabled", "budget_tokens": budget},
            "tools": tools,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            payload["system"] = system
        data = self._post(payload, betas=["interleaved-thinking-2025-05-14"])
        if "error" in data:
            return f"[ERROR] {data['error']}"
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


def cmd_adaptive_thinking(prompt: str, api_key: str, model: str, effort: str = "medium", budget: int = None):
    print(f"\033[94mℹ Adaptive Thinking | effort={effort}\033[0m\n")
    atc = AdaptiveThinkingCoder(api_key=api_key, model=model)
    result = atc.adaptive(prompt, budget=budget or 8000, effort=effort)
    print(result)
    return result
