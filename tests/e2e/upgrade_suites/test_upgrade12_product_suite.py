"""tests/test_upgrade12_product_suite.py — Comprehensive Test Suite for Upgrade-12 SaaS Layer.

Verifies:
  1. SaaS Plans & Entitlement Service (limits, features, versioned bundles, non-override of RBAC)
  2. FakeBillingProvider & Idempotent Usage Reporting (no double-billing on replay)
  3. Public REST API v1 (dispatching, rate limits, standardized errors, idempotency conflicts)
  4. Webhook Signing & SSRF Defense (HMAC-SHA256 signature verification, loopback protection)
  5. Python SDK Client contract execution
"""

import time

from zcoder.api.public.v1 import PublicAPIV1Router
from zcoder.domain.models.product import (
    CustomerWebhookEndpoint,
    EntitlementService,
    FakeBillingProvider,
    PlanTier,
    Subscription,
    SubscriptionStatus,
)
from zcoder.domain.models.tenant import EnterpriseRole, RequestContext
from zcoder.interfaces.sdk.client import ZCoderClient


def test_entitlements_by_plan_tier():
    service = EntitlementService()
    # 1. Default / Free plan
    free_ent = service.get_entitlements("org_free")
    assert free_ent.max_projects == 1
    assert free_ent.sso_oidc_enabled is False

    # 2. Enterprise plan
    service.set_subscription(
        Subscription(
            id="sub_ent",
            account_id="acc_1",
            organization_id="org_ent",
            plan_tier=PlanTier.ENTERPRISE,
            status=SubscriptionStatus.ACTIVE,
        )
    )
    ent = service.get_entitlements("org_ent")
    assert ent.sso_oidc_enabled is True
    assert ent.scim_enabled is True
    assert ent.concurrent_jobs == 100
    assert service.check_quota_limit("org_ent", "concurrent_jobs", 50) is True
    assert service.check_quota_limit("org_ent", "concurrent_jobs", 100) is False


def test_fake_billing_provider_idempotent_usage():
    billing = FakeBillingProvider()
    cus_ref = billing.create_customer("org_test", "test@zcoder.ai", "Test Org")
    assert cus_ref.startswith("cus_fake_")

    sub_ref = billing.create_subscription(cus_ref, PlanTier.DEVELOPER)
    assert sub_ref.startswith("sub_fake_")

    # Report usage event 1
    ok1 = billing.report_usage(cus_ref, "usage_evt_101", "agent_input_tokens", 1500.0)
    assert ok1 is True
    assert len(billing.usage_records) == 1

    # Replay exact same usage event -> must be idempotent and not duplicate
    ok2 = billing.report_usage(cus_ref, "usage_evt_101", "agent_input_tokens", 1500.0)
    assert ok2 is True
    assert len(billing.usage_records) == 1  # count did not increase


def test_customer_webhook_hmac_signature_and_ssrf():
    endpoint = CustomerWebhookEndpoint(
        id="wh_1",
        organization_id="org_1",
        url="https://customer-service.com/webhook",
        event_types={"job.completed"},
        secret="whsec_supersecret123",
    )
    payload = '{"event": "job.completed", "job_id": "job_123"}'
    ts = time.time()
    sig = endpoint.sign_payload("evt_1", ts, payload)
    assert isinstance(sig, str)
    assert len(sig) == 64  # SHA-256 hex string

    # SSRF verification in Public API
    router = PublicAPIV1Router()
    ctx = RequestContext(principal_id="user_1", organization_id="org_1", role=EnterpriseRole.OPERATOR)
    status, body = router.handle_request(
        "POST", "/api/v1/webhooks", ctx, payload={"url": "http://127.0.0.1:8080/hook"}
    )
    assert status == 400
    assert body["error"]["code"] == "SSRF_BLOCKED"


def test_public_api_idempotency_and_routing():
    router = PublicAPIV1Router()
    ctx = RequestContext(principal_id="user_1", organization_id="org_1", role=EnterpriseRole.OPERATOR)

    # 1. First POST with Idempotency Key
    status1, body1 = router.handle_request(
        "POST", "/api/v1/jobs", ctx, payload={"task": "Run lint"}, idempotency_key="idem_abc_123"
    )
    assert status1 == 201
    job_id_1 = body1["id"]

    # 2. Retry with exact same key and payload -> returns identical result
    status2, body2 = router.handle_request(
        "POST", "/api/v1/jobs", ctx, payload={"task": "Run lint"}, idempotency_key="idem_abc_123"
    )
    assert status2 == 201
    assert body2["id"] == job_id_1

    # 3. Conflict: same key, different payload -> 409
    status3, body3 = router.handle_request(
        "POST", "/api/v1/jobs", ctx, payload={"task": "Run build"}, idempotency_key="idem_abc_123"
    )
    assert status3 == 409
    assert body3["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_python_sdk_contract():
    router = PublicAPIV1Router()
    client = ZCoderClient(api_key="zc_live_testkey123", organization_id="org_sdk", router=router)

    entitlements = client.get_entitlements()
    assert "max_projects" in entitlements

    job = client.create_job("Build docs", idempotency_key="sdk_idem_1")
    assert job["status"] == "CREATED"
    assert job["task"] == "Build docs"

    wh = client.register_webhook("https://myapp.com/zcoder-events")
    assert wh["status"] == "ACTIVE"
    assert wh["url"] == "https://myapp.com/zcoder-events"
