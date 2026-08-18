"""tests/test_claude_haiku45.py"""

import pytest

from zcoder.claude.models.haiku45 import (
    HAIKU45_ALIAS,
    HAIKU45_MODEL_ID,
    MIN_THINKING_BUDGET,
    Haiku45Client,
    build_thinking_param,
    resolve_model_id,
    validate_fast_mode,
    validate_inference_geo,
)

# ── build_thinking_param: always the extended shape, never adaptive ────


def test_no_budget_means_no_thinking_block():
    assert build_thinking_param(None) is None


def test_budget_produces_enabled_type_not_adaptive():
    param = build_thinking_param(2000)
    assert param == {"type": "enabled", "budget_tokens": 2000}
    assert param["type"] != "adaptive"


def test_budget_below_floor_raises():
    with pytest.raises(ValueError):
        build_thinking_param(MIN_THINKING_BUDGET - 1)


def test_budget_at_floor_is_accepted():
    param = build_thinking_param(MIN_THINKING_BUDGET)
    assert param["budget_tokens"] == MIN_THINKING_BUDGET


# ── alias resolution ─────────────────────────────────────────────────────


def test_alias_resolves_to_dated_id():
    assert resolve_model_id(HAIKU45_ALIAS) == HAIKU45_MODEL_ID


def test_dated_id_passes_through_unchanged():
    assert resolve_model_id(HAIKU45_MODEL_ID) == HAIKU45_MODEL_ID


# ── unsupported-feature guards (Opus-only fast mode, no data residency) ─


def test_fast_mode_rejected_for_haiku45():
    err = validate_fast_mode(True)
    assert err is not None
    assert "opus" in err.lower()


def test_fast_mode_not_requested_is_fine():
    assert validate_fast_mode(False) is None


def test_inference_geo_rejected_for_haiku45():
    err = validate_inference_geo(True)
    assert err is not None


# ── client wiring ────────────────────────────────────────────────────────


def test_call_raises_before_posting_on_unsupported_fast_mode(monkeypatch):
    client = Haiku45Client(api_key="k")
    calls = []
    monkeypatch.setattr(client, "_post", lambda payload: calls.append(payload) or {"content": []})

    with pytest.raises(ValueError):
        client.call("hi", fast=True)

    assert calls == []


def test_call_sends_extended_thinking_block(monkeypatch):
    client = Haiku45Client(api_key="k")
    captured = {}

    def fake_post(payload):
        captured.update(payload)
        return {"content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn"}

    monkeypatch.setattr(client, "_post", fake_post)
    client.call("hi", thinking_budget=2000)

    assert captured["model"] == HAIKU45_MODEL_ID
    assert captured["thinking"] == {"type": "enabled", "budget_tokens": 2000}
    assert captured["max_tokens"] >= 2000 + 1024
