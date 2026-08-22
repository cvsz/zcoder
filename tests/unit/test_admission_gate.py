"""Unit tests for the admission-control gate seam (F6)."""

from __future__ import annotations

import pytest

from zcoder.domain.models.product import (
    PLAN_ENTITLEMENTS,
    EntitlementService,
    PlanTier,
)
from zcoder.domain.services.admission import (
    REASON_ADMITTED,
    REASON_BACKEND_ERROR,
    REASON_BACKPRESSURE,
    REASON_QUOTA_EXCEEDED,
    AdmissionDecision,
    AdmissionGate,
    PlanQuotaGate,
    QuotaReservation,
)
from zcoder.services.admission_gates import DurableQuotaGate


class StubEntitlements:
    """Minimal stand-in exposing only what PlanQuotaGate consumes."""

    def __init__(self, **limits):
        self._bundle = PLAN_ENTITLEMENTS[PlanTier.DEVELOPER]
        self._limits = limits

    def get_entitlements(self, organization_id):
        merged = dict(self._bundle.__dict__)
        merged.update(self._limits)
        return type(self._bundle)(**merged)


def _service_with_limit(metric_attr: str, value) -> StubEntitlements:
    return StubEntitlements(**{metric_attr: value})


# ── Protocol conformance ────────────────────────────────────────────────


def test_adapters_satisfy_admission_gate_protocol():
    gate = PlanQuotaGate(
        entitlements=EntitlementService(),
        usage_fn=lambda _tenant, _metric: 0.0,
        metric="concurrent_jobs",
    )
    durable = DurableQuotaGate(reserve_fn=lambda *_: True, queue_stats_fn=lambda: {})
    assert isinstance(gate, AdmissionGate)
    assert isinstance(durable, AdmissionGate)


# ── PlanQuotaGate ───────────────────────────────────────────────────────


class TestPlanQuotaGate:
    def test_admits_within_quota(self):
        svc = _service_with_limit("concurrent_jobs", 3)
        gate = PlanQuotaGate(svc, usage_fn=lambda t, m: {"concurrent_jobs": 2}[m], metric="concurrent_jobs")
        decision = gate.check_and_reserve("t-1", "developer", 1.0)
        assert decision.admitted is True
        assert decision.reason == REASON_ADMITTED
        # Read-only plan ceiling: nothing durably held.
        assert decision.reservation is None

    def test_rejects_at_limit(self):
        svc = _service_with_limit("concurrent_jobs", 3)
        gate = PlanQuotaGate(svc, usage_fn=lambda t, m: 3.0, metric="concurrent_jobs")
        decision = gate.check_and_reserve("t-1", "developer", 1.0)
        assert decision.admitted is False
        assert decision.reason == REASON_QUOTA_EXCEEDED
        assert decision.reservation is None

    def test_rejects_when_requested_units_would_exceed(self):
        svc = _service_with_limit("monthly_budget_usd", 100.0)
        gate = PlanQuotaGate(svc, usage_fn=lambda t, m: 95.0, metric="monthly_budget_usd")
        decision = gate.check_and_reserve("t-1", "developer", 10.0)
        assert decision.admitted is False
        assert decision.reason == REASON_QUOTA_EXCEEDED

    def test_fail_closed_on_usage_backend_error(self):
        svc = _service_with_limit("concurrent_jobs", 3)

        def boom(tenant, metric):
            raise RuntimeError("usage store down")

        decision = PlanQuotaGate(svc, usage_fn=boom, metric="concurrent_jobs").check_and_reserve(
            "t-1", "developer", 1.0
        )
        assert decision.admitted is False
        assert decision.reason == REASON_BACKEND_ERROR


# ── DurableQuotaGate ────────────────────────────────────────────────────


class FakeQuotaStore:
    """Mimics EnterprisePostgresStore.check_and_reserve_quota contract."""

    def __init__(self, limit: float = 10.0):
        self.limit = limit
        self.current: dict[tuple[str, str], float] = {}
        self.reserve_calls: list[tuple[str, str, float]] = []
        self.release_calls: list[tuple[str, str, float]] = []

    def reserve(self, tenant_id: str, metric: str, units: float) -> bool:
        self.reserve_calls.append((tenant_id, metric, units))
        key = (tenant_id, metric)
        if self.current.get(key, 0.0) + units > self.limit:
            return False
        self.current[key] = self.current.get(key, 0.0) + units
        return True

    def refund(self, tenant_id: str, metric: str, units: float) -> bool:
        self.release_calls.append((tenant_id, metric, units))
        key = (tenant_id, metric)
        if key not in self.current:
            return False
        self.current[key] = max(0.0, self.current[key] - units)
        return True


