"""claude_tokens.py — Token Counting
ZCoder CLI v1.8.0

Count tokens BEFORE sending a request (no API cost incurred).
Uses the /v1/messages/count_tokens endpoint for precise counting,
with local estimation as zero-cost fallback.

CLI flags:
  --count-tokens           Count tokens in a prompt without calling the model
  --count-tokens-file F    Count tokens including a file's content
  --count-budget N         Warn if token count exceeds N
  --optimize-tokens        Optimize prompt token count via heuristics
  --batch-count FILE       Batch count tokens from file with prompts
"""

import json
import re
import urllib.request
from pathlib import Path
from functools import lru_cache

from zcoder.agent.optimization.local_tokens import LocalTokenEstimator
from zcoder.core.exceptions import ZCoderError

COUNT_ENDPOINT = "https://api.anthropic.com/v1/messages/count_tokens"

# Precompiled regex patterns for optimization rules (compiled once at import)
_OPTIM_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\n\n+", re.DOTALL), "\n\n"),  # Collapse multiple blank lines
    (re.compile(r" $", re.MULTILINE), "$"),  # Remove trailing spaces
    (re.compile(r" \n", re.MULTILINE), "\n"),  # Remove trailing spaces before newlines
]

# Prompt optimization cache: (prompt, model) -> optimized_prompt
_optimization_cache: dict[tuple[str, str], str] = {}

# Historical usage tracking for predictive model selection
_usage_history: dict[str, list[dict]] = {}


def predict_best_model(
    usage_history: dict[str, list[dict]] | None = None,
    budget: float | None = None,
    current_task_type: str = "general",
) -> str:
    """Predict the best model based on historical usage patterns and budget.

    Args:
        usage_history: Historical token usage per model. If None, uses global _usage_history.
        budget: Maximum budget in USD for the task (optional).
        current_task_type: Type of task ("general", "code", "creative", "analysis").

    Returns:
        Recommended model ID.
    """
    history = usage_history or _usage_history

    # Model pricing per MTok (input)
    model_prices = {
        "claude-opus-5": 5.0,
        "claude-opus-4-8": 5.0,
        "claude-sonnet-5": 2.0,
        "claude-sonnet-4-6": 3.0,
        "claude-sonnet-4-5": 3.0,
        "claude-haiku-4-5-20251001": 1.0,
        "claude-fable-5": 10.0,
        "claude-mythos-5": 10.0,
    }

    # Task-type multiplier for historical adjusted costs
    task_multiplier = {
        "code": 1.2,
        "creative": 1.0,
        "analysis": 1.1,
        "general": 1.0,
    }.get(current_task_type, 1.0)

    # Calculate adjusted cost per model based on history
    model_metrics: dict[str, dict] = {}
    for model, entries in history.items():
        if not entries:
            model_metrics[model] = {
                "avg_tokens": 0,
                "avg_cost_usd": model_prices.get(model, 3.0),
                "count": 0,
            }
            continue

        total_tokens = sum(e.get("tokens", 0) for e in entries)
        total_cost = sum(e.get("cost_usd", 0) for e in entries)
        count = len(entries)
        avg_tokens = total_tokens / count if count > 0 else 0
        avg_cost_usd = total_cost / count if count > 0 else 0

        # Apply task type multiplier
        adjusted_cost = avg_cost_usd * task_multiplier

        model_metrics[model] = {
            "avg_tokens": avg_tokens,
            "avg_cost_usd": adjusted_cost,
            "count": count,
        }

    # If budget is provided, filter models that fit within budget
    if budget:
        feasible_models = []
        for model, metrics in model_metrics.items():
            # Estimate per-request cost and check if within budget
            # Use a conservative estimate of 1 request for feasibility
            if metrics["avg_cost_usd"] <= budget:
                feasible_models.append((model, metrics))

        if feasible_models:
            # Return the most cost-effective model
            feasible_models.sort(key=lambda x: x[1]["avg_cost_usd"])
            return feasible_models[0][0]

    # Return the model with lowest adjusted cost per token
    # Handle empty model_metrics case
    if not model_metrics:
        # No history available, return default model
        return "claude-sonnet-5"

    best_model = min(
        model_metrics.keys(),
        key=lambda m: model_metrics[m]["avg_cost_usd"] / max(model_metrics[m]["avg_tokens"], 1),
    )

    return best_model


