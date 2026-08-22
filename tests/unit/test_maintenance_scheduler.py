from __future__ import annotations

import threading

import pytest

from zcoder.services.maintenance_scheduler import (
    MaintenanceScheduler,
    run_maintenance_scheduler,
)
from zcoder.services.upgrade_lease import UpgradeRunLease, UpgradeRunLeaseError


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class FakeSleep:
    def __init__(self, clock: FakeClock | None = None) -> None:
        self.calls: list[float] = []
        self._clock = clock

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        if self._clock is not None:
            self._clock.now += seconds


class RecordingLease:
    """Exclusive in-process lease modeling real lease acquire/release semantics."""

    def __init__(self, registry: dict[str, object], namespace: str) -> None:
        self._registry = registry
        self._namespace = namespace
        self.acquired = False

    def acquire(self) -> None:
        holder = self._registry.get(self._namespace)
        if holder is not None and holder is not self:
            raise UpgradeRunLeaseError(f"lease already held: {self._namespace}")
        self._registry[self._namespace] = self
        self.acquired = True

    def release(self) -> None:
        if self._registry.get(self._namespace) is self:
            del self._registry[self._namespace]
        self.acquired = False

    def __enter__(self) -> RecordingLease:
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


class ContendedLeaseFactory:
    """Hands out mutually exclusive leases like one filesystem lock file would."""

    def __init__(self, namespace: str = "test-namespace") -> None:
        self.registry: dict[str, object] = {}
        self.namespace = namespace

    def __call__(self) -> RecordingLease:
        return RecordingLease(self.registry, self.namespace)


def make_scheduler(
    *,
    campaign_calls: list[int] | None = None,
    outbox_results: list[int] | list[Exception] | None = None,
    max_cycles: int = 3,
    every_seconds: float = 10.0,
    lease_factory: ContendedLeaseFactory | None = None,
    stop_event: threading.Event | None = None,
) -> tuple[MaintenanceScheduler, FakeSleep]:
    clock = FakeClock()
    sleep = FakeSleep(clock)
    campaign_calls = campaign_calls if campaign_calls is not None else []
    outbox_results = outbox_results if outbox_results is not None else [0]

    call_index = {"n": 0}

    def campaign_runner() -> str:
        campaign_calls.append(1)
        return f"campaign-{len(campaign_calls)}"

    def outbox_processor(*, max_messages: int, max_attempts: int) -> int:
        assert max_messages >= 1
        assert max_attempts >= 1
        result = outbox_results[min(call_index["n"], len(outbox_results) - 1)]
        call_index["n"] += 1
        if isinstance(result, Exception):
            raise result
        return result

    scheduler = MaintenanceScheduler(
        lease_factory=lease_factory or ContendedLeaseFactory(),
        campaign_runner=campaign_runner,
        outbox_processor=outbox_processor,
        every_seconds=every_seconds,
        max_cycles=max_cycles,
        clock=clock,
        sleep_func=sleep,
        stop_event=stop_event,
    )
    return scheduler, sleep


def test_exactly_one_campaign_per_interval():
    campaign_calls: list[int] = []
    scheduler, sleep = make_scheduler(campaign_calls=campaign_calls, max_cycles=4)

    results = scheduler.run()

    assert len(campaign_calls) == 4
    assert len(results) == 4
    assert [r.cycle_index for r in results] == [0, 1, 2, 3]
    assert all(r.campaign_ran for r in results)
    assert sleep.calls == [10.0, 10.0, 10.0]


def test_lease_unavailable_skips_cycle_without_raising():
    factory = ContendedLeaseFactory()

    class Holder:
        pass

    factory.registry[factory.namespace] = Holder()

    campaign_calls: list[int] = []
    scheduler, sleep = make_scheduler(campaign_calls=campaign_calls, max_cycles=2, lease_factory=factory)

    results = scheduler.run()

    assert campaign_calls == []
    assert [r.skipped_reason for r in results] == ["lease-unavailable", "lease-unavailable"]
    assert not any(r.campaign_ran for r in results)


def test_two_schedulers_same_namespace_only_one_runs_campaigns(tmp_path):
    lock_path = tmp_path / "scheduler.lease"
    campaign_calls_a: list[int] = []
    campaign_calls_b: list[int] = []

    clock = FakeClock()
    sleep = FakeSleep(clock)

    runner_a_calls = campaign_calls_a
    runner_b_calls = campaign_calls_b

    scheduler_a = MaintenanceScheduler(
        lease_factory=lambda: UpgradeRunLease(lock_path),
        campaign_runner=lambda: runner_a_calls.append(1),
        outbox_processor=lambda *, max_messages, max_attempts: 0,
        every_seconds=1.0,
        max_cycles=1,
        clock=clock,
        sleep_func=sleep,
    )
    scheduler_b = MaintenanceScheduler(
        lease_factory=lambda: UpgradeRunLease(lock_path),
        campaign_runner=lambda: runner_b_calls.append(1),
        outbox_processor=lambda *, max_messages, max_attempts: 0,
        every_seconds=1.0,
        max_cycles=1,
        clock=clock,
        sleep_func=sleep,
    )

    results_a = scheduler_a.run()
    held = UpgradeRunLease(lock_path)
    held.acquire()
    try:
        results_b = scheduler_b.run()
    finally:
        held.release()

    assert campaign_calls_a == [1]
    assert campaign_calls_b == []
    assert results_a[0].campaign_ran is True
    assert results_b[0].skipped_reason == "lease-unavailable"


