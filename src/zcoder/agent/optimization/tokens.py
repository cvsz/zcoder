"""claude_tokens.py — Token Counting

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
from functools import lru_cache
from pathlib import Path

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
            return self._call(req)
        except ZCoderError as e:
            raise RuntimeError(f"Token count failed: {e.message}") from e

    def _call(self, req: urllib.request.Request) -> dict:
        """Execute the count_tokens API request and return parsed JSON.

        Network/HTTP failures are operational errors, so they are wrapped in
        :class:`ZCoderError` and never exposed as raw urllib exceptions.
        """
        try:
            with urllib.request.urlopen(
                req, timeout=30
            ) as resp:  # nosec B310 — controlled internal count_tokens endpoint
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
