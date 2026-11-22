"""tests/unit/test_claude_sonnet5.py

Covers ZCoder ProMax (--sonnet5 -> zcoder-promax via Ollama).

The module was refactored from Claude Sonnet 5 (Anthropic API) to ZCoder's own
ProMax model running locally on Ollama, so there is no pricing, service tier,
inference geo, or sampling-parameter validation — all of those are compatibility
shims that accept input and return a neutral result.
"""

import pytest

from zcoder.agent.models.sonnet5 import (
    SONNET5_EFFORT_BUDGETS,
    SONNET5_EFFORT_LEVELS,
    SONNET5_INFO,
    SONNET5_MODEL_ID,
    Sonnet5Client,
    estimate_cost_usd,
    validate_effort_thinking,
    validate_inference_geo,
)

# ── constants ────────────────────────────────────────────────────────────


def test_model_id_is_zcoder_promax():
    assert SONNET5_MODEL_ID == "zcoder-promax"


def test_info_has_expected_fields():
    assert SONNET5_INFO["model_id"] == SONNET5_MODEL_ID
    assert SONNET5_INFO["tier"] == "current"
    assert SONNET5_INFO["fast_mode_supported"] is True
    assert "ProMax" in SONNET5_INFO["display_name"]


def test_effort_levels():
    assert SONNET5_EFFORT_LEVELS == ["low", "medium", "high", "max"]
    assert set(SONNET5_EFFORT_BUDGETS) == set(SONNET5_EFFORT_LEVELS)


# ── pricing: ZCoder models are free (local inference) ────────────────────


def test_estimate_cost_usd_is_free():
    assert estimate_cost_usd(1_000_000, 1_000_000) == 0.0
    assert estimate_cost_usd(0, 0) == 0.0


# ── validation ───────────────────────────────────────────────────────────


def test_validate_effort_thinking_accepts_all_levels():
    for level in SONNET5_EFFORT_LEVELS:
        assert validate_effort_thinking(level, False) is None
    assert validate_effort_thinking(None, False) is None


def test_validate_effort_thinking_rejects_unknown_level():
    err = validate_effort_thinking("bogus", False)
    assert err is not None
    assert "bogus" in err


def test_validate_inference_geo_not_applicable():
    # Local Ollama models have no data-residency concept.
    assert validate_inference_geo(True) is None
    assert validate_inference_geo(False) is None


# ── client wiring ────────────────────────────────────────────────────────


def _make_capturing_post(captured, text="ok"):
    def fake(payload):
        captured.update(payload)
        # Ollama chat response shape: {"message": {"role": "assistant", "content": "..."}}
        return {
            "message": {"role": "assistant", "content": text},
            "stop_reason": "end_turn",
        }

    return fake


def test_call_sends_model_id(monkeypatch):
    client = Sonnet5Client(api_key="k")
    captured = {}
    monkeypatch.setattr(client._client, "_post", _make_capturing_post(captured))
    client.call("hello")
    assert captured["model"] == SONNET5_MODEL_ID


def test_call_maps_effort_to_temperature(monkeypatch):
    client = Sonnet5Client(api_key="k")
    captured = {}
    monkeypatch.setattr(client._client, "_post", _make_capturing_post(captured))
    client.call("hello", effort="max")
    assert captured["temperature"] == SONNET5_EFFORT_BUDGETS["max"]


def test_call_fast_lowers_temperature(monkeypatch):
    client = Sonnet5Client(api_key="k")
    captured = {}
    monkeypatch.setattr(client._client, "_post", _make_capturing_post(captured))
    client.call("hello", effort="max", fast=True)
    assert captured["temperature"] == min(SONNET5_EFFORT_BUDGETS["max"], 0.3)


def test_call_rejects_unknown_effort(monkeypatch):
    client = Sonnet5Client(api_key="k")
    captured = {}
    monkeypatch.setattr(client._client, "_post", _make_capturing_post(captured))
    with pytest.raises(ValueError):
        client.call("hello", effort="bogus")


def test_call_text_returns_text(monkeypatch):
    client = Sonnet5Client(api_key="k")
    captured = {}
    monkeypatch.setattr(client._client, "_post", _make_capturing_post(captured, "hello world"))
    assert client.call_text("hi") == "hello world"
