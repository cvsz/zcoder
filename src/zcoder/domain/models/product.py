"""product_models.py — SaaS Product, Subscription, Plans, Entitlements, and Billing Models.

Separates:
  • Product/Commercial Domain (CustomerAccount, Subscription, Plan, Entitlement, Trial, BillingProfile)
  • Provider-neutral billing interface (BillingProvider, FakeBillingProvider, StripeBillingProvider)
  • EntitlementService (feature gating with versioned bundles; never overrides RBAC)
  • Webhook subscriptions, delivery logging, HMAC-SHA256 signatures, and replay safety
"""

from __future__ import annotations

import dataclasses
import hashlib
import hmac
import math
import re
import time
import urllib.parse
import urllib.request
import uuid
from collections.abc import Mapping
from typing import Any

from zcoder.core.enums import StringEnum
from zcoder.core.resilience import urlopen_json


class AccountStatus(StringEnum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    PAST_DUE = "PAST_DUE"
    SUSPENDED = "SUSPENDED"
    CANCELLED = "CANCELLED"


class SubscriptionStatus(StringEnum):
    TRIALING = "TRIALING"
    ACTIVE = "ACTIVE"
    PAST_DUE = "PAST_DUE"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"
    INCOMPLETE = "INCOMPLETE"


class PlanTier(StringEnum):
    COMMUNITY_FREE = "community_free"
    DEVELOPER = "developer"
    TEAM = "team"
    BUSINESS = "business"
    ENTERPRISE = "enterprise"


@dataclasses.dataclass
class EntitlementBundle:
    version: str = "2026.1"
    max_projects: int = 3
    max_repositories: int = 5
    monthly_budget_usd: float = 50.0
    concurrent_jobs: int = 2
    managed_agents: bool = True
    multiagent_orchestration: bool = False
    scim_enabled: bool = False
    sso_oidc_enabled: bool = False
    audit_export_enabled: bool = False
    retention_days: int = 30
    regional_controls: bool = False
    priority_support: bool = False


PLAN_ENTITLEMENTS: dict[PlanTier, EntitlementBundle] = {
    PlanTier.COMMUNITY_FREE: EntitlementBundle(
        version="2026.1",
        max_projects=1,
        max_repositories=2,
        monthly_budget_usd=10.0,
        concurrent_jobs=1,
        managed_agents=True,
        multiagent_orchestration=False,
        scim_enabled=False,
        sso_oidc_enabled=False,
        audit_export_enabled=False,
        retention_days=7,
        regional_controls=False,
    ),
    PlanTier.DEVELOPER: EntitlementBundle(
        version="2026.1",
        max_projects=5,
        max_repositories=10,
        monthly_budget_usd=100.0,
        concurrent_jobs=3,
        managed_agents=True,
        multiagent_orchestration=True,
        scim_enabled=False,
        sso_oidc_enabled=True,
        audit_export_enabled=True,
        retention_days=30,
        regional_controls=False,
    ),
    PlanTier.TEAM: EntitlementBundle(
        version="2026.1",
        max_projects=20,
        max_repositories=50,
        monthly_budget_usd=500.0,
        concurrent_jobs=10,
        managed_agents=True,
        multiagent_orchestration=True,
        scim_enabled=True,
        sso_oidc_enabled=True,
        audit_export_enabled=True,
        retention_days=90,
        regional_controls=True,
    ),
    PlanTier.BUSINESS: EntitlementBundle(
        version="2026.1",
        max_projects=100,
        max_repositories=250,
        monthly_budget_usd=2500.0,
        concurrent_jobs=25,
        managed_agents=True,
        multiagent_orchestration=True,
        scim_enabled=True,
        sso_oidc_enabled=True,
        audit_export_enabled=True,
        retention_days=180,
        regional_controls=True,
    ),
    PlanTier.ENTERPRISE: EntitlementBundle(
        version="2026.1",
        max_projects=999999,
        max_repositories=999999,
        monthly_budget_usd=50000.0,
        concurrent_jobs=100,
        managed_agents=True,
        multiagent_orchestration=True,
        scim_enabled=True,
        sso_oidc_enabled=True,
        audit_export_enabled=True,
        retention_days=365,
        regional_controls=True,
        priority_support=True,
    ),
}


@dataclasses.dataclass
class CustomerAccount:
    id: str
    organization_id: str
    name: str
    email: str
    status: AccountStatus = AccountStatus.ACTIVE
    created_at: float = dataclasses.field(default_factory=time.time)
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class Subscription:
    id: str
    account_id: str
    organization_id: str
    plan_tier: PlanTier = PlanTier.DEVELOPER
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE
    current_period_start: float = dataclasses.field(default_factory=time.time)
    current_period_end: float = dataclasses.field(default_factory=lambda: time.time() + 86400 * 30)
    provider_subscription_ref: str | None = None
    cancel_at_period_end: bool = False
    trial_ends_at: float | None = None
    entitlement_version: str = "2026.1"


class EntitlementService:
    """Evaluates features and limits strictly based on the organization's subscription plan.

    Note: Entitlements provide capability ceilings; RBAC provides authorization.
    A paid plan never bypasses or overrides RBAC permission requirements.
    """

    def __init__(self, subscriptions: dict[str, Subscription] | None = None):
        self._subscriptions: dict[str, Subscription] = subscriptions or {}

    def set_subscription(self, sub: Subscription) -> None:
        self._subscriptions[sub.organization_id] = sub

    def get_entitlements(self, organization_id: str) -> EntitlementBundle:
        sub = self._subscriptions.get(organization_id)
        if not sub or sub.status in (SubscriptionStatus.CANCELLED, SubscriptionStatus.INCOMPLETE):
            return PLAN_ENTITLEMENTS[PlanTier.COMMUNITY_FREE]
        return PLAN_ENTITLEMENTS.get(sub.plan_tier, PLAN_ENTITLEMENTS[PlanTier.DEVELOPER])

    def check_feature(self, organization_id: str, feature_name: str) -> bool:
        bundle = self.get_entitlements(organization_id)
        return bool(getattr(bundle, feature_name, False))

    def check_quota_limit(self, organization_id: str, metric: str, current_value: float) -> bool:
        bundle = self.get_entitlements(organization_id)
        if metric == "concurrent_jobs":
            return current_value < bundle.concurrent_jobs
        if metric == "monthly_budget_usd":
            return current_value < bundle.monthly_budget_usd
        if metric == "projects":
            return current_value < bundle.max_projects
        if metric == "repositories":
            return current_value < bundle.max_repositories
        return True


# ---------------------------------------------------------------------------
# Provider-Neutral Billing Interface & Adapters
# ---------------------------------------------------------------------------


class BillingProvider:
    """Abstract interface for commercial billing providers (e.g. Stripe, Fake)."""

    def create_customer(self, organization_id: str, email: str, name: str) -> str:
        raise NotImplementedError

    def create_subscription(self, customer_ref: str, plan_tier: PlanTier) -> str:
        raise NotImplementedError

    def report_usage(
        self,
        customer_ref: str,
        meter_event_id: str,
        metric: str,
        quantity: float,
        *,
        occurred_at: int | None = None,
    ) -> bool:
        raise NotImplementedError

    def reconcile_subscription(self, customer_ref: str) -> dict[str, Any]:
        raise NotImplementedError

    def verify_webhook_signature(self, payload: bytes, signature_header: str, secret: str) -> bool:
        raise NotImplementedError


class BillingProviderError(RuntimeError):
    """A billing operation could not be completed or verified."""


class BillingConfigurationError(BillingProviderError):
    """Required provider configuration is missing or invalid."""


class FakeBillingProvider(BillingProvider):
    """Deterministic, in-memory billing provider for offline CI, local dev, and testing."""

    def __init__(self):
        self.customers: dict[str, dict[str, Any]] = {}
        self.subscriptions: dict[str, dict[str, Any]] = {}
        self.usage_records: dict[str, dict[str, Any]] = {}

    def create_customer(self, organization_id: str, email: str, name: str) -> str:
        ref = f"cus_fake_{uuid.uuid4().hex[:12]}"
        self.customers[ref] = {
            "ref": ref,
            "organization_id": organization_id,
            "email": email,
            "name": name,
            "created_at": time.time(),
        }
        return ref

    def create_subscription(self, customer_ref: str, plan_tier: PlanTier) -> str:
        sub_ref = f"sub_fake_{uuid.uuid4().hex[:12]}"
        self.subscriptions[sub_ref] = {
            "sub_ref": sub_ref,
            "customer_ref": customer_ref,
            "plan_tier": plan_tier.value,
            "status": "active",
            "created_at": time.time(),
        }
        return sub_ref

    def report_usage(
        self,
        customer_ref: str,
        meter_event_id: str,
        metric: str,
        quantity: float,
        *,
        occurred_at: int | None = None,
    ) -> bool:
        # Idempotency: exact same meter_event_id must not double count
        if meter_event_id in self.usage_records:
            return True
        self.usage_records[meter_event_id] = {
            "customer_ref": customer_ref,
            "metric": metric,
            "quantity": quantity,
            "timestamp": occurred_at if occurred_at is not None else time.time(),
        }
        return True

    def reconcile_subscription(self, customer_ref: str) -> dict[str, Any]:
        for sub in self.subscriptions.values():
            if sub["customer_ref"] == customer_ref:
                return sub
        return {"status": "none", "customer_ref": customer_ref}

    def verify_webhook_signature(self, payload: bytes, signature_header: str, secret: str) -> bool:
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature_header)


