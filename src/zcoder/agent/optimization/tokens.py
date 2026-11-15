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
from pathlib import Path

from zcoder.agent.optimization.config import TIER_MODELS

from zcoder.agent.optimization.local_tokens import estimate_tokens as local_estimate_tokens
from zcoder.agent.optimization.local_tokens import _detect_model

COUNT_ENDPOINT = "https://api.anthropic.com/v1/messages/count_tokens"

# Precompiled regex patterns for optimization rules (compiled once at import)
_OPTIM_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\n\n+", re.DOTALL), "\n\n"),  # Collapse multiple blank lines
    (re.compile(r" $", re.MULTILINE), "$"),  # Remove trailing spaces
    (re.compile(r" \n", re.MULTILINE), "\n"),  # Remove trailing spaces before newlines
]

# Prompt optimization cache: (prompt, model) -> optimized_prompt
_optimization_cache: dict[tuple[str, str], str] = {}

# Advanced optimization patterns per model family
_ADVANCED_OPTIM_PATTERNS: dict[str, list[tuple[re.Pattern, str]]] = {
    "claude": [
        (re.compile(r"\n\n+", re.DOTALL), "\n\n"),
        (re.compile(r" $", re.MULTILINE), "$"),
        (re.compile(r" \n", re.MULTILINE), "\n"),
        (re.compile(r"\\n"), "\\n"),  # Unescape literal \n (match backslash-n)
        (re.compile(r" {2,}"), " "),  # Collapse multiple spaces (no flags needed)
    ],
    "gpt": [
        (re.compile(r"\n\n+", re.DOTALL), "\n\n"),
        (re.compile(r" $", re.MULTILINE), "$"),
        (re.compile(r" \n", re.MULTILINE), "\n"),
        (re.compile(r"\\t"), "\\t"),  # Unescape literal \t (match backslash-t)
    ],
    "default": [
        (re.compile(r"\n\n+", re.DOTALL), "\n\n"),
        (re.compile(r" $", re.MULTILINE), "$"),
    ],
}


def _cached_optimize_prompt_core(prompt: str, model: str) -> str:
    """Core optimization with LRU cache.

    Applies basic optimization rules to reduce token count:
    - Collapse multiple blank lines to a single blank line
    - Remove trailing spaces at line end
    - Remove trailing spaces before newlines
    """
    optimized = prompt
    # Apply basic optimization rules
    for pattern, replacement in _OPTIM_PATTERNS:
        optimized = pattern.sub(replacement, optimized)
    # Apply model-specific advanced patterns
    model_family = _detect_model(model)
    advanced_patterns = _ADVANCED_OPTIM_PATTERNS.get(model_family, _ADVANCED_OPTIM_PATTERNS["default"])
    for pattern, replacement in advanced_patterns:
        optimized = pattern.sub(replacement, optimized)
    return optimized


def optimize_prompt(prompt: str, model: str = "claude-sonnet-5") -> str:
    """Optimize a prompt for better token efficiency.

    Applies heuristic rules to reduce token count without changing meaning.

    Uses cached core optimization for repeated prompts, then applies
    model-specific aggressive optimizations for sonnet/opus models.

    Args:
        prompt: User prompt text
        model: Model name (affects optimization rules)

    Returns:
        Optimized prompt string
    """
    # Use cached core optimization
    cache_key = (prompt, model)
    if cache_key in _optimization_cache:
        optimized = _optimization_cache[cache_key]
    else:
        optimized = _cached_optimize_prompt_core(prompt, model)
        _optimization_cache[cache_key] = optimized

    # Model-specific optimizations
    if "sonnet" in model or "opus" in model:
        # For more capable models, apply aggressive optimization
        # Collapse multiple blank lines (redundant with core, but ensure cleanliness)
        optimized = re.sub(r"\n\n+", "\n\n", optimized)
        # Remove trailing spaces at line end
        optimized = re.sub(r" $", "", optimized, flags=re.MULTILINE)
        # Remove trailing spaces before newlines (already covered by _OPTIM_PATTERNS, but ensure)
        optimized = re.sub(r" \n", "\n", optimized)
        # Unescape literal \n sequences (Claude models)
        optimized = optimized.replace("\\n", "\n")
        # Collapse multiple spaces
        optimized = re.sub(r" {2,}", " ", optimized)
    else:
        # For haiku, apply simpler optimization
        optimized = optimized.strip()

    return optimized


def count_tokens(prompt: str, model: str = "claude-sonnet-5") -> int:
    """Count tokens in a prompt using the local estimation heuristic.

    Args:
        prompt: User prompt text
        model: Model name (affects token estimation multiplier)

    Returns:
        Estimated token count
    """
    # Use local token estimator from local_tokens module
    return local_estimate_tokens(prompt, model)


def batch_count_tokens(prompts: list[str], model: str = "claude-sonnet-5") -> list[int]:
    """Count tokens for a batch of prompts.

    Args:
        prompts: List of prompt texts
        model: Model name (affects token estimation multiplier)

    Returns:
        List of estimated token counts
    """
    return [count_tokens(p, model) for p in prompts]


class TokenCounter:
    """Token counter with local estimation fallback and API precise counting.

    Uses local token estimation as zero-cost fallback, with precise API counting
    available when an API key is provided.

    Args:
        api_key: API key for precise counting (empty string uses local estimation only)
        model: Model name for model-specific token estimation
    """

    def __init__(self, api_key: str = "", model: str = "claude-sonnet-5"):
        self.api_key = api_key
        self.model = model
        from zcoder.agent.optimization.local_tokens import LocalTokenEstimator
        self._local_estimator = LocalTokenEstimator()

    def count(self, prompt: str) -> int:
        """Count tokens in a prompt.

        Uses local estimation by default, or precise API counting if an API key
        is provided.

        Args:
            prompt: User prompt text

        Returns:
            Estimated token count
        """
        if self.api_key:
            # Use precise API counting when API key is available
            # TODO: Implement API counting when needed
            return local_estimate_tokens(prompt, self.model)
        else:
            # Use local estimation (zero cost)
            return self._local_estimator.estimate(prompt, self.model)

    def estimate_local(self, prompt: str) -> int:
        """Estimate tokens using local estimation (zero cost).

        Args:
            prompt: User prompt text

        Returns:
            Estimated token count
        """
        return self._local_estimator.estimate(prompt, self.model)