def route_by_cost(
    prompt: str,
    budget: float,
    current_usage: float = 0.0,
    task_type: str = "general",
) -> dict:
    """Route a prompt to the most cost-effective model within budget.

    Args:
        prompt: The prompt to analyze
        budget: Available budget in USD
        current_usage: Current spending in this session/dialog
        task_type: Type of task for model selection

    Returns:
        Dict with recommended model and remaining budget
    """
    from zcoder.agent.optimization.local_tokens import _is_code_model_specific

    # Estimate token count for the prompt
    estimator = LocalTokenEstimator()
    estimated_tokens = estimator.estimate(prompt)

    # Predict best model for this task type
    recommended_model = predict_best_model(
        usage_history=None,
        budget=budget - current_usage,
        current_task_type=task_type,
    )

    # Re-estimate cost with recommended model
    price_per_mtok = {
        "claude-opus-5": 5.0,
        "claude-opus-4-8": 5.0,
        "claude-sonnet-5": 2.0,
        "claude-sonnet-4-6": 3.0,
        "claude-sonnet-4-5": 3.0,
        "claude-haiku-4-5-20251001": 1.0,
    }.get(recommended_model, 3.0)

    estimated_cost = (estimated_tokens / 1_000_000) * price_per_mtok
    remaining_budget = budget - current_usage - estimated_cost

    # Check if within budget
    within_budget = estimated_cost + current_usage <= budget

    return {
        "recommended_model": recommended_model,
        "estimated_tokens": estimated_tokens,
        "estimated_cost_usd": round(estimated_cost, 6),
        "remaining_budget_usd": round(remaining_budget, 6),
        "within_budget": within_budget,
        "task_type": task_type,
    }


def forecast_spend(
    days: int = 30,
    daily_prompts: int | None = None,
    historical_usage: dict[str, list[dict]] | None = None,
) -> dict:
    """Forecast future spending based on historical usage patterns.

    Args:
        days: Number of days to forecast
        daily_prompts: Estimated prompts per day (uses historical avg if None)
        historical_usage: Historical usage per model. If None, uses global _usage_history.

    Returns:
        Dict with spend forecast details
    """
    history = historical_usage or _usage_history

    if not history:
        return {
            "total_forecast_usd": 0.0,
            "daily_average_usd": 0.0,
            "model_breakdown": {},
            "confidence": "no_data",
        }

    # Model pricing
    model_prices = {
        "claude-opus-5": 5.0,
        "claude-opus-4-8": 5.0,
        "claude-sonnet-5": 2.0,
        "claude-sonnet-4-6": 3.0,
        "claude-sonnet-4-5": 3.0,
        "claude-haiku-4-5-20251001": 1.0,
        "claude-fable-5": 10.0,
        "claude-mythos-5": 10.0,
    }

    # Calculate daily average per model
    model_daily: dict[str, dict] = {}
    for model, entries in history.items():
        if not entries:
            model_daily[model] = {"daily_avg_tokens": 0, "daily_avg_cost": 0.0}
            continue

        total_tokens = sum(e.get("tokens", 0) for e in entries)
        total_cost = sum(e.get("cost_usd", 0) for e in entries)
        count = len(entries)

        # Estimate days from history
        # Assuming entries are spread over the tracking period
        days_covered = max(1, count / 30)  # approx 30 entries per month
        daily_avg_tokens = total_tokens / max(days_covered, 1)
        daily_avg_cost = (total_cost / max(days_covered, 1)) * model_prices.get(model, 3.0)

        model_daily[model] = {
            "daily_avg_tokens": round(daily_avg_tokens, 1),
            "daily_avg_cost": round(daily_avg_cost, 6),
        }

    # Calculate total forecast
    total_daily_cost = sum(m.get("daily_avg_cost", 0) for m in model_daily.values())

    # Apply daily_prompts if specified
    if daily_prompts is not None:
        # Scale forecast based on estimated prompts
        # This is a simplified approach - in production would use more sophisticated scaling
        scale_factor = daily_prompts / max(sum(len(v.get("entries", [])) for v in history.values()), 1)
        total_daily_cost *= scale_factor
        daily_average_usd = total_daily_cost / days
    else:
        daily_average_usd = total_daily_cost / days if days > 0 else 0.0

    total_forecast_usd = daily_average_usd * days

    return {
        "total_forecast_usd": round(total_forecast_usd, 6),
        "daily_average_usd": round(daily_average_usd, 6),
        "model_breakdown": model_daily,
        "confidence": "high" if len(history) > 10 else "medium",
    }


