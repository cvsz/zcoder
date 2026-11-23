"""tests/unit/test_claude_fable5.py

Covers ZCoder Flash (--fable5 -> zcoder-flash via Ollama).

The module was refactored from Claude Fable 5 (Anthropic API) to ZCoder's own
Flash model running locally on Ollama. The old server-side / client-side
fallback retry paths and RefusalError no longer exist; parse_fallback_chain is
kept as a compatibility shim that accepts input and returns a neutral result.
"""

from zcoder.agent.models.fable5 import (
    FABLE5_EFFORT_BUDGETS,
    FABLE5_EFFORT_LEVELS,
    FABLE5_INFO,
    FABLE5_MODEL_ID,
    Fable5Client,
    estimate_cost_usd,
    parse_fallback_chain,
    validate_effort_thinking,
    validate_inference_geo,
)

# ── constants ────────────────────────────────────────────────────────────


def test_model_id_is_zcoder_flash():
    assert FABLE5_MODEL_ID == "zcoder-flash"


def test_info_has_expected_fields():
    assert FABLE5_INFO["model_id"] == FABLE5_MODEL_ID
    assert FABLE5_INFO["tier"] == "current"
    assert FABLE5_INFO["fast_mode_supported"] is True
    assert "Flash" in FABLE5_INFO["display_name"]


def test_effort_levels():
    assert FABLE5_EFFORT_LEVELS == ["low", "medium", "high", "max"]
    assert set(FABLE5_EFFORT_BUDGETS) == set(FABLE5_EFFORT_LEVELS)


# ── pricing: free local inference ────────────────────────────────────────


def test_estimate_cost_usd_is_free():
    assert estimate_cost_usd(1_000_000, 1_000_000) == 0.0


# ── parse_fallback_chain (compatibility shim) ────────────────────────────


def test_parse_fallback_chain_splits_and_strips():
    assert parse_fallback_chain(" claude-opus-4-8 , claude-sonnet-5 ") == [
        "claude-opus-4-8",
        "claude-sonnet-5",
    ]


def test_parse_fallback_chain_none_when_empty():
    assert parse_fallback_chain(None) is None
    assert parse_fallback_chain("") is None


def test_parse_fallback_chain_recognizes_default_case_insensitively():
    assert parse_fallback_chain("default") == ["default"]
    assert parse_fallback_chain("Default") == ["Default"]
    assert parse_fallback_chain("DEFAULT") == ["DEFAULT"]


# ── validation ───────────────────────────────────────────────────────────


def test_validate_effort_thinking_accepts_all_levels():
    for level in FABLE5_EFFORT_LEVELS:
        assert validate_effort_thinking(level, False) is None


def test_validate_inference_geo_not_applicable():
    assert validate_inference_geo(True) is None
    assert validate_inference_geo(False) is None


# ── client wiring ────────────────────────────────────────────────────────


def _make_capturing_post(captured, text="ok"):
    def fake(payload):
        captured.update(payload)
        return {"content": [{"type": "text", "text": text}], "stop_reason": "end_turn"}

    return fake


def test_call_sends_model_id(monkeypatch):
    client = Fable5Client(api_key="k")
    captured = {}
    monkeypatch.setattr(client._client, "_post", _make_capturing_post(captured))
    client.call("hello")
    assert captured["model"] == FABLE5_MODEL_ID


def test_call_maps_effort_to_temperature(monkeypatch):
    client = Fable5Client(api_key="k")
    captured = {}
    monkeypatch.setattr(client._client, "_post", _make_capturing_post(captured))
    client.call("hello", effort="max")
    assert captured["temperature"] == FABLE5_EFFORT_BUDGETS["max"]