def test_sigterm_stop_event_stops_between_cycles():
    stop_event = threading.Event()
    campaign_calls: list[int] = []

    clock = FakeClock()
    sleep = FakeSleep(clock)

    def campaign_runner() -> None:
        campaign_calls.append(1)
        stop_event.set()

    scheduler = MaintenanceScheduler(
        lease_factory=ContendedLeaseFactory(),
        campaign_runner=campaign_runner,
        outbox_processor=lambda *, max_messages, max_attempts: 0,
        every_seconds=5.0,
        max_cycles=10,
        clock=clock,
        sleep_func=sleep,
        stop_event=stop_event,
    )

    results = scheduler.run()

    assert len(results) == 1
    assert len(campaign_calls) == 1
    assert sleep.calls == []


def test_max_cycles_bound_is_respected_even_when_never_stopped():
    campaign_calls: list[int] = []
    scheduler, sleep = make_scheduler(campaign_calls=campaign_calls, max_cycles=7)

    results = scheduler.run()

    assert len(results) == 7
    assert len(campaign_calls) == 7
    assert scheduler.max_cycles == 7
    assert len(sleep.calls) == 6


class IdempotentOutboxHarness:
    """Real-ish durable outbox flow: enqueue keyed summaries, drain exactly once."""

    def __init__(self, fail_first_drain: bool) -> None:
        self.pending: list[str] = []
        self.delivered: list[str] = []
        self.fail_first_drain = fail_first_drain
        self.drains = 0
        self.enqueue_failures = 0

    def enqueue_summary(self, idempotency_key: str) -> None:
        self.pending.append(idempotency_key)

    def process_outbox(self, *, max_messages: int, max_attempts: int) -> int:
        self.drains += 1
        if self.fail_first_drain and self.drains == 1:
            raise RuntimeError("simulated crash between campaign enqueue and drain")
        batch = self.pending[:max_messages]
        self.delivered.extend(batch)
        self.pending = self.pending[len(batch) :]
        return len(batch)


def test_crash_between_campaign_and_drain_recovers_with_exactly_one_delivery_next_cycle():
    harness = IdempotentOutboxHarness(fail_first_drain=True)
    campaign_calls: list[int] = []

    clock = FakeClock()
    sleep = FakeSleep(clock)
    drains = {"n": 0}

    def campaign_runner() -> str:
        campaign_calls.append(1)
        harness.enqueue_summary(f"maintenance-campaign:maintenance-{len(campaign_calls)}")
        return "dispatched"

    def outbox_processor(*, max_messages: int, max_attempts: int) -> int:
        harness.process_outbox(max_messages=max_messages, max_attempts=max_attempts)
        drains["n"] += 1
        return 0

    scheduler = MaintenanceScheduler(
        lease_factory=ContendedLeaseFactory(),
        campaign_runner=campaign_runner,
        outbox_processor=outbox_processor,
        every_seconds=1.0,
        max_cycles=2,
        clock=clock,
        sleep_func=sleep,
    )

    results = scheduler.run()

    assert len(campaign_calls) == 2
    assert harness.drains == 2
    assert results[0].skipped_reason == "cycle-failed"
    assert results[1].skipped_reason == ""
    # Cycle 0's durable summary is drained exactly once in cycle 1; cycle 1's
    # own summary (one campaign per interval) is drained in that same drain.
    expected_keys = [
        "maintenance-campaign:maintenance-1",
        "maintenance-campaign:maintenance-2",
    ]
    assert harness.delivered == expected_keys
    assert len(set(harness.delivered)) == len(harness.delivered)
    assert harness.pending == []


def test_run_function_composes_injected_collaborators():
    campaign_calls: list[int] = []

    results = run_maintenance_scheduler(
        lease_factory=ContendedLeaseFactory(),
        campaign_runner=lambda: campaign_calls.append(1),
        outbox_processor=lambda *, max_messages, max_attempts: 3,
        every_seconds=0.0,
        max_cycles=2,
        clock=FakeClock(),
        sleep_func=FakeSleep(),
    )

    assert len(results) == 2
    assert len(campaign_calls) == 2
    assert [r.outbox_processed for r in results] == [3, 3]


def test_invalid_bounds_are_rejected():
    with pytest.raises(ValueError, match="max_cycles"):
        MaintenanceScheduler(
            lease_factory=ContendedLeaseFactory(),
            campaign_runner=lambda: None,
            outbox_processor=lambda *, max_messages, max_attempts: 0,
            every_seconds=1.0,
            max_cycles=0,
        )
    with pytest.raises(ValueError, match="every_seconds"):
        MaintenanceScheduler(
            lease_factory=ContendedLeaseFactory(),
            campaign_runner=lambda: None,
            outbox_processor=lambda *, max_messages, max_attempts: 0,
            every_seconds=-1.0,
            max_cycles=1,
        )
