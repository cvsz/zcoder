"""tests/unit/test_claude_haiku45.py

Covers ZCoder Max (--haiku45 -> zcoder-max via Ollama).

The module was refactored from Claude Haiku 4.5 (Anthropic API) to ZCoder's own
Max model running locally on Ollama. build_thinking_param, resolve_model_id,
HAIKU45_ALIAS, MIN_THINKING_BUDGET and validate_fast_mode no longer exist;
thinking_budget is accepted for compatibility but ignored by the local model.
"""

from zcoder.agent.models.haiku45 import (
    HAIKU45_EFFORT_BUDGETS,
    HAIKU45_EFFORT_LEVELS,
    HAIKU45_INFO,
    HAIKU45_MODEL_ID,
    Haiku45Client,
    estimate_cost_usd,
    validate_effort_thinking,
    validate_inference_geo,
)

# ── constants ────────────────────────────────────────────────────────────


def test_model_id_is_zcoder_max():
    assert HAIKU45_MODEL_ID == "zcoder-max"


def test_info_has_expected_fields():
    assert HAIKU45_INFO["model_id"] == HAIKU45_MODEL_ID
    assert HAIKU45_INFO["tier"] == "current"
    assert HAIKU45_INFO["fast_mode_supported"] is True
    assert "Max" in HAIKU45_INFO["display_name"]


def test_effort_levels():
    assert HAIKU45_EFFORT_LEVELS == ["low", "medium", "high", "max"]
    assert set(HAIKU45_EFFORT_BUDGETS) == set(HAIKU45_EFFORT_LEVELS)


# ── pricing: free local inference ────────────────────────────────────────


def test_estimate_cost_usd_is_free():
    assert estimate_cost_usd(1_000_000, 1_000_000) == 0.0


# ── validation ───────────────────────────────────────────────────────────


def test_validate_effort_thinking_accepts_all_levels():
    for level in HAIKU45_EFFORT_LEVELS:
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
    client = Haiku45Client(api_key="k")
    captured = {}
    monkeypatch.setattr(client._client, "_post", _make_capturing_post(captured))
    client.call("hello")
    assert captured["model"] == HAIKU45_MODEL_ID


def test_call_maps_effort_to_temperature(monkeypatch):
    client = Haiku45Client(api_key="k")
    captured = {}
    monkeypatch.setattr(client._client, "_post", _make_capturing_post(captured))
    client.call("hello", effort="max")
    assert captured["temperature"] == HAIKU45_EFFORT_BUDGETS["max"]


def test_call_accepts_thinking_budget_ignored(monkeypatch):
    client = Haiku45Client(api_key="k")
    captured = {}
    monkeypatch.setattr(client._client, "_post", _make_capturing_post(captured))
    # thinking_budget is accepted for compatibility but not forwarded to Ollama.
    client.call("hello", thinking_budget=2000)
    assert "thinking" not in captured
    assert captured["model"] == HAIKU45_MODEL_ID