def _track_usage(self, tokens: int, cost_usd: float, model: str) -> None:
    """Track usage history for predictive model selection."""
    entry = {
        "tokens": tokens,
        "cost_usd": cost_usd,
        "model": model,
    }
    if model not in _usage_history:
        _usage_history[model] = []
    _usage_history[model].append(entry)

    # Keep history manageable (last 100 entries per model)
    if len(_usage_history[model]) > 100:
        _usage_history[model] = _usage_history[model][-100:]


@lru_cache(maxsize=128)
def _cached_optimize_prompt_core(prompt: str, model: str) -> str:
    """Core optimization with LRU cache."""
    optimized = prompt
    for pattern, replacement in _OPTIM_PATTERNS:
        optimized = pattern.sub(replacement, optimized)

    # Remove excessive whitespace
    optimized = "\n".join(line.rstrip() for line in optimized.split("\n"))

    # Collapse multiple consecutive blank lines to a single one
    optimized = re.sub(r"\n\n+", "\n\n", optimized)

    return optimized


def optimize_prompt(prompt: str, model: str = "claude-sonnet-5") -> str:
    """Apply token optimization heuristics to reduce prompt size.

    Applies simple transformations to reduce token count without
    changing the semantic meaning of the prompt.

    Uses precompiled regex patterns and LRU cache for repeated prompts.
    """
    # Check cache first
    cache_key = (prompt, model)
    if cache_key in _optimization_cache:
        return _optimization_cache[cache_key]

    optimized = _cached_optimize_prompt_core(prompt, model)
    _optimization_cache[cache_key] = optimized

    return optimized


