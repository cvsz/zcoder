"""tests/unit/test_local_token_estimation.py — Tests for local token estimation."""

from __future__ import annotations

import time

import pytest

from zcoder.agent.optimization.local_tokens import LocalTokenEstimator


class TestLocalTokenEstimation:
    """Tests for local token estimation accuracy and speed."""

    def test_local_estimation_accuracy_english(self):
        """Test estimation accuracy for English text."""
        estimator = LocalTokenEstimator()
        # "Hello world" * 100 = ~200 words, ~250-300 tokens
        prompt = "Hello world " * 100
        tokens = estimator.estimate(prompt, "claude-sonnet-5")
        assert 200 < tokens < 400, f"Expected 200-400 tokens, got {tokens}"

    def test_local_estimation_accuracy_code(self):
        """Test estimation accuracy for code (more tokens per char)."""
        estimator = LocalTokenEstimator()
        # Code has more tokens per character
        code = "def fibonacci(n):\n    if n <= 1: return n\n    return fibonacci(n-1) + fibonacci(n-2)\n" * 20
        tokens = estimator.estimate(code, "claude-sonnet-5")
        # Code typically ~3-4 chars per token
        assert tokens > 200, f"Expected >200 tokens for code, got {tokens}"

    def test_local_estimation_speed(self):
        """Test that local estimation is fast (<1ms per estimate)."""
        estimator = LocalTokenEstimator()
        prompt = "Test prompt for speed measurement " * 100

        # Warm up
        for _ in range(10):
            estimator.estimate(prompt, "claude-sonnet-5")

        # Measure
        start = time.perf_counter()
        for _ in range(1000):
            estimator.estimate(prompt, "claude-sonnet-5")
        elapsed = time.perf_counter() - start

        # 1000 estimates in <1 second = <1ms each
        assert elapsed < 1.0, f"1000 estimates took {elapsed:.3f}s (target <1s)"

    def test_model_specific_multipliers(self):
        """Test that different models have appropriate multipliers."""
        estimator = LocalTokenEstimator()
        prompt = "Test prompt " * 50

        # All models should give reasonable estimates
        for model in ["claude-sonnet-5", "claude-opus-5", "claude-haiku-4-5-20251001", "gpt-4"]:
            tokens = estimator.estimate(prompt, model)
            assert tokens > 0, f"Model {model} returned 0 tokens"
            assert tokens < 10000, f"Model {model} returned unreasonable token count: {tokens}"

    def test_empty_prompt(self):
        """Test estimation for empty prompt."""
        estimator = LocalTokenEstimator()
        tokens = estimator.estimate("", "claude-sonnet-5")
        assert tokens == 0

    def test_estimate_with_system_prompt(self):
        """Test estimation including system prompt."""
        estimator = LocalTokenEstimator()
        prompt = "User question here"
        system = (
            "You are a helpful assistant with a very long system prompt that contains many instructions and guidelines for how to respond to the user."
            * 5
        )

        tokens = estimator.estimate(prompt, "claude-sonnet-5", system=system)
        # Should include system prompt tokens
        assert tokens > estimator.estimate(prompt, "claude-sonnet-5")

    def test_estimate_with_tools(self):
        """Test estimation including tool definitions."""
        estimator = LocalTokenEstimator()
        prompt = "Use the tool to get data"
        tools = [
            {
                "name": "get_data",
                "description": "Get data from API",
                "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
            },
            {
                "name": "process_data",
                "description": "Process the data",
                "input_schema": {"type": "object", "properties": {"data": {"type": "string"}}},
            },
        ]

        tokens = estimator.estimate(prompt, "claude-sonnet-5", tools=tools)
        assert tokens > estimator.estimate(prompt, "claude-sonnet-5")


class TestTokenCounterIntegration:
    """Tests for integration with existing TokenCounter."""

    def test_token_counter_uses_local_estimator(self):
        """Test that TokenCounter can use local estimator as backend."""
        from zcoder.agent.optimization.tokens import TokenCounter

        # TokenCounter should work without API key for local estimation
        counter = TokenCounter(api_key="", model="claude-sonnet-5")

        # Should have local estimator available
        assert hasattr(counter, "_local_estimator") or hasattr(counter, "estimate_local")

    def test_fallback_to_api_when_needed(self):
        """Test that precise counting still works via API when needed."""
        from zcoder.agent.optimization.tokens import TokenCounter

        # This test would require a real API key, so we just verify the interface exists
        counter = TokenCounter(api_key="test-key", model="claude-sonnet-5")
        assert hasattr(counter, "count")  # Original API method


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
