"""
claude_cost_optimizer.py — Cost-aware model routing.
Classifies a prompt's complexity and routes to the cheapest model that
can handle it. Tracks cumulative spend across calls.
ZCoder CLI v1.10.3

Pricing below verified against platform.claude.com/docs/en/about-claude/
models/overview as of 2026-07-02, re-verified 2026-08-13. Claude Sonnet 5
launched at $2/$10 per MTok. On 2026-08-10 Anthropic cancelled the planned
Sep 1 increase to $3/$15 — the $2/$10 rate is now the permanent standard
price. PRICE["claude-sonnet-5"] reflects that permanently at $2/$10.
Re-verify before relying on this for billing-sensitive decisions.

Note: everything in this module is a *local estimate* built from token
counts this CLI is told about after a call completes — it never queries a
real usage/spend endpoint, and has no way to see calls made outside this
CLI. For actual org-level historical usage and cost data (the real
numbers Anthropic bills against), see claude_admin_api.py's
get_usage_report()/get_cost_report() and --usage-report — that requires
an Admin API key rather than a regular one, which is why it's a separate
module instead of folded into local estimation here.
"""

import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import requests

from zcoder.agent.optimization.local_tokens import estimate_tokens as local_estimate_tokens
from zcoder.agent.optimization.tokens import optimize_prompt
from zcoder.core.provider_policy import create_anthropic_client
from zcoder.core.utils import sampling_kwargs

SPEND_LOG = Path.home() / ".zcoder" / "cost_log.json"

# Thread-safe cost log cache
_cost_lock = threading.Lock()
_cost_cache: dict = {}
_cache_ttl = 300  # 5 minutes TTL for cost cache

# Connection pool for HTTP API requests
_connection_pool: requests.Session | None = None


def get_connection_pool() -> requests.Session:
    """Get or create a thread-safe HTTP connection pool."""
    global _connection_pool
    if _connection_pool is None:
        _connection_pool = requests.Session()
        # Configure connection pool settings
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=10,
            max_retries=3,
        )
        _connection_pool.mount("https://", adapter)
        _connection_pool.mount("http://", adapter)
    return _connection_pool


def release_connection_pool() -> None:
    """Release the connection pool resources."""
    global _connection_pool
    if _connection_pool is not None:
        _connection_pool.close()
        _connection_pool = None


# ── Response Cache with TTL ──────────────────────────────────────────────
# Cache for API responses to avoid redundant calls.


_response_cache: OrderedDict[str, dict] = OrderedDict()


def _cache_key(model: str, in_tok: int, out_tok: int, inference_geo: str) -> str:
    """Generate a cache key for cost estimation."""
    import hashlib

    data = f"{model}:{in_tok}:{out_tok}:{inference_geo}"
    return hashlib.sha256(data.encode()).hexdigest()


def _evict_cache() -> None:
    """Evict oldest entries from the response cache when it exceeds capacity."""
    max_cache_size = 100  # Keep last 100 entries
    while len(_response_cache) > max_cache_size:
        _response_cache.popitem(last=False)


def estimate_cost_cached(
    model: str,
    in_tok: int,
    out_tok: int,
    use_intro_pricing: bool = False,
    inference_geo: str = "global",
) -> float:
    """Estimate cost with caching to avoid redundant calculations.

    Uses an OrderedDict-based TTL cache. If the same (model, tokens, geo)
    combination has been computed within the TTL window, the cached result
    is returned immediately.

    Args:
        model: Model identifier
        in_tok: Input token count
        out_tok: Output token count
        use_intro_pricing: Whether to use Sonnet 5 intro pricing
        inference_geo: Data residency ("us" or "global")

    Returns:
        Estimated cost in USD
    """
    key = _cache_key(model, in_tok, out_tok, inference_geo)

    with _cost_lock:
        # Check cache hit
        if key in _response_cache:
            entry = _response_cache[key]
            # Check TTL
            entry_time = entry["timestamp"]
            now = time.time()
            if now - entry_time < _cache_ttl:
                # Cache hit — return cached cost
                return entry["cost"]
            else:
                # Expired — remove and recompute
                del _response_cache[key]

        # Cache miss — compute cost
        cost = estimate_cost(model, in_tok, out_tok, use_intro_pricing, inference_geo)

        # Store in cache
        _response_cache[key] = {
            "cost": cost,
            "timestamp": time.time(),
        }

        # Evict if over capacity
        _evict_cache()

        return cost


