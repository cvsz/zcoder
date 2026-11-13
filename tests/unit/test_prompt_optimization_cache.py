"""tests/unit/test_prompt_optimization_cache.py — Tests for prompt optimization caching."""

from __future__ import annotations

import pytest

from zcoder.agent.optimization.prompt import clear_optimize_cache, get_optimize_cache_stats, optimize


class MockClient:
    """Mock client that tracks call count."""

    def __init__(self):
        self.call_count = 0
        self.model = "test-model"
        self.max_tokens = 2048

    def generate(self, user: str, system: str = "") -> str:
        self.call_count += 1
        return f"Optimized: {user[:50]}"


class TestPromptOptimizationCache:
    """Tests for LRU caching in prompt optimization."""

    def setup_method(self):
        """Clear cache before each test."""
        clear_optimize_cache()

    def test_optimize_cache_hit(self):
        """Test that repeated optimization of same prompt hits cache."""
        client = MockClient()
        prompt = "Write a function to sort a list"

        # First call - cache miss
        result1 = optimize(prompt, client, "test-model")
        assert client.call_count == 1

        # Second call - cache hit
        result2 = optimize(prompt, client, "test-model")
        assert client.call_count == 1  # No additional call
        assert result1 == result2

    def test_optimize_different_prompts_cache_miss(self):
        """Test that different prompts cause cache misses."""
        client = MockClient()

        optimize("Prompt A", client, "test-model")
        assert client.call_count == 1

        optimize("Prompt B", client, "test-model")
        assert client.call_count == 2

    def test_optimize_different_models_cache_miss(self):
        """Test that same prompt with different models causes cache miss."""
        client = MockClient()

        optimize("Test prompt", client, "model-a")
        assert client.call_count == 1

        optimize("Test prompt", client, "model-b")
        assert client.call_count == 2

    def test_cache_stats(self):
        """Test that cache stats are available."""
        client = MockClient()

        # Initial stats
        stats = get_optimize_cache_stats()
        assert "hits" in stats
        assert "misses" in stats
        assert "size" in stats
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["size"] == 0

        # After one call
        optimize("Test prompt", client, "test-model")
        stats = get_optimize_cache_stats()
        assert stats["misses"] == 1
        assert stats["size"] == 1

        # After cache hit
        optimize("Test prompt", client, "test-model")
        stats = get_optimize_cache_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["size"] == 1

    def test_cache_eviction(self):
        """Test that cache evicts old entries when full."""
        client = MockClient()

        # Fill cache beyond maxsize (default 128)
        for i in range(150):
            optimize(f"Prompt {i}", client, "test-model")

        stats = get_optimize_cache_stats()
        assert stats["size"] <= 128
        assert client.call_count == 150  # All were cache misses

    def test_clear_cache(self):
        """Test that cache can be cleared."""
        client = MockClient()

        optimize("Test prompt", client, "test-model")
        assert get_optimize_cache_stats()["size"] == 1

        clear_optimize_cache()
        assert get_optimize_cache_stats()["size"] == 0

    def test_offline_optimization_not_cached(self):
        """Test that offline (no client) optimization is not cached."""
        # When no client provided, uses rule-based optimization
        prompt = "Write a function to sort a list"

        result1 = optimize(prompt, None, "test-model")
        result2 = optimize(prompt, None, "test-model")

        # Both should return same result but not use cache
        assert result1 == result2
        # Cache should still be empty
        assert get_optimize_cache_stats()["size"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