class TestDurableQuotaGate:
    def _gate(self, store: FakeQuotaStore, queue=None, max_depth=100, release=True):
        return DurableQuotaGate(
            reserve_fn=store.reserve,
            queue_stats_fn=(lambda: queue if queue is not None else {}),
            release_fn=store.refund if release else None,
            metric="concurrent_jobs",
            max_queue_depth=max_depth,
        )

    def test_admits_within_quota_and_records_reservation(self):
        store = FakeQuotaStore(limit=3.0)
        gate = self._gate(store, queue={"pending": 1, "queued": 2})
        decision = gate.check_and_reserve("t-1", "developer", 1.0)
        assert decision.admitted is True
        assert decision.reason == REASON_ADMITTED
        assert isinstance(decision.reservation, QuotaReservation)
        assert decision.reservation.tenant_id == "t-1"
        assert decision.reservation.metric == "concurrent_jobs"
        assert decision.reservation.units == 1.0
        assert store.current[("t-1", "concurrent_jobs")] == 1.0

    def test_rejects_at_quota_limit_without_reservation(self):
        store = FakeQuotaStore(limit=3.0)
        gate = self._gate(store)
        assert gate.check_and_reserve("t-1", "developer", 3.0).admitted is True
        decision = gate.check_and_reserve("t-1", "developer", 1.0)
        assert decision.admitted is False
        assert decision.reason == REASON_QUOTA_EXCEEDED
        assert decision.reservation is None

    def test_release_refunds_reserved_units(self):
        store = FakeQuotaStore(limit=3.0)
        gate = self._gate(store)
        decision = gate.check_and_reserve("t-1", "developer", 2.0)
        assert gate.release(decision.reservation) is True
        assert store.current[("t-1", "concurrent_jobs")] == 0.0
        # Capacity freed: re-admission succeeds.
        assert gate.check_and_reserve("t-1", "developer", 2.0).admitted is True

    def test_release_without_release_fn_reports_not_released(self):
        store = FakeQuotaStore()
        gate = self._gate(store, release=False)
        decision = gate.check_and_reserve("t-1", "developer", 1.0)
        assert gate.release(decision.reservation) is False

    def test_release_is_fail_closed_on_backend_error(self):
        gate = DurableQuotaGate(
            reserve_fn=lambda *a: True,
            queue_stats_fn=lambda: {},
            release_fn=lambda *a: (_ for _ in ()).throw(RuntimeError("down")),
        )
        reservation = QuotaReservation("r-1", "t-1", "concurrent_jobs", 1.0)
        assert gate.release(reservation) is False

    @pytest.mark.parametrize("depth", [100, 250])
    def test_backpressure_rejects_at_and_over_threshold_before_reserving(self, depth):
        store = FakeQuotaStore(limit=1000.0)
        gate = self._gate(store, queue={"pending": depth}, max_depth=100)
        decision = gate.check_and_reserve("t-1", "developer", 1.0)
        assert decision.admitted is False
        assert decision.reason == REASON_BACKPRESSURE
        assert store.reserve_calls == []  # no reservation attempted under pressure
        assert decision.reservation is None

    def test_below_threshold_admits(self):
        store = FakeQuotaStore()
        gate = self._gate(store, queue={"pending": 99, "queued": 0}, max_depth=100)
        assert gate.check_and_reserve("t-1", "developer", 1.0).admitted is True

    def test_untracked_statuses_do_not_count_toward_depth(self):
        store = FakeQuotaStore()
        gate = self._gate(store, queue={"completed": 500, "failed": 400}, max_depth=100)
        assert gate.check_and_reserve("t-1", "developer", 1.0).admitted is True

    def test_fail_closed_on_queue_stats_error_and_no_reserve_attempted(self):
        store = FakeQuotaStore()

        def broken_stats():
            raise RuntimeError("queue stats unavailable")

        gate = DurableQuotaGate(
            reserve_fn=store.reserve,
            queue_stats_fn=broken_stats,
            metric="concurrent_jobs",
            max_queue_depth=100,
        )
        decision = gate.check_and_reserve("t-1", "developer", 1.0)
        assert decision.admitted is False
        assert decision.reason == REASON_BACKEND_ERROR
        assert store.reserve_calls == []

    def test_fail_closed_on_reserve_backend_error(self):
        def broken_reserve(tenant_id, metric, units):
            raise RuntimeError("quota row lock timeout")

        gate = DurableQuotaGate(
            reserve_fn=broken_reserve,
            queue_stats_fn=lambda: {},
            metric="concurrent_jobs",
            max_queue_depth=100,
        )
        decision = gate.check_and_reserve("t-1", "developer", 1.0)
        assert decision.admitted is False
        assert decision.reason == REASON_BACKEND_ERROR

    def test_no_double_reserve_within_a_single_admission(self):
        store = FakeQuotaStore()
        gate = self._gate(store)
        decision = gate.check_and_reserve("t-1", "developer", 2.0)
        assert decision.admitted is True
        assert len(store.reserve_calls) == 1
        assert store.current[("t-1", "concurrent_jobs")] == 2.0

    def test_retry_without_release_consumes_quota_again_per_store_semantics(self):
        # The PG store's check_and_reserve_quota is non-idempotent (no dedup
        # key): every successful call increments usage.  The gate mirrors this
        # exactly-once-per-call contract — it never suppresses or retries a
        # reserve internally, so callers MUST release before re-reserving or
        # capacity is consumed twice.
        store = FakeQuotaStore(limit=3.0)
        gate = self._gate(store)
        first = gate.check_and_reserve("t-1", "developer", 1.0)
        second = gate.check_and_reserve("t-1", "developer", 1.0)
        assert first.admitted and second.admitted
        assert first.reservation.reservation_id != second.reservation.reservation_id
        assert len(store.reserve_calls) == 2
        assert store.current[("t-1", "concurrent_jobs")] == 2.0
        third = gate.check_and_reserve("t-1", "developer", 1.0)
        fourth = gate.check_and_reserve("t-1", "developer", 1.0)
        assert third.admitted is True and fourth.admitted is False
        assert store.current[("t-1", "concurrent_jobs")] == 3.0


# ── Decision invariants ────────────────────────────────────────────────


def test_rejected_decision_factory_has_no_reservation():
    decision = AdmissionDecision.reject(REASON_QUOTA_EXCEEDED)
    assert decision.admitted is False
    assert decision.reservation is None