PRICE: dict[str, dict[str, float]] = {
    # Current
    "claude-haiku-4-5-20251001": {"in": 1.0, "out": 5.0},
    "claude-sonnet-5": {"in": 2.0, "out": 10.0},
    "claude-opus-5": {"in": 5.0, "out": 25.0},
    "claude-opus-4-8": {"in": 5.0, "out": 25.0},
    "claude-fable-5": {"in": 10.0, "out": 50.0},
    "claude-mythos-5": {"in": 10.0, "out": 50.0},
    # Legacy — still callable, kept so cost estimates don't silently fall
    # back to the DEFAULT_PRICE guess for accounts still on these
    "claude-opus-4-7": {"in": 5.0, "out": 25.0},
    "claude-opus-4-6": {"in": 5.0, "out": 25.0},
    "claude-opus-4-5": {"in": 5.0, "out": 25.0},
    "claude-sonnet-4-6": {"in": 3.0, "out": 15.0},
    "claude-sonnet-4-5": {"in": 3.0, "out": 15.0},
}
SONNET5_INTRO_PRICE = {"in": 2.0, "out": 10.0}  # permanent standard price
TIER_MODELS = ["claude-haiku-4-5-20251001", "claude-sonnet-5", "claude-opus-5"]

# Long-context (>200K input) pricing surcharge. Previously missing entirely —
# estimate_cost() applied flat per-model pricing regardless of input size,
# which under-quoted cost for any model that has a long-context surcharge.
#
# Per platform.claude.com/docs/en/about-claude/pricing (checked 2026-07-02):
# Claude Opus 5, Opus 4.8, Opus 4.7, Opus 4.6, Sonnet 4.6, and Sonnet 5 all get the
# full 1M-token context window at FLAT standard pricing — no surcharge at
# any input size. Those models are deliberately absent below. The surcharge
# only still applies to models on the older 1M-context BETA
# (context-1m-2025-08-07 header): confirmed for claude-sonnet-4-5 at 2x
# input / 1.5x output above a 200K-token request — the *whole* request is
# billed at the surcharge rate once it crosses the threshold, not just the
# tokens above it. That beta is scheduled for retirement 2026-04-30 per the
# API release notes, after which this entry stops mattering, but it's kept
# since claude-sonnet-4-5 is still callable / still in PRICE. Add other
# legacy models here only once their surcharge terms are confirmed —
# guessing a multiplier is worse than omitting it, since PRICE already
# falls back sanely for anything not in this table.
LONG_CONTEXT_SURCHARGE: dict[str, dict[str, float]] = {
    "claude-sonnet-4-5": {"threshold": 200_000, "in_mult": 2.0, "out_mult": 1.5},
}

# ── Context windows ──────────────────────────────────────────────────────
# Cross-checked against the pricing notes above: Claude Opus 5 / 4.8 /
# 4.7 / 4.6, Sonnet 5 / 4.6, Fable 5 and Mythos 5 run a full 1M-token
# window at flat pricing; claude-sonnet-4-5 reaches 1M through the
# (retiring 2026-04-30) context-1m beta. Anything not mapped here falls
# back to the legacy 200K window — assuming too small a
# window makes /context warn early, never late (Upgrade-56, parity W1).
MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    "claude-opus-5": 1_000_000,
    "claude-opus-4-8": 1_000_000,
    "claude-opus-4-7": 1_000_000,
    "claude-opus-4-6": 1_000_000,
    "claude-sonnet-5": 1_000_000,
    "claude-sonnet-4-6": 1_000_000,
    "claude-sonnet-4-5": 1_000_000,  # via context-1m beta
    "claude-fable-5": 1_000_000,
    "claude-mythos-5": 1_000_000,
}
LEGACY_CONTEXT_WINDOW = 200_000


def context_window(model: str) -> int:
    """Best-known context window (tokens) for ``model``; 200K when unmapped."""
    return MODEL_CONTEXT_WINDOWS.get(model, LEGACY_CONTEXT_WINDOW)


