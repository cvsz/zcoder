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

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any


# Model-specific character-to-token multipliers
# Based on typical tokenizer behavior for each model family
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

# Token overhead for common message components
SYSTEM_PROMPT_OVERHEAD_FACTOR = 1.0  # System prompt counted as regular text
TOOLS_OVERHEAD_PER_TOOL = 50  # Base tokens per tool definition
TOOLS_SCHEMA_CHAR_FACTOR = 0.15  # Additional tokens per schema character


@dataclass
class TokenEstimate:
    """Result of token estimation."""
    input_tokens: int
    model: str
    method: str  # "local" or "api"
    breakdown: dict[str, int] | None = None


class LocalTokenEstimator:
    """Fast local token estimation without API calls."""

    def __init__(self):
        self._cache: dict[str, int] = {}

    def _get_multiplier(self, model: str) -> float:
        """Get character-to-token multiplier for a model."""
        # Try exact match first
        if model in MODEL_MULTIPLIERS:
            return MODEL_MULTIPLIERS[model]
        
        # Try prefix match (e.g., "claude-sonnet-5-20260101")
        for prefix, mult in MODEL_MULTIPLIERS.items():
            if model.startswith(prefix):
                return mult
        
        return MODEL_MULTIPLIERS["default"]

    def _is_code(self, text: str) -> bool:
        """Heuristic to detect if text is code."""
        code_indicators = [
            r'\bdef\b', r'\bclass\b', r'\bfunction\b', r'\bimport\b',
            r'\bfrom\b', r'\breturn\b', r'\bif\b.*:',
            r'\bfor\b.*:', r'\bwhile\b.*:', r'\{', r'\}',
            r'\[', r'\]', r'\(\)', r'->', r'=>',
            r'SELECT\b', r'INSERT\b', r'UPDATE\b', r'DELETE\b',
            r'CREATE\b', r'TABLE\b', r'INDEX\b',
        ]
        text_lower = text.lower()
        return any(re.search(pattern, text_lower) for pattern in code_indicators)

    def _estimate_chars(self, text: str, is_code: bool) -> int:
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

    def _estimate_words(self, text: str) -> int:
        """Estimate tokens from word count (fallback)."""
        if not text:
            return 0
        words = len(text.split())
        # ~1.3 tokens per word for English
        return max(1, int(words * 1.3))

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
        # Create cache key
        cache_key = f"{model}:{prompt}:{system}:{tools}:{history}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        is_code = self._is_code(prompt)
        multiplier = self._get_multiplier(model)

        # Estimate prompt tokens
        prompt_tokens = self._estimate_chars(prompt, is_code)

        # Estimate system prompt tokens
        system_tokens = 0
        if system:
            system_is_code = self._is_code(system)
            system_tokens = self._estimate_chars(system, system_is_code)

        # Estimate history tokens
        history_tokens = 0
        if history:
            for msg in history:
                content = msg.get("content", "")
                if content:
                    msg_is_code = self._is_code(content)
                    history_tokens += self._estimate_chars(content, msg_is_code)

        # Estimate tools tokens
        tools_tokens = 0
        if tools:
            for tool in tools:
                tools_tokens += TOOLS_OVERHEAD_PER_TOOL
                # Add schema tokens
                import json
                schema_str = json.dumps(tool.get("input_schema", {}))
                tools_tokens += int(len(schema_str) * TOOLS_SCHEMA_CHAR_FACTOR)

        total = prompt_tokens + system_tokens + history_tokens + tools_tokens
        # Apply model multiplier
        total = int(total * (multiplier / 0.25))  # Normalize to base 0.25

        # Cache result (limit cache size)
        if len(self._cache) > 1000:
            self._cache.clear()
        self._cache[cache_key] = total

        return total

    def estimate_detailed(
        self,
        prompt: str,
        model: str = "claude-sonnet-5",
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> TokenEstimate:
        """Estimate with detailed breakdown."""
        is_code = self._is_code(prompt)
        
        prompt_tokens = self._estimate_chars(prompt, is_code)
        system_tokens = 0
        if system:
            system_tokens = self._estimate_chars(system, self._is_code(system))
        
        history_tokens = 0
        if history:
            for msg in history:
                content = msg.get("content", "")
                if content:
                    history_tokens += self._estimate_chars(content, self._is_code(content))
        
        tools_tokens = 0
        if tools:
            for tool in tools:
                tools_tokens += TOOLS_OVERHEAD_PER_TOOL
                import json
                schema_str = json.dumps(tool.get("input_schema", {}))
                tools_tokens += int(len(schema_str) * TOOLS_SCHEMA_CHAR_FACTOR)

        total = prompt_tokens + system_tokens + history_tokens + tools_tokens
        multiplier = self._get_multiplier(model)
        total = int(total * (multiplier / 0.25))

        return TokenEstimate(
            input_tokens=total,
            model=model,
            method="local",
            breakdown={
                "prompt": prompt_tokens,
                "system": system_tokens,
                "history": history_tokens,
                "tools": tools_tokens,
            },
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


def estimate_tokens_detailed(
    prompt: str,
    model: str = "claude-sonnet-5",
    system: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    history: list[dict[str, Any]] | None = None,
) -> TokenEstimate:
    """Convenience function for detailed token estimation."""
    return _default_estimator.estimate_detailed(prompt, model, system, tools, history)