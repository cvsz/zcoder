"""tests/unit/test_cost_routing_enhancement.py — Tests for enhanced cost-aware model routing."""

from __future__ import annotations

import pytest

from zcoder.agent.optimization.cost import classify_complexity, select_model


class TestComplexityClassification:
    """Tests for enhanced complexity classification."""

    def test_complexity_classification_code_heavy(self):
        """Code-heavy prompts should route to higher tier."""
        code_prompt = (
            "def fibonacci(n):\n" "    if n <= 1: return n\n" "    return fibonacci(n-1) + fibonacci(n-2)\n"
        ) * 10
        assert classify_complexity(code_prompt) == "high"

    def test_complexity_classification_simple(self):
        """Simple prompts should route to low tier."""
        simple_prompt = "What is 2+2?"
        assert classify_complexity(simple_prompt) == "low"

    def test_complexity_classification_medium(self):
        """Medium complexity prompts should route to medium tier."""
        medium_prompt = "Write a Python function that reads a CSV file and returns the average of a column"
        assert classify_complexity(medium_prompt) == "medium"

    def test_complexity_classification_sql_heavy(self):
        """SQL-heavy prompts should route to higher tier."""
        sql_prompt = (
            "CREATE TABLE users (id INT PRIMARY KEY, name VARCHAR(100)); SELECT * FROM users WHERE age > 18;"
        )
        assert classify_complexity(sql_prompt) in ("medium", "high")

    def test_complexity_classification_very_long(self):
        """Very long prompts should route to high tier."""
        long_prompt = "Explain the concept of machine learning " * 200  # ~800 words
        assert classify_complexity(long_prompt) == "high"

    def test_complexity_classification_nested_code(self):
        """Nested code structures should increase complexity."""
        nested_prompt = (
            "async def process_data(items):\n"
            "    results = []\n"
            "    for item in items:\n"
            "        if item.valid:\n"
            "            try:\n"
            "                result = await transform(item)\n"
            "                results.append(result)\n"
            "            except Exception:\n"
            "                pass\n"
            "    return results\n"
        )
        assert classify_complexity(nested_prompt) in ("medium", "high")


class TestModelSelection:
    """Tests for model selection with latency awareness."""

    def test_latency_aware_routing(self):
        """When latency critical, prefer faster model even for medium complexity."""
        model = select_model("medium", force=None, prefer_latency=True)
        assert model == "claude-haiku-4-5-20251001"

    def test_latency_aware_routing_high_complexity(self):
        """Even for high complexity, latency preference selects faster model."""
        model = select_model("high", force=None, prefer_latency=True)
        assert model == "claude-haiku-4-5-20251001"

    def test_force_model_override(self):
        """Force parameter should override complexity classification."""
        model = select_model("low", force="claude-opus-5")
        assert model == "claude-opus-5"

    def test_default_routing_low(self):
        """Low complexity should route to Haiku by default."""
        model = select_model("low")
        assert model == "claude-haiku-4-5-20251001"

    def test_default_routing_medium(self):
        """Medium complexity should route to Sonnet by default."""
        model = select_model("medium")
        assert model == "claude-sonnet-5"

    def test_default_routing_high(self):
        """High complexity should route to Opus by default."""
        model = select_model("high")
        assert model == "claude-opus-5"


class TestCostRoutingAccuracy:
    """Tests for end-to-end cost routing accuracy."""

    def test_cost_routing_test_cases(self):
        """Test cases covering various prompt types and expected routing."""
        test_cases = [
            # (prompt, expected_complexity, expected_model)
            ("What is 2+2?", "low", "claude-haiku-4-5-20251001"),
            ("Write a Python class with methods for a user model", "medium", "claude-sonnet-5"),
            (
                "Refactor this 500-line legacy module with comprehensive tests and documentation",
                "high",
                "claude-opus-5",
            ),
            ("SELECT * FROM users WHERE active = true", "medium", "claude-sonnet-5"),
            ("def hello():\n    print('world')", "low", "claude-haiku-4-5-20251001"),
        ]

        for prompt, expected_complexity, expected_model in test_cases:
            complexity = classify_complexity(prompt)
            model = select_model(complexity)
            assert (
                complexity == expected_complexity
            ), f"Prompt: {prompt[:50]}... Expected {expected_complexity}, got {complexity}"
            assert model == expected_model, f"Prompt: {prompt[:50]}... Expected {expected_model}, got {model}"

    def test_code_marker_detection(self):
        """Test that code markers are properly detected."""
        # Python code markers - minimal stubs are low complexity
        assert classify_complexity("def func(): pass") == "low"
        assert classify_complexity("class MyClass: pass") == "low"

        # But code with more substance is medium
        assert classify_complexity("def func():\n    return 42") in ("medium", "high")
        assert classify_complexity("class MyClass:\n    def method(self):\n        return 1") in (
            "medium",
            "high",
        )
        assert classify_complexity("async def handler(): await foo()") in ("medium", "high")

        # SQL markers
        assert classify_complexity("SELECT * FROM table") in ("medium", "high")
        assert classify_complexity("CREATE INDEX idx ON table(col)") in ("medium", "high")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
