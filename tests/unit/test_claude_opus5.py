"""tests/unit/test_claude_opus5.py

Covers ZCoder Pro (--opus5 -> zcoder-pro via Ollama).

Refactored from Claude Opus 5 (Anthropic API) to ZCoder's own Pro model running
locally on Ollama, matching local inference architecture and zero-cost policy.
"""

import pytest

from zcoder.agent.models.opus5 import (
    OPUS5_EFFORT_BUDGETS,
    OPUS5_EFFORT_LEVELS,
    OPUS5_INFO,
    OPUS5_MODEL_ID,
    Opus5Client,
    estimate_cost_usd,
    validate_effort_thinking,
    validate_inference_geo,
)

# ── constants ────────────────────────────────────────────────────────────


def test_model_id_is_zcoder_pro():
    assert OPUS5_MODEL_ID == "zcoder-pro"


def test_info_has_expected_fields():
    assert OPUS5_INFO["model_id"] == OPUS5_MODEL_ID
    assert OPUS5_INFO["tier"] == "current"
    assert OPUS5_INFO["fast_mode_supported"] is True
    assert "ZCoder Pro" in OPUS5_INFO["display_name"]


def test_effort_levels():
    assert OPUS5_EFFORT_LEVELS == ["low", "medium", "high", "max"]
    assert set(OPUS5_EFFORT_BUDGETS) == set(OPUS5_EFFORT_LEVELS)


# ── pricing: ZCoder models are free (local inference) ────────────────────


def test_estimate_cost_usd_is_free():
    assert estimate_cost_usd(1_000_000, 1_000_000) == 0.0
    assert estimate_cost_usd(0, 0) == 0.0


# ── validation ───────────────────────────────────────────────────────────


def test_validate_effort_thinking_accepts_all_levels():
    for level in OPUS5_EFFORT_LEVELS:
        assert validate_effort_thinking(level, False) is None
        assert validate_effort_thinking(level, True) is None
    assert validate_effort_thinking(None, False) is None
    assert validate_effort_thinking(None, True) is None


def test_validate_effort_thinking_rejects_unknown_level():
    err = validate_effort_thinking("bogus", False)
    assert err is not None
    assert "bogus" in err


def test_validate_inference_geo_not_applicable():
    assert validate_inference_geo(True) is None
    assert validate_inference_geo(False) is None


# ── client wiring ────────────────────────────────────────────────────────


def _make_capturing_post(captured, text="ok"):
    def fake(payload):
        captured.update(payload)
        return {
            "message": {"role": "assistant", "content": text},
            "stop_reason": "end_turn",
        }

    return fake


def test_call_sends_model_id(monkeypatch):
    client = Opus5Client(api_key="k")
    captured = {}
    monkeypatch.setattr(client._client, "_post", _make_capturing_post(captured))
    client.call("hello")
    assert captured["model"] == OPUS5_MODEL_ID


def test_call_maps_effort_to_temperature(monkeypatch):
    client = Opus5Client(api_key="k")
    captured = {}
    monkeypatch.setattr(client._client, "_post", _make_capturing_post(captured))
    client.call("hello", effort="max")
    assert captured["temperature"] == OPUS5_EFFORT_BUDGETS["max"]


def test_call_fast_lowers_temperature(monkeypatch):
    client = Opus5Client(api_key="k")
    captured = {}
    monkeypatch.setattr(client._client, "_post", _make_capturing_post(captured))
    client.call("hello", effort="max", fast=True)
    assert captured["temperature"] == min(OPUS5_EFFORT_BUDGETS["max"], 0.3)


def test_call_rejects_unknown_effort(monkeypatch):
    client = Opus5Client(api_key="k")
    captured = {}
    monkeypatch.setattr(client._client, "_post", _make_capturing_post(captured))
    with pytest.raises(ValueError):
        client.call("hello", effort="bogus")


def test_call_text_returns_text(monkeypatch):
    client = Opus5Client(api_key="k")
    captured = {}
    monkeypatch.setattr(client._client, "_post", _make_capturing_post(captured, "hello from opus"))
    assert client.call_text("hi") == "hello from opus"
