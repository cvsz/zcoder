"""Admission control: pure domain policy for admitting work under plan quota.

This module owns the *decision* vocabulary and the plan-based quota gate.
It never sleeps, polls, retries, or touches storage.  Durable reservations
are delegated to an ``AdmissionGate`` implementation supplied by an outer
layer (see ``zcoder.services.admission_gates`` for the callable-injected
adapter that binds to the Postgres quota store).
"""

from __future__ import annotations

import typing
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

if typing.TYPE_CHECKING:
    from zcoder.domain.models.product import EntitlementService

REASON_ADMITTED = "admitted"
REASON_QUOTA_EXCEEDED = "quota_exceeded"
REASON_BACKPRESSURE = "backpressure"
REASON_BACKEND_ERROR = "backend_error"


@dataclass(frozen=True)
class QuotaReservation:
    """Reference to capacity held by a successful admission."""

    reservation_id: str
    tenant_id: str
    metric: str
    units: float


@dataclass(frozen=True)
class AdmissionDecision:
    """Outcome of an admission attempt.

    Fail-closed invariant: when ``admitted`` is ``False``, ``reservation``
    is always ``None`` and ``reason`` explains the rejection.
    """

    admitted: bool
    reason: str
    reservation: QuotaReservation | None = None

    @classmethod
    def reject(cls, reason: str) -> AdmissionDecision:
        return cls(admitted=False, reason=reason)


@runtime_checkable
class AdmissionGate(Protocol):
    """Seam between request handling and quota/backpressure enforcement."""

    def check_and_reserve(self, tenant_id: str, plan: str, requested_units: float) -> AdmissionDecision: ...

    def release(self, reservation: QuotaReservation) -> bool: ...


class PlanQuotaGate:
    """Plan-ceiling gate wrapping :meth:`EntitlementService.check_quota_limit`.

    Semantics mirror ``check_quota_limit``: a metric is admissible while the
    projected value stays strictly below the plan entitlement ceiling.  The
    ``plan`` argument is accepted for interface conformance but ignored —
    matching ``EntitlementService`` semantics, the applicable bundle is always
    derived from the organization's persisted subscription, not from caller
    input.  This gate performs no durable reservation; ``release`` is a no-op
    that reports whether a real reservation was handed to it.
    """

    # Mirrors the metric -> bundle attribute mapping in
    # ``EntitlementService.check_quota_limit``.
    _METRIC_ATTRS = {
        "concurrent_jobs": "concurrent_jobs",
        "monthly_budget_usd": "monthly_budget_usd",
        "projects": "max_projects",
        "repositories": "max_repositories",
    }

    def __init__(
        self,
        entitlements: EntitlementService,
        usage_fn: typing.Callable[[str, str], float],
        metric: str,
    ):
        if metric not in self._METRIC_ATTRS:
            raise ValueError(f"unsupported quota metric: {metric}")
        self._entitlements = entitlements
        self._usage_fn = usage_fn
        self._metric_attr = self._METRIC_ATTRS[metric]

    def check_and_reserve(self, tenant_id: str, plan: str, requested_units: float) -> AdmissionDecision:
        del plan  # entitlements derive the plan from the stored subscription
        try:
            current_value = float(self._usage_fn(tenant_id, self._metric_attr))
        except Exception:
            return AdmissionDecision.reject(REASON_BACKEND_ERROR)
        bundle = self._entitlements.get_entitlements(tenant_id)
        limit = float(getattr(bundle, self._metric_attr, 0.0))
        if current_value + requested_units > limit:
            return AdmissionDecision.reject(REASON_QUOTA_EXCEEDED)
        return AdmissionDecision(admitted=True, reason=REASON_ADMITTED)

    def release(self, reservation: QuotaReservation) -> bool:
        # No capacity is durably held by this gate; nothing to refund.
        return False
