"""
claude_tokens.py — Token Counting
AI Model Coder CLI v1.8.0

Count tokens BEFORE sending a request (no API cost incurred).
Uses the /v1/messages/count_tokens endpoint.

CLI flags:
  --count-tokens           Count tokens in a prompt without calling the model
  --count-tokens-file F    Count tokens including a file's content
  --count-budget N         Warn if token count exceeds N
"""

import json
import sys
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

from exceptions import AICoderError
from resilience import CircuitBreaker, retry, urlopen_json

COUNT_ENDPOINT = "https://api.anthropic.com/v1/messages/count_tokens"
_breaker = CircuitBreaker(failure_threshold=5, reset_timeout=30)


class TokenCounter:
    """Count tokens without sending to the model."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-5"):
        self.api_key = api_key
        self.model   = model

    def count(self, prompt: str, system: Optional[str] = None,
              tools: list[dict] = None, history: list[dict] = None) -> dict:
        messages = list(history or [])
        messages.append({"role": "user", "content": prompt})

        payload: dict = {"model": self.model, "messages": messages}
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = tools

        headers = {
            "Content-Type":      "application/json",
            "x-api-key":         self.api_key,
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
        except AICoderError as e:
            raise RuntimeError(f"Token count failed: {e.message}") from e

    @retry(max_attempts=4, base_delay=1.0, max_delay=15.0, breaker=_breaker)
    def _call(self, req: "urllib.request.Request") -> dict:
        return urlopen_json(req, timeout=30)

    def count_file(self, file_path: str, prompt: str,
                   system: Optional[str] = None) -> dict:
        content = Path(file_path).read_text()
        full    = f"File:\n```\n{content}\n```\n\n{prompt}"
        return self.count(full, system=system)

    def estimate_cost(self, token_count: int, model: str = None) -> dict:
        """Rough cost estimate based on current pricing tiers."""
        m = model or self.model
        # MTok prices (input) — verified against platform.claude.com/docs
        # as of 2026-07-02. Re-verify before relying on this for billing.
        prices_per_mtok = {
            "claude-opus-4-8":            5.0,
            "claude-sonnet-5":            3.0,
            "claude-haiku-4-5-20251001":  1.0,
            "claude-fable-5":            10.0,
            "claude-mythos-5":           10.0,
            "claude-opus-4-7":            5.0,
            "claude-opus-4-6":            5.0,
            "claude-opus-4-5":            5.0,
            "claude-sonnet-4-6":          3.0,
            "claude-sonnet-4-5":          3.0,
        }
        price = prices_per_mtok.get(m, 3.0)
        cost  = (token_count / 1_000_000) * price
        return {
            "tokens":           token_count,
            "model":            m,
            "price_per_mtok":   price,
            "estimated_cost_usd": round(cost, 6),
        }


def cmd_count_tokens(prompt: str, api_key: str, model: str,
                     system: str = None, file_path: str = None,
                     budget: int = None):
    tc = TokenCounter(api_key=api_key, model=model)
    if file_path:
        result = tc.count_file(file_path, prompt, system=system)
    else:
        result = tc.count(prompt, system=system)

    tokens = result.get("input_tokens", 0)
    est    = tc.estimate_cost(tokens, model)

    print(f"\n  Model:            {model}")
    print(f"  Input tokens:     {tokens:,}")
    print(f"  Estimated cost:   ${est['estimated_cost_usd']:.6f} (input only)")
    if budget:
        pct = tokens / budget * 100
        bar = "█" * int(pct // 5) + "░" * (20 - int(pct // 5))
        print(f"  Budget usage:     [{bar}] {pct:.1f}% of {budget:,}")
        if tokens > budget:
            print(f"\033[91m  ⚠ EXCEEDS BUDGET by {tokens-budget:,} tokens\033[0m")
        else:
            print(f"\033[92m  ✓ Within budget ({budget-tokens:,} tokens remaining)\033[0m")