# Data residency (inference_geo) pricing. Per platform.claude.com/docs
# (Service tiers / Data residency, checked 2026-07-02, re-verified 2026-08-13): requests with
# inference_geo:"us" on Claude Opus 4.6, Sonnet 4.6, and later models (including Opus 5) are
# billed at a flat 1.1x multiplier on both input and output tokens.
# inference_geo:"global" (the default) is standard pricing. Requesting
# inference_geo at all on models before Opus 4.6 / Sonnet 4.6 is a 400 —
# INFERENCE_GEO_SUPPORTED gates that at the call site (see optimized_call).
INFERENCE_GEO_MULTIPLIER = 1.1
INFERENCE_GEO_SUPPORTED = {
    "claude-opus-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-sonnet-5",
    "claude-sonnet-4-6",
    "claude-fable-5",
    "claude-mythos-5",
}


def estimate_cost(
    model: str, in_tok: int, out_tok: int, use_intro_pricing: bool = False, inference_geo: str = "global"
) -> float:
    if model == "claude-sonnet-5" and use_intro_pricing:
        p = SONNET5_INTRO_PRICE
    else:
        p = PRICE.get(model, {"in": 3.0, "out": 15.0})

    surcharge = LONG_CONTEXT_SURCHARGE.get(model)
    if surcharge and in_tok > surcharge["threshold"]:
        # Whole request is billed at the surcharge rate once input crosses
        # the threshold — not just the tokens above it.
        in_price, out_price = p["in"] * surcharge["in_mult"], p["out"] * surcharge["out_mult"]
    else:
        in_price, out_price = p["in"], p["out"]

    if inference_geo == "us" and model in INFERENCE_GEO_SUPPORTED:
        in_price *= INFERENCE_GEO_MULTIPLIER
        out_price *= INFERENCE_GEO_MULTIPLIER

    return in_tok / 1e6 * in_price + out_tok / 1e6 * out_price


def _count_markers(prompt: str, markers: list[str]) -> int:
    """Count occurrences of each marker in prompt."""
    return sum(prompt.count(k) for k in markers)


def classify_complexity(prompt: str) -> str:
    """Enhanced heuristic: short simple → haiku; long/complex → sonnet; very long or code-heavy → opus.

    Considers:
    - Word count
    - Code markers (def, class, async, SQL keywords, etc.)
    - Structural complexity (nesting, control flow)
    - Task complexity keywords (refactor, comprehensive, legacy, etc.)
    - Task description keywords (write, create, build, implement)
    - SQL-specific markers (indicates database operations)
    - Estimated token count via local estimator
    """
    words = len(prompt.split())
    prompt_lower = prompt.lower()

    # Code markers for general programming
    code_markers = _count_markers(
        prompt,
        [
            "def ",
            "class ",
            "function ",
            "CREATE ",
            "INSERT ",
            "UPDATE ",
            "DELETE ",
            "async ",
            "await ",
            "try:",
            "except:",
            "for ",
            "while ",
            "if ",
            "elif ",
            "else:",
            "lambda ",
            "yield ",
            "with ",
            "import ",
            "from ",
            "return ",
            "raise ",
            "=>",
            "->",
            "{}",
            "[]",
            "::",
            "@@",
        ],
    )

    # SQL-specific markers (SELECT is a strong indicator of DB operations)
    sql_markers = prompt.count("SELECT ")

    # Task complexity keywords that indicate higher complexity
    complexity_keywords = [
        "refactor",
        "comprehensive",
        "legacy",
        "architecture",
        "optimize",
        "performance",
        "security",
        "authentication",
        "authorization",
        "migration",
        "integration",
        "distributed",
        "concurrent",
        "parallel",
        "async",
        "microservice",
        "kubernetes",
        "docker",
        "ci/cd",
        "pipeline",
        "testing",
        "benchmark",
        "profiling",
    ]
    complexity_score = sum(1 for kw in complexity_keywords if kw in prompt_lower)

    # Task description keywords - these indicate a coding task request, not a simple snippet
    task_keywords = [
        "write",
        "create",
        "build",
        "implement",
        "design",
        "develop",
        "function that",
        "class that",
        "module that",
        "script that",
        "api that",
        "endpoint that",
        "reads",
        "parses",
        "processes",
        "transforms",
        "validates",
        "generates",
    ]
    task_score = sum(1 for kw in task_keywords if kw in prompt_lower)

    # Structural complexity indicators
    structural_score = 0
    lines = prompt.split("\n")
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(("if ", "for ", "while ", "try:", "except", "with ", "async ")):
            structural_score += 1
        # Count nesting level (indentation)
        indent = len(line) - len(line.lstrip())
        if indent > 4:
            structural_score += indent // 4

    # Use local token estimation for more accurate sizing (cached)
    estimated_tokens = local_estimate_tokens(prompt, "claude-sonnet-5")

    # Simple code snippets (short, minimal structure, no task/SQL keywords) should be low complexity
    is_simple_snippet = (
        words < 20
        and code_markers <= 1
        and sql_markers == 0
        and structural_score == 0
        and complexity_score == 0
        and task_score == 0
        and estimated_tokens < 50
    )

    # High complexity: very long, lots of code, high structural complexity, many complexity keywords, or many tokens
    if (
        words > 500
        or code_markers > 5
        or sql_markers > 2
        or structural_score > 10
        or complexity_score > 2
        or estimated_tokens > 1500
    ):
        return "high"

    # Medium complexity: moderate length, some code, SQL markers, moderate structure, some complexity/task keywords
    if not is_simple_snippet and (
        words > 50
        or code_markers >= 1
        or sql_markers >= 1
        or structural_score > 1
        or complexity_score > 0
        or task_score > 0
        or estimated_tokens > 200
    ):
        return "medium"

    return "low"


