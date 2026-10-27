"""Stripe adapter tests use a mocked transport and never contact Stripe."""

from __future__ import annotations

import hashlib
import hmac
import time
import urllib.parse

import pytest

from zcoder.domain.models import product
from zcoder.domain.models.product import (
    BillingConfigurationError,
    BillingProviderError,
    PlanTier,
    StripeBillingProvider,
)


def _provider(**kwargs) -> StripeBillingProvider:
    return StripeBillingProvider(
        "sk_test_not_sent",
        price_ids={PlanTier.DEVELOPER: "price_dev"},
        meter_event_names={"agent_input_tokens": "agent_input_tokens"},
        **kwargs,
    )


def test_missing_api_key_fails_without_request(monkeypatch):
    called = []
    monkeypatch.setattr(product, "urlopen_json", lambda *args, **kwargs: called.append(args))
    provider = StripeBillingProvider()

    with pytest.raises(BillingConfigurationError, match="STRIPE_SECRET_KEY"):
        provider.create_customer("org_1", "person@example.test", "Example")

    assert called == []


def test_create_customer_returns_only_id_from_stripe_and_uses_idempotency(monkeypatch):
    requests = []

    def fake_request(request, timeout):
        requests.append((request, timeout))
        return {"object": "customer", "id": "cus_real_123"}

    monkeypatch.setattr(product, "urlopen_json", fake_request)
    provider = _provider()

    result = provider.create_customer("org_1", "person@example.test", "Example")

    assert result == "cus_real_123"
    request, timeout = requests[0]
    assert request.full_url == "https://api.stripe.com/v1/customers"
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == "Bearer sk_test_not_sent"
    assert request.get_header("Idempotency-key").startswith("zcoder-customer-")
    assert urllib.parse.parse_qs(request.data.decode()) == {
        "email": ["person@example.test"],
        "name": ["Example"],
        "metadata[organization_id]": ["org_1"],
    }
    assert timeout == 20


def test_create_customer_rejects_fabricated_or_malformed_response(monkeypatch):
    monkeypatch.setattr(product, "urlopen_json", lambda *args, **kwargs: {"id": "cus_fake_123"})
    provider = _provider()

    with pytest.raises(BillingProviderError, match="valid customer ID"):
        provider.create_customer("org_1", "person@example.test", "Example")


def test_subscription_requires_price_configuration_and_uses_returned_id(monkeypatch):
    called = []
    monkeypatch.setattr(product, "urlopen_json", lambda *args, **kwargs: called.append(args))
    provider = StripeBillingProvider("sk_test_not_sent")

    with pytest.raises(BillingConfigurationError, match="Price ID"):
        provider.create_subscription("cus_real_123", PlanTier.DEVELOPER)
    assert called == []

    monkeypatch.setattr(
        product,
        "urlopen_json",
        lambda request, timeout: {"object": "subscription", "id": "sub_real_456"},
    )
    assert _provider().create_subscription("cus_real_123", PlanTier.DEVELOPER) == "sub_real_456"


def test_usage_requires_config_and_reports_only_provider_acknowledgement(monkeypatch):
    provider = _provider()
    calls = []

    def fake_request(request, timeout):
        calls.append(request)
        return {"object": "billing.meter_event", "id": "obj_meter_1"}

    monkeypatch.setattr(product, "urlopen_json", fake_request)
    assert provider.report_usage("cus_real_123", "event_1", "agent_input_tokens", 10) is True
    data = urllib.parse.parse_qs(calls[0].data.decode())
    assert data["identifier"] == ["event_1"]
    assert data["event_name"] == ["agent_input_tokens"]
    assert data["payload[stripe_customer_id]"] == ["cus_real_123"]

    provider.report_usage("cus_real_123", "event_1b", "agent_input_tokens", 10, occurred_at=int(time.time()))
    assert "timestamp" in urllib.parse.parse_qs(calls[1].data.decode())

    monkeypatch.setattr(product, "urlopen_json", lambda *args, **kwargs: {"object": "error"})
    assert provider.report_usage("cus_real_123", "event_2", "agent_input_tokens", 1) is False

    with pytest.raises(BillingConfigurationError, match="meter event"):
        StripeBillingProvider("sk_test_not_sent").report_usage("cus_real_123", "event_3", "unknown_metric", 1)


@pytest.mark.parametrize("quantity", [0, -1, float("nan"), float("inf")])
def test_usage_rejects_invalid_quantities(quantity):
    with pytest.raises(ValueError, match="finite positive"):
        _provider().report_usage("cus_real_123", "event_1", "agent_input_tokens", quantity)


@pytest.mark.parametrize("occurred_at", [True, 1.5, 1, int(time.time()) + 600])
def test_usage_rejects_invalid_or_out_of_window_timestamps(occurred_at):
    with pytest.raises(ValueError, match="occurred_at"):
        _provider().report_usage("cus_real_123", "event_1", "agent_input_tokens", 1, occurred_at=occurred_at)


def test_reconciliation_paginates_and_returns_real_latest_status(monkeypatch):
    pages = iter(
        [
            {
                "data": [{"id": "sub_old", "created": 10, "status": "canceled", "metadata": {}}],
                "has_more": True,
            },
            {
                "data": [
                    {
                        "id": "sub_new",
                        "created": 20,
                        "status": "past_due",
                        "metadata": {"plan_tier": "team"},
                    }
                ],
                "has_more": False,
            },
        ]
    )
    requests = []

    def fake_request(request, timeout):
        requests.append(request.full_url)
        return next(pages)

    monkeypatch.setattr(product, "urlopen_json", fake_request)
    result = _provider().reconcile_subscription("cus_real_123")

    assert result == {
        "id": "sub_new",
        "customer_ref": "cus_real_123",
        "status": "past_due",
        "plan_tier": "team",
        "created": 20,
    }
    assert "starting_after=sub_old" in requests[1]


def test_reconciliation_reports_no_subscription_without_fabricating_active(monkeypatch):
    monkeypatch.setattr(product, "urlopen_json", lambda *args, **kwargs: {"data": [], "has_more": False})

    assert _provider().reconcile_subscription("cus_real_123") == {
        "status": "none",
        "customer_ref": "cus_real_123",
    }


def test_stripe_webhook_signature_checks_timestamp_and_all_v1_values():
    secret = "whsec_test"
    timestamp = int(time.time())
    payload = b'{"id":"evt_1"}'
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256).hexdigest()
    provider = StripeBillingProvider(webhook_secret=secret)

    assert provider.verify_webhook_signature(payload, f"t={timestamp},v1={'0' * 64},v1={digest}")
    assert not provider.verify_webhook_signature(payload, f"t={timestamp - 600},v1={digest}")
    assert not provider.verify_webhook_signature(payload, "t=invalid,v1=bad")
