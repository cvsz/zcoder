"""Unit coverage for Upgrade-32 PostgreSQL runtime composition."""

import time

import pytest

from zcoder.domain.models.engineering import EngineeringTask, TaskStatus
from zcoder.services.upgrade_postgres_fence import UpgradeFenceToken
from zcoder.services.upgrade_postgres_runtime import (
    FencedUpgradeEngineeringStore,
    PostgresFencedRunLease,
    PostgresFencedRunLeaseError,
)


class FakeAdvisoryLease:
    def __init__(self, events, *, release_error=None):
        self.events = events
        self.release_error = release_error
        self.acquired = False

    def acquire(self):
        self.events.append("advisory.acquire")
        self.acquired = True

    def release(self):
        self.events.append("advisory.release")
        self.acquired = False
        if self.release_error is not None:
            raise self.release_error


class FakeFence:
    def __init__(self, events, *, acquire_error=None):
        self.events = events
        self.acquire_error = acquire_error
        self.token = UpgradeFenceToken("fleet-a", "control", 7)
        self.saved = []

    def acquire_token(self):
        self.events.append("fence.acquire")
        if self.acquire_error is not None:
            raise self.acquire_error
        return self.token

    def save_task(self, task, token):
        self.events.append("fence.save")
        self.saved.append((task, token))


class FakeStore:
    def __init__(self):
        self.tasks = {}
        self.closed = False

    def save_task(self, task):
        self.tasks[task.id] = task

    def get_task(self, task_id):
        return self.tasks.get(task_id)

    def create_attempt(self, attempt):
        raise AssertionError("attempt write must not delegate")

    def save_checkpoint(self, checkpoint):
        raise AssertionError("checkpoint write must not delegate")

    def get_latest_checkpoint(self, attempt_id):
        return None

    def list_tasks(self, status=None):
        values = list(self.tasks.values())
        if status is None:
            return values
        return [task for task in values if task.status.value == status]

    def close(self):
        self.closed = True


def test_composed_lease_acquires_advisory_before_fence_and_releases():
    events = []
    advisory = FakeAdvisoryLease(events)
    fence = FakeFence(events)
    lease = PostgresFencedRunLease(advisory, fence)

    with lease:
        assert lease.require_token() == fence.token
        assert events == ["advisory.acquire", "fence.acquire"]

    assert events == ["advisory.acquire", "fence.acquire", "advisory.release"]
    with pytest.raises(PostgresFencedRunLeaseError, match="not acquired"):
        lease.require_token()


def test_fence_acquire_failure_rolls_back_advisory_lease():
    events = []
    advisory = FakeAdvisoryLease(events)
    fence = FakeFence(events, acquire_error=RuntimeError("fence unavailable"))
    lease = PostgresFencedRunLease(advisory, fence)

    with pytest.raises(RuntimeError, match="fence unavailable"):
        lease.acquire()

    assert events == ["advisory.acquire", "fence.acquire", "advisory.release"]
    assert advisory.acquired is False


def test_fence_acquire_and_rollback_failure_is_fail_closed():
    events = []
    advisory = FakeAdvisoryLease(events, release_error=RuntimeError("unlock failed"))
    fence = FakeFence(events, acquire_error=RuntimeError("fence unavailable"))
    lease = PostgresFencedRunLease(advisory, fence)

    with pytest.raises(PostgresFencedRunLeaseError, match="roll back"):
        lease.acquire()


def test_fenced_store_routes_task_write_through_current_token():
    events = []
    delegate = FakeStore()
    fence = FakeFence(events)
    token = fence.token
    store = FencedUpgradeEngineeringStore(delegate, fence, lambda: token)
    task = EngineeringTask(
        id="work-1",
        task_description="fenced write",
        status=TaskStatus.PAUSED,
        created_at=time.time(),
        metadata={"kind": "upgrade"},
    )

    store.save_task(task)

    assert fence.saved == [(task, token)]
    assert events == ["fence.save"]


def test_fenced_store_refuses_unfenced_mutation_surfaces():
    store = FencedUpgradeEngineeringStore(FakeStore(), FakeFence([]), lambda: UpgradeFenceToken("a", "b", 1))

    with pytest.raises(PostgresFencedRunLeaseError, match="attempt mutations"):
        store.create_attempt(object())
    with pytest.raises(PostgresFencedRunLeaseError, match="checkpoint-table mutations"):
        store.save_checkpoint(object())


def test_fenced_store_delegates_reads_and_close():
    delegate = FakeStore()
    task = EngineeringTask(
        id="work-1",
        task_description="read",
        status=TaskStatus.PAUSED,
        created_at=time.time(),
    )
    delegate.save_task(task)
    store = FencedUpgradeEngineeringStore(delegate, FakeFence([]), lambda: UpgradeFenceToken("a", "b", 1))

    assert store.get_task("work-1") is task
    assert store.list_tasks("PAUSED") == [task]
    assert store.get_latest_checkpoint("attempt") is None
    store.close()
    assert delegate.closed is True
