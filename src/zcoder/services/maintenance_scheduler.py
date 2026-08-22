"""Bounded scheduler entrypoint for recurring maintenance campaigns.

Recurrence policy is deliberately minimal and externalizable: acquire the
namespace run lease, run exactly one campaign once per interval, drain the
durable outbox with finite budgets, then release. The loop never runs a
campaign while another process holds the same lease (fail-closed skip), stops
between cycles on a stop event or SIGTERM, and is always bounded by a hard
``max_cycles`` limit. All collaborators are injected so tests never touch real
infrastructure.
"""

from __future__ import annotations

import logging
import signal
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from zcoder.services.upgrade_lease import RunLease, UpgradeRunLeaseError
from zcoder.services.upgrade_postgres_lease import PostgresUpgradeRunLeaseError

LOGGER = logging.getLogger(__name__)

DEFAULT_OUTBOX_MAX_MESSAGES = 100
DEFAULT_OUTBOX_MAX_ATTEMPTS = 3

Clock = Callable[[], float]
SleepFunc = Callable[[float], None]


class StopEvent(Protocol):
    """Minimal ``threading.Event``-compatible graceful-stop flag."""

    def is_set(self) -> bool: ...


@dataclass(frozen=True)
class MaintenanceSchedulerCycleResult:
    """Structured outcome of one bounded scheduler cycle."""

    cycle_index: int
    lease_acquired: bool
    campaign_ran: bool
    outbox_processed: int | None
    skipped_reason: str = ""


def install_sigterm_stop(stop_event: Any) -> Any:
    """Install SIGTERM/SIGINT handlers that set ``stop_event``; return the old handlers."""

    def _handler(signum: int, frame: Any) -> None:
        LOGGER.info("maintenance scheduler received signal %s; stopping between cycles", signum)
        stop_event.set()

    installed = {}
    for sig in (signal.SIGTERM, signal.SIGINT):
        installed[sig] = signal.signal(sig, _handler)
    return installed


class MaintenanceScheduler:
    """Bounded fail-closed loop over one-shot maintenance-campaign workers.

    The scheduler owns no campaign, outbox, or lease implementation. It only
    sequences them: lease first, exactly one campaign per interval, one finite
    outbox drain, release, sleep. Every collaborator is injectable.
    """

    def __init__(
        self,
        *,
        lease_factory: Callable[[], RunLease],
        campaign_runner: Callable[[], Any],
        outbox_processor: Callable[..., int],
        every_seconds: float = 300.0,
        max_cycles: int,
        clock: Clock = time.monotonic,
        sleep_func: SleepFunc = time.sleep,
        stop_event: StopEvent | None = None,
        outbox_max_messages: int = DEFAULT_OUTBOX_MAX_MESSAGES,
        outbox_max_attempts: int = DEFAULT_OUTBOX_MAX_ATTEMPTS,
    ) -> None:
        if max_cycles < 1:
            raise ValueError("max_cycles must be >= 1")
        if every_seconds < 0:
            raise ValueError("every_seconds must be >= 0")
        if outbox_max_messages < 1:
            raise ValueError("outbox_max_messages must be >= 1")
        if outbox_max_attempts < 1:
            raise ValueError("outbox_max_attempts must be >= 1")

        self._lease_factory = lease_factory
        self._campaign_runner = campaign_runner
        self._outbox_processor = outbox_processor
        self._every_seconds = float(every_seconds)
        self._max_cycles = int(max_cycles)
        self._clock = clock
        self._sleep_func = sleep_func
        self._stop_event = stop_event
        self._outbox_max_messages = int(outbox_max_messages)
        self._outbox_max_attempts = int(outbox_max_attempts)

    @property
    def max_cycles(self) -> int:
        return self._max_cycles

    def should_stop(self) -> bool:
        return self._stop_event is not None and bool(self._stop_event.is_set())

    def run(self) -> list[MaintenanceSchedulerCycleResult]:
        """Run at most ``max_cycles`` bounded cycles; stop early on the stop event."""

        results: list[MaintenanceSchedulerCycleResult] = []
        for index in range(self._max_cycles):
            if self.should_stop():
                LOGGER.info("maintenance scheduler stopped before cycle %d of %d", index, self._max_cycles)
                break
            results.append(self.run_cycle(index))
            if index + 1 < self._max_cycles:
                self._sleep_interval()
        return results

    def _sleep_interval(self) -> None:
        if self._every_seconds <= 0 or self.should_stop():
            return
        started_at = self._clock()
        self._sleep_func(self._every_seconds)
        LOGGER.debug("maintenance scheduler slept %.3fs", self._clock() - started_at)

    def run_cycle(self, index: int) -> MaintenanceSchedulerCycleResult:
        """Run one lease-guarded cycle: campaign once, drain outbox once, release."""

        lease = self._lease_factory()
        try:
            lease.acquire()
        except (UpgradeRunLeaseError, PostgresUpgradeRunLeaseError) as exc:
            # Fail closed: another holder owns this namespace, so skipping is safe.
            LOGGER.warning("maintenance scheduler cycle %d skipped: lease unavailable (%s)", index, exc)
            return MaintenanceSchedulerCycleResult(
                cycle_index=index,
                lease_acquired=False,
                campaign_ran=False,
                outbox_processed=None,
                skipped_reason="lease-unavailable",
            )

        campaign_result: Any = None
        try:
            campaign_result = self._campaign_runner()
            processed = self._outbox_processor(
                max_messages=self._outbox_max_messages,
                max_attempts=self._outbox_max_attempts,
            )
        except Exception as exc:
            # The durable outbox idempotency key makes the next cycle's single
            # drain exactly-once, so surviving to the next cycle is the safest
            # recovery for a crash between campaign enqueue and outbox delivery.
            LOGGER.error("maintenance scheduler cycle %d failed: %s", index, exc)
            return MaintenanceSchedulerCycleResult(
                cycle_index=index,
                lease_acquired=True,
                campaign_ran=campaign_result is not None,
                outbox_processed=None,
                skipped_reason="cycle-failed",
            )
        finally:
            try:
                lease.release()
            except (UpgradeRunLeaseError, PostgresUpgradeRunLeaseError) as exc:
                LOGGER.error("maintenance scheduler cycle %d could not release lease: %s", index, exc)

        return MaintenanceSchedulerCycleResult(
            cycle_index=index,
            lease_acquired=True,
            campaign_ran=True,
            outbox_processed=processed,
        )


def run_maintenance_scheduler(
    *,
    lease_factory: Callable[[], RunLease],
    campaign_runner: Callable[[], Any],
    outbox_processor: Callable[..., int],
    every_seconds: float = 300.0,
    max_cycles: int,
    clock: Clock = time.monotonic,
    sleep_func: SleepFunc = time.sleep,
    stop_event: StopEvent | None = None,
    outbox_max_messages: int = DEFAULT_OUTBOX_MAX_MESSAGES,
    outbox_max_attempts: int = DEFAULT_OUTBOX_MAX_ATTEMPTS,
) -> list[MaintenanceSchedulerCycleResult]:
    """Compose a :class:`MaintenanceScheduler` from injected collaborators and run it."""

    return MaintenanceScheduler(
        lease_factory=lease_factory,
        campaign_runner=campaign_runner,
        outbox_processor=outbox_processor,
        every_seconds=every_seconds,
        max_cycles=max_cycles,
        clock=clock,
        sleep_func=sleep_func,
        stop_event=stop_event,
        outbox_max_messages=outbox_max_messages,
        outbox_max_attempts=outbox_max_attempts,
    ).run()