def select_model(complexity: str, force: str | None = None, prefer_latency: bool = False) -> str:
    if force:
        return force

    # Latency-aware routing: prefer faster/cheaper models when latency is critical
    if prefer_latency:
        # Haiku is fastest, then Sonnet, then Opus
        latency_tier = ["claude-haiku-4-5-20251001", "claude-sonnet-5", "claude-opus-5"]
        return {"low": latency_tier[0], "medium": latency_tier[0], "high": latency_tier[0]}[complexity]

    return {"low": TIER_MODELS[0], "medium": TIER_MODELS[1], "high": TIER_MODELS[2]}[complexity]


def _log_spend(model: str, in_tok: int, out_tok: int, cost: float, prompt_preview: str):
    SPEND_LOG.parent.mkdir(parents=True, exist_ok=True)

    # Use thread-safe cache
    with _cost_lock:
        _cost_cache.setdefault("entries", []).append(
            {
                "ts": datetime.now().isoformat(),
                "model": model,
                "in_tok": in_tok,
                "out_tok": out_tok,
                "cost_usd": round(cost, 6),
                "prompt": prompt_preview[:80],
            }
        )
        # Keep only last 5000 entries
        _cost_cache["entries"] = _cost_cache["entries"][-5000:]
        # Write to file
        SPEND_LOG.write_text(json.dumps(_cost_cache["entries"], indent=2))

    # Also update persistent log
    try:
        all_entries = json.loads(SPEND_LOG.read_text()) if SPEND_LOG.exists() else []
        # Merge and dedupe by timestamp+model
        existing_entries = {e["ts"] + e["model"]: e for e in all_entries}
        existing_entries[f"{datetime.now().isoformat()}{model}"] = {
            "ts": datetime.now().isoformat(),
            "model": model,
            "in_tok": in_tok,
            "out_tok": out_tok,
            "cost_usd": round(cost, 6),
            "prompt": prompt_preview[:80],
        }
        SPEND_LOG.write_text(json.dumps(list(existing_entries.values())[-5000:], indent=2))
    except Exception:  # nosec
        pass


@dataclass
class OptimizedResponse:
    text: str
    model_used: str
    complexity: str
    in_tokens: int
    out_tokens: int
    cost_usd: float
    latency_ms: int