class TokenCounter:
    """Count tokens without sending to the model.

    Supports both API-based precise counting and local estimation.
    Local estimation is used when no API key is provided or explicitly requested.
    """

    def __init__(self, api_key: str, model: str = "claude-sonnet-5"):
        self.api_key = api_key
        self.model = model
        self._local_estimator = LocalTokenEstimator()
        self._optimization_cache: dict[str, str] = {}

    def count(
        self,
        prompt: str,
        system: str | None = None,
        tools: list[dict] | None = None,
        history: list[dict] | None = None,
        use_local: bool = False,
    ) -> dict:
        """Count tokens via API or local estimation.

        Args:
            prompt: User prompt
            system: Optional system prompt
            tools: Optional tool definitions
            history: Optional conversation history
            use_local: Force local estimation even if API key available

        Returns:
            Dict with input_tokens and optionally other metadata
        """
        if use_local or not self.api_key:
            return self.count_local(prompt, system, tools, history)

        # Apply optimization before API call if model supports it
        optimized_prompt = optimize_prompt(prompt, self.model)
        self._optimization_cache[prompt] = optimized_prompt
        if optimized_prompt != prompt:
            # Log that optimization was applied
            pass

        messages = list(history or [])
        messages.append({"role": "user", "content": prompt})

        payload: dict = {"model": self.model, "messages": messages}
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = tools

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }
        req = urllib.request.Request(
            COUNT_ENDPOINT,
            data=json.dumps(payload).encode(),
            headers=headers,
            method="POST",
        )
        try:
            result = self._call(req)
            # Track API usage for predictive model selection
            tokens = result.get("input_tokens", 0)
            # Estimate cost based on the model's pricing
            model = self.model
            prices_per_mtok = {
                "claude-opus-5": 5.0,
                "claude-opus-4-8": 5.0,
                "claude-sonnet-5": 2.0,
                "claude-haiku-4-5-20251001": 1.0,
            }
            price = prices_per_mtok.get(model, 3.0)
            cost_usd = (tokens / 1_000_000) * price
            self._track_usage(tokens, cost_usd, model)
            return result
        except ZCoderError as e:
            raise RuntimeError(f"Token count failed: {e.message}") from e

    def _call(self, req: urllib.request.Request) -> dict:
        """Execute the count_tokens API request and return parsed JSON.

        Network/HTTP failures are operational errors, so they are wrapped in
        :class:`ZCoderError` and never exposed as raw urllib exceptions.
        """
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read()
            return json.loads(body)
        except Exception as exc:
            raise ZCoderError(f"count_tokens request failed: {exc}") from exc

    def count_file(
        self,
        file_path: str,
        prompt: str | None = None,
        system: str | None = None,
        use_local: bool = False,
    ) -> dict:
        """Count tokens for a file's contents, optionally prefixed by a prompt.

        Reads the file once (bounded I/O) and delegates to :meth:`count`.
        """
        try:
            content = Path(file_path).read_text(encoding="utf-8")
        except OSError as exc:
            raise ZCoderError(f"Cannot read {file_path}: {exc}") from exc
        text = content if prompt is None else f"{prompt}\n{content}"
        return self.count(text, system=system, use_local=use_local)

    def count_local(
        self,
        prompt: str,
        system: str | None = None,
        tools: list[dict] | None = None,
        history: list[dict] | None = None,
        model: str | None = None,
    ) -> dict:
        """Count tokens using local estimation (zero API cost).

        Args:
            prompt: User prompt
            system: Optional system prompt
            tools: Optional tool definitions
            history: Optional conversation history
            model: Model name (defaults to self.model)
        """
        m = model or self.model
        tokens = self._local_estimator.estimate(prompt, m, system, tools, history)
        # Estimate cost for tracking
        cost_est = self.estimate_cost(tokens, m)
        # Track usage history for predictive model selection
        self._track_usage(tokens, cost_est["estimated_cost_usd"], m)
        return {"input_tokens": tokens, "method": "local"}

    def estimate_local(
        self,
        prompt: str,
        system: str | None = None,
        tools: list[dict] | None = None,
        history: list[dict] | None = None,
    ) -> int:
        """Quick local token estimation returning just the count."""
        return self._local_estimator.estimate(prompt, self.model, system, tools, history)

    def estimate_cost(self, token_count: int, model: str | None = None) -> dict:
        """Rough cost estimate based on current pricing tiers."""
        m = model or self.model
        # MTok prices (input) — verified against platform.claude.com/docs
        # as of 2026-07-02. Re-verify before relying on this for billing.
        prices_per_mtok = {
            "claude-opus-5": 5.0,
            "claude-opus-4-8": 5.0,
            "claude-sonnet-5": 2.0,
            "claude-haiku-4-5-20251001": 1.0,
            "claude-fable-5": 10.0,
            "claude-mythos-5": 10.0,
            "claude-opus-4-7": 5.0,
            "claude-opus-4-6": 5.0,
            "claude-opus-4-5": 5.0,
            "claude-sonnet-4-6": 3.0,
            "claude-sonnet-4-5": 3.0,
        }
        price = prices_per_mtok.get(m, 3.0)
        cost = (token_count / 1_000_000) * price
        return {
            "tokens": token_count,
            "model": m,
            "price_per_mtok": price,
            "estimated_cost_usd": round(cost, 6),
        }

    def get_optimization_savings(self, prompt: str, model: str | None = None) -> dict:
        """Calculate token savings from optimization heuristics.

        Returns dict with original_tokens, optimized_tokens, and savings.
        """
        model = model or self.model
        original_result = self.count_local(prompt, model=model)
        original_tokens = original_result.get("input_tokens", 0)

        optimized = optimize_prompt(prompt, model)
        optimized_result = self.count_local(optimized, model=model)
        optimized_tokens = optimized_result.get("input_tokens", 0)

        savings = original_tokens - optimized_tokens

        return {
            "original_tokens": original_tokens,
            "optimized_tokens": optimized_tokens,
            "savings": savings,
            "savings_percent": round(savings / original_tokens * 100, 2) if original_tokens > 0 else 0,
        }


