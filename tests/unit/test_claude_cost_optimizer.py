"""tests/test_claude_cost_optimizer.py"""

import pytest

from claude_cost_optimizer import (
    INFERENCE_GEO_MULTIPLIER,
    INFERENCE_GEO_SUPPORTED,
    PRICE,
    TIER_MODELS,
    estimate_cost,
)


def test_price_table_contains_current_generation():
    assert "claude-opus-5" in PRICE
    assert "claude-sonnet-5" in PRICE
    assert "claude-haiku-4-5-20251001" in PRICE
    assert "claude-fable-5" in PRICE
    assert "claude-mythos-5" in PRICE
    assert PRICE["claude-opus-5"] == {"in": 5.0, "out": 25.0}


def test_tier_models_includes_opus5():
    assert "claude-opus-5" in TIER_MODELS


def test_inference_geo_supported_models():
    assert "claude-opus-5" in INFERENCE_GEO_SUPPORTED
    assert "claude-sonnet-5" in INFERENCE_GEO_SUPPORTED
    assert "claude-fable-5" in INFERENCE_GEO_SUPPORTED
    assert "claude-mythos-5" in INFERENCE_GEO_SUPPORTED


def test_estimate_cost_standard():
    cost = estimate_cost("claude-opus-5", 1_000_000, 1_000_000)
    assert cost == pytest.approx(5.0 + 25.0)


def test_estimate_cost_inference_geo_us():
    cost_global = estimate_cost("claude-opus-5", 1_000_000, 1_000_000, inference_geo="global")
    cost_us = estimate_cost("claude-opus-5", 1_000_000, 1_000_000, inference_geo="us")
    assert cost_us == pytest.approx(cost_global * INFERENCE_GEO_MULTIPLIER)