def optimized_call(
    prompt: str,
    api_key: str,
    system: str = "",
    force_model: str | None = None,
    max_tokens: int = 2048,
    service_tier: str | None = None,
    inference_geo: str | None = None,
) -> OptimizedResponse:
    complexity = classify_complexity(prompt)
    model = select_model(complexity, force_model)
    # Apply prompt optimization to reduce token count before sending
    optimized_prompt = optimize_prompt(prompt)
    client = create_anthropic_client(api_key)
    t0 = time.time()
    # NOTE: was hardcoded temperature=0.5, which 400s (invalid_request_error)
    # on claude-sonnet-5 and newer — those models reject explicit sampling
    # params entirely. Route through sampling_kwargs() so it's a no-op there
    # and unchanged (temperature=0.5) on everything else.
    kwargs: dict = dict(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": optimized_prompt}],
        **sampling_kwargs(model, temperature=0.5),
    )
    if system:
        kwargs["system"] = system
    if service_tier:
        # "auto" (use Priority Tier capacity if committed, else fall back to
        # standard) or "standard_only". Priority Tier commitments are no
        # longer purchasable but existing ones still work, and aren't
        # supported on Sonnet 5 / Mythos-tier models — let the API 400
        # surface rather than silently guarding it away client-side.
        kwargs["service_tier"] = service_tier
    if inference_geo:
        # "us" (US-only inference, 1.1x pricing) or "global" (default).
        # Only Opus 4.6+/Sonnet 4.6+ and later support this param at all;
        # earlier models 400 — same reasoning as service_tier above.
        kwargs["inference_geo"] = inference_geo
    resp = client.messages.create(**kwargs)
    ms = int((time.time() - t0) * 1000)
    stop_reason = getattr(resp, "stop_reason", None)
    text = resp.content[0].text if resp.content else ""
    in_tok = resp.usage.input_tokens
    out_tok = resp.usage.output_tokens
    # Refusal billing exemption: a request that returns stop_reason:"refusal"
    # with no generated output isn't billed on the Claude API (checked
    # platform.claude.com/docs 2026-07-02). Don't log spend for it, and don't
    # count it against cost estimates — it's free.
    if stop_reason == "refusal" and out_tok == 0:
        cost = 0.0
    else:
        cost = estimate_cost(model, in_tok, out_tok, inference_geo=inference_geo or "global")
        _log_spend(model, in_tok, out_tok, cost, optimized_prompt)
    return OptimizedResponse(
        text=text,
        model_used=model,
        complexity=complexity,
        in_tokens=in_tok,
        out_tokens=out_tok,
        cost_usd=cost,
        latency_ms=ms,
    )


# ── CLI commands ──────────────────────────────────────────────────────────────


def cmd_optimized(prompt: str, api_key: str, verbose: bool = False, force_model: str | None = None):
    r = optimized_call(prompt, api_key, force_model=force_model)
    if verbose:
        print(
            f"[model={r.model_used}  complexity={r.complexity}  cost=${r.cost_usd:.5f}  {r.latency_ms}ms]\n"
        )
    print(r.text)


def cmd_cost_summary(limit: int = 20, use_cache: bool = True):
    """Print cost summary from the spend log.

    Args:
        limit: Number of recent entries to show
        use_cache: If True, use the in-memory cache for faster access
    """
    # Use cache if available and requested
    entries = []
    with _cost_lock:
        if use_cache and _cost_cache.get("entries"):
            entries = _cost_cache["entries"][-limit:]
        else:
            # Fall back to file
            if not SPEND_LOG.exists():
                print("No cost log found.")
                return
            entries = json.loads(SPEND_LOG.read_text())[-limit:]

    recent = entries[-limit:] if limit > 0 else entries
    total = sum(e["cost_usd"] for e in entries)
    print(f"Total spend logged: ${total:.4f}  ({len(entries)} calls)\n")
    print(f"{'Timestamp':<21} {'Model':<35} {'Cost':>9}  Prompt preview")
    print("─" * 90)
    for e in reversed(recent):
        print(f"{e['ts'][:19]:<21} {e['model']:<35} ${e['cost_usd']:>8.5f}  {e['prompt']}")


def cmd_cost_reset():
    """Clear the cost log and in-memory cache."""
    with _cost_lock:
        _cost_cache.clear()
    if SPEND_LOG.exists():
        SPEND_LOG.unlink()
        print("✓ Cost log cleared.")
    else:
        print("No log to clear.")


def cmd_cost_clear_cache():
    """Clear only the in-memory cost cache."""
    with _cost_lock:
        _cost_cache.clear()
    print("✓ Cost cache cleared.")


def cmd_optimize_prompt(prompt: str, model: str = "claude-sonnet-5") -> str:
    """Optimize a prompt using token heuristics and return the optimized version."""
    optimized = optimize_prompt(prompt, model)
    original_tokens = local_estimate_tokens(prompt, model)
    optimized_tokens = local_estimate_tokens(optimized, model)
    savings = original_tokens - optimized_tokens
    print(f"Original tokens: {original_tokens:,}")
    print(f"Optimized tokens: {optimized_tokens:,}")
    print(f"Savings: {savings:,} tokens ({round(savings/original_tokens*100,2)}%)")
    return optimized