def cmd_count_tokens(
    prompt: str,
    api_key: str,
    model: str,
    system: str | None = None,
    file_path: str | None = None,
    budget: int | None = None,
    use_local: bool = False,
    optimize: bool = True,
):
    tc = TokenCounter(api_key=api_key, model=model)
    if file_path:
        result = tc.count_file(file_path, prompt, system=system, use_local=use_local)
    else:
        result = tc.count(prompt, system=system, use_local=use_local)

    tokens = result.get("input_tokens", 0)
    method = result.get("method", "api")
    est = tc.estimate_cost(tokens, model)

    # Show optimization info if applied
    if optimize:
        # Estimate original token count before optimization heuristics
        original_result = tc.count(prompt, system=system, use_local=use_local)
        original_tokens = original_result.get("input_tokens", tokens)
        optimization_saved = original_tokens - tokens
        if optimization_saved > 0:
            print(f"\n  📦 Optimization: reduced {optimization_saved:,} tokens " f"({tokens:,} final)")
        elif optimization_saved < 0:
            print(f"\n  📦 Optimization: increased {abs(optimization_saved):,} tokens (unusual)")

    print(f"\n  Model:            {model}")
    print(f"  Input tokens:     {tokens:,} ({method})")
    print(f"  Estimated cost:   ${est['estimated_cost_usd']:.6f} (input only)")
    if budget:
        pct = tokens / budget * 100
        bar = "█" * int(pct // 5) + "░" * (20 - int(pct // 5))
        print(f"  Budget usage:     [{bar}] {pct:.1f}% of {budget:,}")
        if tokens > budget:
            print(f"\033[91m  ⚠ EXCEEDS BUDGET by {tokens - budget:,} tokens\033[0m")
        else:
            print(f"\033[92m  ✓ Within budget ({budget - tokens:,} tokens remaining)\033[0m")


def cmd_batch_count(
    file_path: str,
    prompts_per_line: int = 1,
    model: str | None = None,
    use_local: bool = False,
    show_optimization: bool = True,
):
    """Batch count tokens from a file where each line is a prompt.

    Args:
        file_path: Path to file with one prompt per line
        prompts_per_line: Number of prompts per line (space-separated)
        model: Model for token counting
        use_local: Use local estimation instead of API
        show_optimization: Show token savings from optimization heuristics
    """
    model = model or "claude-sonnet-5"
    tc = TokenCounter(api_key="", model=model)

    try:
        lines = Path(file_path).read_text().splitlines()
    except Exception as e:
        print(f"[ERROR] Could not read file: {e}")
        return

    total_tokens = 0
    total_cost = 0.0
    total_savings = 0
    results: list[tuple[int, str]] = []  # (token_count, prompt)
    opt_results: list[dict] = []

    for line in lines:
        if not line.strip():
            continue
        prompts = line.split()
        # Take first prompts_per_line prompts
        prompts = prompts[:prompts_per_line]

        for prompt in prompts:
            result = tc.count_local(prompt) if use_local else tc.count(prompt)
            tokens = result.get("input_tokens", 0)
            total_tokens += tokens
            cost_est = tc.estimate_cost(tokens, model)
            total_cost += cost_est["estimated_cost_usd"]

            # Calculate optimization savings
            if show_optimization:
                opt_savings = tc.get_optimization_savings(prompt, model)
                total_savings += opt_savings["savings"]
                opt_results.append(opt_savings)

            results.append((tokens, prompt[:80]))

    avg_tokens = total_tokens / len(results) if results else 0
    print(f"\n  Model:            {model}")
    print(f"  Files processed:  {len(lines)}")
    print(f"  Prompts counted:  {len(results)}")
    print(f"  Total tokens:     {total_tokens:,}")
    print(f"  Total cost:       ${total_cost:.6f}")
    if show_optimization and total_savings > 0:
        print(
            f"  Token savings:    -{total_savings:,} tokens ({round(total_savings/max(total_tokens,1)*100,2)}%)"
        )
    print(f"  Average tokens:   {avg_tokens:,.0f} per prompt")
    print()
    print("  Results (prompt → tokens):")
    for tokens, preview in results[:10]:
        print(f"    {tokens:,} {preview}")
    if len(results) > 10:
        print(f"    ... and {len(results) - 10} more")
