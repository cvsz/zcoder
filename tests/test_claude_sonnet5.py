"""tests/test_claude_sonnet5.py"""
from datetime import date

import pytest

from claude_sonnet5 import (
    Sonnet5Client,
    current_pricing,
    estimate_cost_usd,
    validate_service_tier,
    PROMO_END_DATE,
    PROMO_PRICE_IN_USD,
    PROMO_PRICE_OUT_USD,
    STANDARD_PRICE_IN_USD,
    STANDARD_PRICE_OUT_USD,
    SONNET5_MODEL_ID,
)


# ── pricing cliff-edge ───────────────────────────────────────────────────

def test_promo_pricing_on_promo_end_date_itself():
    pricing = current_pricing(as_of=PROMO_END_DATE)
    assert pricing["promo_active"] is True
    assert pricing["price_in"] == PROMO_PRICE_IN_USD


def test_standard_pricing_day_after_promo_ends():
    day_after = date(PROMO_END_DATE.year, PROMO_END_DATE.month, PROMO_END_DATE.day) + \
        __import__("datetime").timedelta(days=1)
    pricing = current_pricing(as_of=day_after)
    assert pricing["promo_active"] is False
    assert pricing["price_in"] == STANDARD_PRICE_IN_USD
    assert pricing["price_out"] == STANDARD_PRICE_OUT_USD


def test_promo_pricing_well_before_end_date():
    pricing = current_pricing(as_of=date(2026, 7, 26))
    assert pricing["promo_active"] is True


def test_estimate_cost_usd_uses_promo_rate_when_active():
    cost = estimate_cost_usd(1_000_000, 1_000_000, as_of=date(2026, 7, 26))
    assert cost == pytest.approx(PROMO_PRICE_IN_USD + PROMO_PRICE_OUT_USD)


def test_estimate_cost_usd_applies_geo_multiplier():
    base = estimate_cost_usd(1_000_000, 1_000_000, as_of=date(2026, 7, 26), use_geo=False)
    geo = estimate_cost_usd(1_000_000, 1_000_000, as_of=date(2026, 7, 26), use_geo=True)
    assert geo == pytest.approx(base * 1.1)


# ── service_tier: the one current model that doesn't support it ─────────

def test_service_tier_none_is_fine():
    assert validate_service_tier(None) is None


def test_service_tier_requested_warns_unsupported():
    warning = validate_service_tier("auto")
    assert warning is not None
    assert "not support" in warning.lower()


# ── client wiring ────────────────────────────────────────────────────────

def test_call_sends_model_id_and_geo_flag(monkeypatch):
    client = Sonnet5Client(api_key="k")
    captured = {}

    def fake_post(payload):
        captured.update(payload)
        return {"content": [{"type": "text", "text": "hi"}], "stop_reason": "end_turn"}

    monkeypatch.setattr(client, "_post", fake_post)
    client.call("hello", use_geo=True)

    assert captured["model"] == SONNET5_MODEL_ID
    assert captured["inference_geo"] == "us"


def test_call_attaches_service_tier_warning(monkeypatch):
    client = Sonnet5Client(api_key="k")
    monkeypatch.setattr(client, "_post", lambda payload: {"content": [], "stop_reason": "end_turn"})
    data = client.call("hello", service_tier="auto")
    assert data["_service_tier_warning"] is not None


def test_validate_sampling_params_none_set_is_safe():
    from claude_sonnet5 import validate_sampling_params

    assert validate_sampling_params() is None
    assert validate_sampling_params(None, None, None) is None


def test_validate_sampling_params_temperature_flagged():
    from claude_sonnet5 import validate_sampling_params

    warning = validate_sampling_params(temperature=0.5)
    assert warning is not None
    assert "temperature=0.5" in warning


def test_validate_sampling_params_multiple_flagged():
    from claude_sonnet5 import validate_sampling_params

    warning = validate_sampling_params(temperature=0.5, top_p=0.9, top_k=40)
    assert "temperature=0.5" in warning
    assert "top_p=0.9" in warning
    assert "top_k=40" in warning


def test_call_rejects_non_default_sampling_params_before_request(monkeypatch):
    client = Sonnet5Client(api_key="k")

    def fail_post(payload):
        raise AssertionError("should not send a request when sampling params are set")

    monkeypatch.setattr(client, "_post", fail_post)
    data = client.call("hello", temperature=0.7)
    assert "error" in data
    assert "temperature=0.7" in data["error"]
