"""Durable admission gates binding the domain admission seam to storage.

The architecture boundary rules forbid this package from importing
``zcoder.infrastructure`` directly, so :class:`DurableQuotaGate` is wired to
the Postgres quota store through injected callables.  The composition root
(a later wave) supplies::

    reserve_fn(tenant_id, metric, units) -> bool
        binds ``EnterprisePostgresStore.check_and_reserve_quota``; ``True``
        means capacity was atomically reserved (usage incremented).
    queue_stats_fn() -> Mapping[str, int]
        binds ``PostgresJobStore.get_queue_stats`` (status -> count).
    release_fn(tenant_id, metric, units) -> bool
        optional refund path; the store currently ships no refund function,
        so callers may omit it.

Both adapters fail closed: any backend error yields a rejected decision.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable, Mapping

from zcoder.domain.services.admission import (
    REASON_ADMITTED,
    REASON_BACKEND_ERROR,
    REASON_BACKPRESSURE,
    REASON_QUOTA_EXCEEDED,
    AdmissionDecision,
    QuotaReservation,
)

ReserveFn = Callable[[str, str, float], bool]
QueueStatsFn = Callable[[], Mapping[str, int]]
ReleaseFn = Callable[[str, str, float], bool]


class DurableQuotaGate:
    """Quota + backpressure gate over durable callables.  Fail-closed."""

    def __init__(
        self,
        reserve_fn: ReserveFn,
        queue_stats_fn: QueueStatsFn,
        metric: str = "concurrent_jobs",
        max_queue_depth: int = 100,
        tracked_statuses: Iterable[str] = ("pending", "queued"),
        release_fn: ReleaseFn | None = None,
    ):
        self._reserve_fn = reserve_fn
        self._queue_stats_fn = queue_stats_fn
        self._release_fn = release_fn
        self._metric = metric
        self._max_queue_depth = max_queue_depth
        self._tracked_statuses = frozenset(tracked_statuses)

    def check_and_reserve(self, tenant_id: str, plan: str, requested_units: float) -> AdmissionDecision:
        del plan  # durable limits are enforced per tenant quota rows, not plan tier
        try:
            depth = self._queue_depth()
        except Exception:
            return AdmissionDecision.reject(REASON_BACKEND_ERROR)
        if depth >= self._max_queue_depth:
            return AdmissionDecision.reject(REASON_BACKPRESSURE)
        try:
            reserved = bool(self._reserve_fn(tenant_id, self._metric, requested_units))
        except Exception:
            return AdmissionDecision.reject(REASON_BACKEND_ERROR)
        if not reserved:
            return AdmissionDecision.reject(REASON_QUOTA_EXCEEDED)
        reservation = QuotaReservation(
            reservation_id=uuid.uuid4().hex,
            tenant_id=tenant_id,
            metric=self._metric,
            units=requested_units,
        )
        return AdmissionDecision(admitted=True, reason=REASON_ADMITTED, reservation=reservation)

    def release(self, reservation: QuotaReservation) -> bool:
        if self._release_fn is None:
            return False
        try:
            return bool(self._release_fn(reservation.tenant_id, reservation.metric, reservation.units))
        except Exception:
            return False

    def _queue_depth(self) -> int:
        stats = self._queue_stats_fn()
        return sum(int(stats.get(status, 0)) for status in self._tracked_statuses)
