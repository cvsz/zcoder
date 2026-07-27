"""tests/test_claude_opus5.py"""
import pytest

from claude_opus5 import (
    Opus5Client,
    validate_effort_thinking,
    validate_inference_geo,
    OPUS5_MODEL_ID,
    OPUS5_EFFORT_LEVELS,
    estimate_cost_usd,
)


# ── validate_effort_thinking: the breaking-change guard ─────────────────

def test_thinking_enabled_any_effort_is_always_fine():
    for effort in OPUS5_EFFORT_LEVELS:
        assert validate_effort_thinking(effort, disable_thinking=False) is None
    assert validate_effort_thinking(None, disable_thinking=False) is None


@pytest.mark.parametrize("effort", ["low", "medium", "high"])
def test_thinking_disabled_allowed_at_high_or_below(effort):
    assert validate_effort_thinking(effort, disable_thinking=True) is None


@pytest.mark.parametrize("effort", ["xhigh", "max"])
def test_thinking_disabled_rejected_above_high(effort):
    err = validate_effort_thinking(effort, disable_thinking=True)
    assert err is not None
    assert "400" in err or "reject" in err.lower()


def test_thinking_disabled_no_effort_given_is_not_rejected():
    # Conservative: we don't know the API's default resolution, so this
    # module doesn't invent a rejection for a case it can't confirm.
    assert validate_effort_thinking(None, disable_thinking=True) is None


def test_unknown_effort_level_is_rejected():
    err = validate_effort_thinking("ultra", disable_thinking=True)
    assert err is not None
    assert "ultra" in err


# ── validate_inference_geo: unconfirmed, not blocked or silently allowed ─

def test_inference_geo_not_requested_is_fine():
    assert validate_inference_geo(False) is None


def test_inference_geo_requested_warns_unconfirmed():
    warning = validate_inference_geo(True)
    assert warning is not None
    assert "unconfirmed" in warning.lower()


# ── Opus5Client.call: client-side validation happens before any HTTP call ─

def test_call_raises_before_posting_on_bad_combination(monkeypatch):
    client = Opus5Client(api_key="k")
    calls = []
    monkeypatch.setattr(client, "_post", lambda payload: calls.append(payload) or {"content": []})

    with pytest.raises(ValueError):
        client.call("hi", effort="xhigh", disable_thinking=True)

    assert calls == []  # never reached the network layer


def test_call_sends_expected_payload_shape(monkeypatch):
    client = Opus5Client(api_key="k")
    captured = {}

    def fake_post(payload):
        captured.update(payload)
        return {"content": [{"type": "text", "text": "hello"}], "stop_reason": "end_turn"}

    monkeypatch.setattr(client, "_post", fake_post)
    data = client.call("hi", effort="high", fast=True)

    assert captured["model"] == OPUS5_MODEL_ID
    assert captured["effort"] == "high"
    assert captured["speed"] == "fast"
    assert "thinking" not in captured  # not disabled -> no thinking key sent
    assert data["content"][0]["text"] == "hello"


def test_call_geo_warning_attached_but_not_blocking(monkeypatch):
    client = Opus5Client(api_key="k")
    monkeypatch.setattr(client, "_post", lambda payload: {"content": [], "stop_reason": "end_turn"})
    data = client.call("hi", use_geo=True)
    assert data["_geo_warning"] is not None
    assert data.get("error") is None


def test_estimate_cost_usd():
    cost = estimate_cost_usd(1_000_000, 1_000_000)
    assert cost == pytest.approx(5.0 + 25.0)