class StripeBillingProvider(BillingProvider):
    """Stripe Billing adapter. It never fabricates provider IDs or success."""

    API_BASE_URL = "https://api.stripe.com/v1"
    WEBHOOK_TOLERANCE_SECONDS = 300

    def __init__(
        self,
        api_key: str = "",
        webhook_secret: str = "",
        *,
        price_ids: Mapping[PlanTier, str] | None = None,
        meter_event_names: Mapping[str, str] | None = None,
        webhook_tolerance_seconds: int = WEBHOOK_TOLERANCE_SECONDS,
    ) -> None:
        self.api_key = api_key.strip()
        self.webhook_secret = webhook_secret
        self.price_ids = dict(price_ids or {})
        self.meter_event_names = dict(meter_event_names or {})
        if webhook_tolerance_seconds <= 0:
            raise ValueError("webhook_tolerance_seconds must be positive")
        self.webhook_tolerance_seconds = webhook_tolerance_seconds

    def _request(
        self,
        method: str,
        path: str,
        params: Mapping[str, str] | None = None,
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if not self.api_key:
            raise BillingConfigurationError("STRIPE_SECRET_KEY is required for Stripe billing operations")
        if not path.startswith("/") or ".." in path.split("/"):
            raise ValueError("Stripe API path must be an absolute API path")
        encoded = urllib.parse.urlencode(params or {}).encode("utf-8")
        url = f"{self.API_BASE_URL}{path}"
        data: bytes | None = None
        if method == "GET":
            if encoded:
                url = f"{url}?{encoded.decode('ascii')}"
        elif method == "POST":
            data = encoded
        else:
            raise ValueError("Unsupported Stripe HTTP method")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "User-Agent": "ZCoder-Billing/1.0",
        }
        if data is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        if idempotency_key:
            if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,255}", idempotency_key):
                raise ValueError("idempotency_key must be 1 to 255 safe ASCII characters")
            headers["Idempotency-Key"] = idempotency_key
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        response = urlopen_json(request, timeout=20)
        if not isinstance(response, dict):
            raise BillingProviderError("Stripe returned an invalid response")
        return response

    @staticmethod
    def _idempotency_key(operation: str, value: str) -> str:
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
        return f"zcoder-{operation}-{digest[:48]}"

    def create_customer(self, organization_id: str, email: str, name: str) -> str:
        if not organization_id.strip() or not email.strip() or not name.strip():
            raise ValueError("organization_id, email, and name are required")
        organization_id = organization_id.strip()
        response = self._request(
            "POST",
            "/customers",
            {"email": email.strip(), "name": name.strip(), "metadata[organization_id]": organization_id},
            idempotency_key=self._idempotency_key("customer", organization_id),
        )
        customer_id = response.get("id")
        if (
            response.get("object") != "customer"
            or not isinstance(customer_id, str)
            or not customer_id.startswith("cus_")
        ):
            raise BillingProviderError("Stripe customer creation returned no valid customer ID")
        return customer_id

    def create_subscription(
        self,
        customer_ref: str,
        plan_tier: PlanTier,
        *,
        idempotency_key: str | None = None,
    ) -> str:
        if not customer_ref.startswith("cus_"):
            raise ValueError("customer_ref must be a Stripe customer ID")
        price_id = self.price_ids.get(plan_tier)
        if not price_id:
            raise BillingConfigurationError(f"No Stripe Price ID configured for plan {plan_tier.value}")
        response = self._request(
            "POST",
            "/subscriptions",
            {
                "customer": customer_ref,
                "items[0][price]": price_id,
                "metadata[plan_tier]": plan_tier.value,
            },
            idempotency_key=idempotency_key
            or self._idempotency_key("subscription", f"{customer_ref}:{plan_tier.value}"),
        )
        subscription_id = response.get("id")
        if (
            response.get("object") != "subscription"
            or not isinstance(subscription_id, str)
            or not subscription_id.startswith("sub_")
        ):
            raise BillingProviderError("Stripe subscription creation returned no valid subscription ID")
        return subscription_id

    def report_usage(
        self,
        customer_ref: str,
        meter_event_id: str,
        metric: str,
        quantity: float,
        *,
        occurred_at: int | None = None,
    ) -> bool:
        if not customer_ref.startswith("cus_"):
            raise ValueError("customer_ref must be a Stripe customer ID")
        if not meter_event_id.strip() or len(meter_event_id) > 100:
            raise ValueError("meter_event_id must contain 1 to 100 characters")
        if (
            isinstance(quantity, bool)
            or not isinstance(quantity, (int, float))
            or not math.isfinite(quantity)
            or quantity <= 0
        ):
            raise ValueError("quantity must be a finite positive number")
        if occurred_at is not None:
            if isinstance(occurred_at, bool) or not isinstance(occurred_at, int):
                raise ValueError("occurred_at must be a Unix timestamp in seconds")
            now = int(time.time())
            if occurred_at < now - 35 * 24 * 60 * 60 or occurred_at > now + 300:
                raise ValueError("occurred_at must be within Stripe's supported 35-day window")
        event_name = self.meter_event_names.get(metric)
        if not event_name or not re.fullmatch(r"[A-Za-z0-9_]{1,100}", event_name):
            raise BillingConfigurationError(
                f"No valid Stripe meter event is configured for metric {metric!r}"
            )
        response = self._request(
            "POST",
            "/billing/meter_events",
            {
                "event_name": event_name,
                "identifier": meter_event_id,
                **({"timestamp": str(occurred_at)} if occurred_at is not None else {}),
                "payload[stripe_customer_id]": customer_ref,
                "payload[value]": format(quantity, ".15g"),
            },
            idempotency_key=self._idempotency_key("meter", meter_event_id),
        )
        return response.get("object") == "billing.meter_event" and bool(response.get("id"))

    def reconcile_subscription(self, customer_ref: str) -> dict[str, Any]:
        if not customer_ref.startswith("cus_"):
            raise ValueError("customer_ref must be a Stripe customer ID")
        subscriptions: list[dict[str, Any]] = []
        starting_after = ""
        while True:
            params = {"customer": customer_ref, "status": "all", "limit": "100"}
            if starting_after:
                params["starting_after"] = starting_after
            response = self._request("GET", "/subscriptions", params)
            page = response.get("data")
            if not isinstance(page, list) or any(not isinstance(item, dict) for item in page):
                raise BillingProviderError("Stripe subscription listing returned invalid data")
            subscriptions.extend(page)
            if response.get("has_more") is not True:
                break
            if not page or not isinstance(page[-1].get("id"), str):
                raise BillingProviderError("Stripe subscription pagination returned no cursor")
            starting_after = page[-1]["id"]

        if not subscriptions:
            return {"status": "none", "customer_ref": customer_ref}
        latest = max(subscriptions, key=lambda item: int(item.get("created", 0)))
        metadata = latest.get("metadata")
        plan_tier = metadata.get("plan_tier") if isinstance(metadata, dict) else None
        return {
            "id": latest.get("id"),
            "customer_ref": customer_ref,
            "status": latest.get("status", "unknown"),
            "plan_tier": plan_tier,
            "created": latest.get("created"),
        }

    def verify_webhook_signature(self, payload: bytes, signature_header: str, secret: str = "") -> bool:
        signing_secret = secret or self.webhook_secret
        if not signing_secret or not isinstance(payload, bytes) or not isinstance(signature_header, str):
            return False
        try:
            fields = [part.strip().split("=", 1) for part in signature_header.split(",")]
            values = [(key, value) for pair in fields if len(pair) == 2 for key, value in [pair]]
            timestamps = [value for key, value in values if key == "t"]
            signatures = [value for key, value in values if key == "v1"]
            if (
                len(timestamps) != 1
                or not re.fullmatch(r"[0-9]+", timestamps[0] if timestamps else "")
                or not signatures
                or not all(re.fullmatch(r"[a-fA-F0-9]{64}", sig) for sig in signatures)
            ):
                return False
            timestamp = int(timestamps[0])
            if abs(time.time() - timestamp) > self.webhook_tolerance_seconds:
                return False
            signed_payload = f"{timestamp}.".encode("ascii") + payload
            expected = hmac.new(signing_secret.encode(), signed_payload, hashlib.sha256).hexdigest()
            return any(hmac.compare_digest(expected, signature.lower()) for signature in signatures)
        except (TypeError, ValueError, UnicodeEncodeError):
            return False


# ---------------------------------------------------------------------------
# Customer Outbound Webhook Models & Delivery
# ---------------------------------------------------------------------------


class WebhookDeliveryStatus(StringEnum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    RETRY = "RETRY"
    FAILED = "FAILED"


@dataclasses.dataclass
class CustomerWebhookEndpoint:
    id: str
    organization_id: str
    url: str
    event_types: set[str]
    secret: str
    active: bool = True
    created_at: float = dataclasses.field(default_factory=time.time)

    def sign_payload(self, event_id: str, timestamp: float, payload_json: str) -> str:
        """Compute HMAC-SHA256 signature for customer webhook verification."""
        to_sign = f"t={timestamp},id={event_id},v={payload_json}".encode()
        return hmac.new(self.secret.encode(), to_sign, hashlib.sha256).hexdigest()


@dataclasses.dataclass
class WebhookDelivery:
    id: str
    endpoint_id: str
    organization_id: str
    event_id: str
    event_type: str
    status: WebhookDeliveryStatus = WebhookDeliveryStatus.PENDING
    http_status: int | None = None
    attempts: int = 0
    created_at: float = dataclasses.field(default_factory=time.time)
    last_attempt_at: float | None = None
