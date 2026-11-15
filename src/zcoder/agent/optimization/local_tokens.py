"""
local_tokens.py — Local Token Estimation

Provides fast, zero-API-cost token estimation using character/word-based heuristics.
Integrates with existing TokenCounter for API fallback when precise counts needed.

Estimation strategy:
- English text: ~4 characters per token (0.25 tokens/char)
- Code: ~3 characters per token (0.33 tokens/char)
- With system prompt/tools: additional overhead
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from zcoder.agent.optimization.config import TIER_MODELS

# Model-specific character-to-token multipliers
# Based on typical tokenizer behavior for each model family
# (imported from config to avoid circular imports)
MODEL_MULTIPLIERS: dict[str, float] = {
    # Anthropic models
    "claude-sonnet-5": 0.25,
    "claude-opus-5": 0.25,
    "claude-haiku-4-5-20251001": 0.25,
    "claude-fable-5": 0.25,
    "claude-mythos-5": 0.25,
    "claude-opus-4-8": 0.25,
    "claude-opus-4-7": 0.25,
    "claude-opus-4-6": 0.25,
    "claude-opus-4-5": 0.25,
    "claude-sonnet-4-6": 0.25,
    "claude-sonnet-4-5": 0.25,
    # OpenAI models
    "gpt-4": 0.25,
    "gpt-4o": 0.25,
    "gpt-4-turbo": 0.25,
    "gpt-3.5-turbo": 0.25,
    # Local/other models (default)
    "default": 0.3,  # More conservative for unknown models
}

# Cached model multipliers (memoized lookups)
_MULTIPLIER_CACHE: dict[str, float] = {}
_MULTIPLIER_CACHE_VERSION: int = 0  # Version bump for cache invalidation

# Token overhead for common message components
SYSTEM_PROMPT_OVERHEAD_FACTOR = 1.0  # System prompt counted as regular text
TOOLS_OVERHEAD_PER_TOOL = 50  # Base tokens per tool definition
TOOLS_SCHEMA_CHAR_FACTOR = 0.15  # Additional tokens per schema character

# Precompiled regex patterns for code detection (module-level, compiled once)
_CODE_PATTERNS_COMPILED: list[re.Pattern] = []
_CODE_PATTERN_STRINGS = [
    r"\bdef\b",
    r"\bclass\b",
    r"\bfunction\b",
    r"\bimport\b",
    r"\bfrom\b",
    r"\breturn\b",
    r"\bif\b.*:",
    r"\bfor\b.*:",
    r"\bwhile\b.*:",
    r"\{",
    r"\}",
    r"\[",
    r"\]",
    r"\(\)",
    r"->",
    r"=>",
    r"SELECT\b",
    r"INSERT\b",
    r"UPDATE\b",
    r"DELETE\b",
    r"CREATE\b",
    r"TABLE\b",
    r"INDEX\b",
]
for pattern in _CODE_PATTERN_STRINGS:
    _CODE_PATTERNS_COMPILED.append(re.compile(pattern, re.IGNORECASE))

# Model-specific code detection patterns
# Each model family has different keyword patterns and tokenizer behaviors
_MODEL_CODE_PATTERNS: dict[str, list[re.Pattern]] = {
    "claude": [
        re.compile(r"\bdef\b", re.IGNORECASE),
        re.compile(r"\bclass\b", re.IGNORECASE),
        re.compile(r"\bawait\b", re.IGNORECASE),
        re.compile(r"\btry:\b", re.IGNORECASE),
        re.compile(r"\bcatch\b", re.IGNORECASE),
    ],
    "gpt": [
        re.compile(r"\bfunction\b", re.IGNORECASE),
        re.compile(r"\bclass\b", re.IGNORECASE),
        re.compile(r"\breturn\b", re.IGNORECASE),
        re.compile(r"=>\b", re.IGNORECASE),
    ],
    "default": [
        re.compile(r"\bdef\b", re.IGNORECASE),
        re.compile(r"\bclass\b", re.IGNORECASE),
        re.compile(r"\bimport\b", re.IGNORECASE),
        re.compile(r"\bfor\b.*:", re.IGNORECASE),
        re.compile(r"\bwhile\b.*:", re.IGNORECASE),
    ],
}


def _detect_model(model: str) -> str:
    """Detect the model family from model name."""
    model_lower = model.lower()
    if "claude" in model_lower:
        return "claude"
    elif "gpt" in model_lower or "openai" in model_lower:
        return "gpt"
    return "default"


def _is_code_model_specific(text: str, model: str) -> bool:
    """Heuristic to detect if text is code using model-specific patterns."""
    if not text:
        return False

    model_family = _detect_model(model)
    patterns = _MODEL_CODE_PATTERNS.get(model_family, _MODEL_CODE_PATTERNS["default"])

    text_lower = text.lower()
    for pattern in patterns:
        if pattern.search(text_lower):
            return True
    return False


def _get_multiplier(model: str, cache: dict | None = None) -> float:
    """Get character-to-token multiplier for a model with optional cache."""
    global _MULTIPLIER_CACHE_VERSION
    # Try exact match first
    if model in MODEL_MULTIPLIERS:
        if cache is not None and model not in cache:
            cache[model] = MODEL_MULTIPLIERS[model]
        return MODEL_MULTIPLIERS[model]

    # Try prefix match (e.g., "claude-sonnet-5-20260101")
    for prefix, mult in MODEL_MULTIPLIERS.items():
        if model.startswith(prefix):
            if cache is not None and prefix not in cache:
                cache[prefix] = mult
            return mult

    # Use provided cache or global cache
    if cache is not None:
        if model not in cache:
            cache[model] = MODEL_MULTIPLIERS.get(model, MODEL_MULTIPLIERS["default"])
        return cache[model]

    # Cache miss — bump version to invalidate stale cache entries
    _MULTIPLIER_CACHE_VERSION += 1
    return MODEL_MULTIPLIERS["default"]


def _estimate_chars(text: str, is_code: bool) -> int:
    """Estimate tokens from character count."""
    if not text:
        return 0

    char_count = len(text)
    if is_code:
        # Code: ~3 chars per token
        return max(1, int(char_count / 3))
    else:
        # Natural language: ~4 chars per token
        return max(1, int(char_count / 4))


def _estimate_mixed(text: str, code_ratio: float = 0.5) -> int:
    """Estimate tokens for mixed code/non-code content.

    Args:
        text: The text to estimate
        code_ratio: Estimated proportion of code content (0.0 to 1.0)
            Default 0.5 assumes balanced mix

    Returns:
        Estimated token count accounting for mixed content
    """
    if not text:
        return 0

    char_count = len(text)
    # Split estimation based on code ratio
    code_chars = int(char_count * code_ratio)
    non_code_chars = char_count - code_chars

    # Only award a minimum of one token when the slice actually contains
    # characters; an empty slice (e.g. non-code text with code_ratio=0.0)
    # must not contribute a spurious token to the estimate.
    code_tokens = int(code_chars / 3) if code_chars > 0 else 0
    non_code_tokens = int(non_code_chars / 4) if non_code_chars > 0 else 0

    total = code_tokens + non_code_tokens
    # Non-empty text always estimates at least one token (matches
    # _estimate_chars), but never a spurious code token for non-code input.
    return max(1, total)


def _estimate_words(text: str) -> int:
    """Estimate tokens from word count (fallback)."""
    if not text:
        return 0
    words = len(text.split())
    # ~1.3 tokens per word for English
    return max(1, int(words * 1.3))


@dataclass
class TokenEstimate:
    """Result of token estimation."""

    input_tokens: int
    model: str
    method: str = "local"
    breakdown: dict[str, int] | None = None


class LocalTokenEstimator:
    """Fast local token estimation without API calls."""

    def __init__(self):
        self._cache: dict[str, int] = {}

    def estimate(
        self,
        prompt: str,
        model: str = "claude-sonnet-5",
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> int:
        """Estimate token count for a request.

        Args:
            prompt: User prompt text
            model: Model name for model-specific estimation
            system: Optional system prompt
            tools: Optional tool definitions
            history: Optional conversation history

        Returns:
            Estimated input token count
        """
        global _MULTIPLIER_CACHE_VERSION
        # Create cache key
        cache_key = f"{model}:{prompt}:{system}:{tools}:{history}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Use cached multiplier lookup (memoized at module level)
        if model not in _MULTIPLIER_CACHE:
            _MULTIPLIER_CACHE[model] = _get_multiplier(model, _MULTIPLIER_CACHE)
        multiplier = _MULTIPLIER_CACHE[model]

        # Detect code type using model-specific heuristics
        is_code = _is_code_model_specific(prompt, model)

        # Estimate prompt tokens with mixed content support
        prompt_tokens = _estimate_mixed(prompt, code_ratio=0.5 if is_code else 0.0)

        # Estimate system prompt tokens
        system_tokens = 0
        if system:
            system_is_code = _is_code_model_specific(system, model) if system else False
            system_tokens = _estimate_mixed(system, code_ratio=0.5 if system_is_code else 0.0)

        # Estimate history tokens
        history_tokens = 0
        if history:
            for msg in history:
                content = msg.get("content", "")
                if content:
                    history_tokens += _estimate_mixed(
                        content, code_ratio=0.5 if _is_code_model_specific(content, model) else 0.0
                    )

        # Estimate tools tokens
        tools_tokens = 0
        if tools:
            for tool in tools:
                tools_tokens += TOOLS_OVERHEAD_PER_TOOL
                # Add schema tokens
                schema_str = json.dumps(tool.get("input_schema", {}))
                tools_tokens += int(len(schema_str) * TOOLS_SCHEMA_CHAR_FACTOR)

        total = prompt_tokens + system_tokens + history_tokens + tools_tokens
        # Apply model multiplier
        total = int(total * (multiplier / 0.25))  # Normalize to base 0.25

        # Cache result (limit cache size, bump version on cache clear)
        if len(self._cache) > 1000:
            self._cache.clear()
            _MULTIPLIER_CACHE_VERSION += 1
        self._cache[cache_key] = total

        return total

    def estimate_batch(self, prompts: list[str], model: str = "claude-sonnet-5") -> list[int]:
        """Estimate tokens for a batch of prompts efficiently.

        Args:
            prompts: List of prompt texts
            model: Model name for estimation

        Returns:
            List of estimated token counts
        """
        # Use module-level cache key prefix to avoid re-computation
        # Pre-compute multiplier for the model
        if model not in _MULTIPLIER_CACHE:
            _MULTIPLIER_CACHE[model] = _get_multiplier(model, _MULTIPLIER_CACHE)
        multiplier = _MULTIPLIER_CACHE[model]

        results: list[int] = []
        for prompt in prompts:
            # Re-use the same cache key logic as estimate()
            is_code = _is_code_model_specific(prompt, model)
            prompt_tokens = _estimate_mixed(prompt, code_ratio=0.5 if is_code else 0.0)
            total = int(prompt_tokens * (multiplier / 0.25))
            results.append(total)
        return results

    def estimate_detailed(
        self,
        prompt: str,
        model: str = "claude-sonnet-5",
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> TokenEstimate:
        """Estimate with detailed breakdown."""
        is_code = _is_code_model_specific(prompt, model)

        prompt_tokens = _estimate_mixed(prompt, code_ratio=0.5 if is_code else 0.0)
        system_tokens = 0
        if system:
            system_is_code = _is_code_model_specific(system, model) if system else False
            system_tokens = _estimate_mixed(system, code_ratio=0.5 if system_is_code else 0.0)

        history_tokens = 0
        if history:
            for msg in history:
                content = msg.get("content", "")
                if content:
                    history_tokens += _estimate_mixed(
                        content, code_ratio=0.5 if _is_code_model_specific(content, model) else 0.0
                    )

        tools_tokens = 0
        if tools:
            for tool in tools:
                tools_tokens += TOOLS_OVERHEAD_PER_TOOL
                schema_str = json.dumps(tool.get("input_schema", {}))
                tools_tokens += int(len(schema_str) * TOOLS_SCHEMA_CHAR_FACTOR)

        total = prompt_tokens + system_tokens + history_tokens + tools_tokens
        multiplier = _get_multiplier(model)
        total = int(total * (multiplier / 0.25))

        # Build detailed breakdown with code/non-code analysis
        breakdown: dict[str, Any] = {
            "prompt": prompt_tokens,
            "system": system_tokens,
            "history": history_tokens,
            "tools": tools_tokens,
        }

        # Add model-specific code detection info
        breakdown["is_code"] = 1 if is_code else 0
        breakdown["model_family"] = _detect_model(model)
        breakdown["model"] = model  # Actual model name, not hashed identifier

        return TokenEstimate(
            input_tokens=total,
            model=model,
            method="local",
            breakdown=breakdown,
        )

    def clear_cache(self):
        """Clear the estimation cache."""
        self._cache.clear()


# Global instance for convenience
_default_estimator = LocalTokenEstimator()


def estimate_tokens(
    prompt: str,
    model: str = "claude-sonnet-5",
    system: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    history: list[dict[str, Any]] | None = None,
) -> int:
    """Convenience function for quick token estimation."""
    return _default_estimator.estimate(prompt, model, system, tools, history)


def predict_best_model(
    prompt: str,
    available_models: list[str] | None = None,
    prefer_latency: bool = False,
) -> dict[str, Any]:
    """Predict the best model for a given prompt based on complexity and cost.

    Args:
        prompt: User prompt text
        available_models: List of available model names (defaults to TIER_MODELS)
        prefer_latency: If True, prefer faster models even for complex prompts

    Returns:
        Dict with 'model', 'complexity', 'estimated_cost', 'estimated_tokens'
    """
    from zcoder.agent.optimization.cost import classify_complexity, estimate_cost, select_model

    if available_models is None:
        available_models = TIER_MODELS

    complexity = classify_complexity(prompt)
    estimated_tokens = estimate_tokens(prompt, "claude-sonnet-5")

    # Select optimal model
    if prefer_latency:
        # Always prefer haiku for latency-sensitive tasks
        model = select_model(complexity, prefer_latency=True)
    else:
        model = select_model(complexity)

    # Estimate cost with current model
    cost = estimate_cost(model, estimated_tokens, estimated_tokens // 2)

    # Check if switching models would provide significant savings
    if len(available_models) > 1:
        for alt_model in available_models:
            if alt_model == model:
                continue
            alt_cost = estimate_cost(alt_model, estimated_tokens, estimated_tokens // 2)
            # Switch if at least 30% cheaper and model supports the complexity
            if alt_cost < cost * 0.7:
                model = alt_model
                cost = alt_cost
                complexity = "medium"  # Reset complexity for new model

    return {
        "model": model,
        "complexity": complexity,
        "estimated_cost": cost,
        "estimated_tokens": estimated_tokens,
    }


def estimate_tokens_detailed(
    prompt: str,
    model: str = "claude-sonnet-5",
    system: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    history: list[dict[str, Any]] | None = None,
) -> TokenEstimate:
    """Convenience function for detailed token estimation."""
    return _default_estimator.estimate_detailed(prompt, model, system, tools, history)


def detect_code_patterns(text: str, model: str = "claude-sonnet-5") -> dict:
    """Detect code patterns in text using model-specific heuristics.

    Args:
        text: Text to analyze
        model: Model name for pattern detection

    Returns:
        Dict with code detection results
    """
    is_code = _is_code_model_specific(text, model)
    model_family = _detect_model(model)
    return {
        "is_code": is_code,
        "model_family": model_family,
        "text_length": len(text),
    }
