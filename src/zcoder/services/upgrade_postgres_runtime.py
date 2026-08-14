"""Fenced PostgreSQL runtime composition for continuous-engineering state."""

from __future__ import annotations

from collections.abc import Callable

from zcoder.domain.interfaces.engineering_store import EngineeringStore
from zcoder.domain.models.engineering import Attempt, Checkpoint, EngineeringTask
from zcoder.services.upgrade_postgres_fence import PostgresUpgradeFence, UpgradeFenceToken
from zcoder.services.upgrade_postgres_lease import PostgresAdvisoryRunLease


class PostgresFencedRunLeaseError(RuntimeError):
    """Raised when a composed PostgreSQL run lease cannot preserve safe ownership."""


class PostgresFencedRunLease:
    """Acquire distributed exclusivity before issuing a monotonic fence token.

    The advisory lease is acquired first. Only its owner may advance the durable
    fence generation. The token remains available to fenced store mutations only
    while this composed lease is active.
    """

    def __init__(self, advisory_lease: PostgresAdvisoryRunLease, fence: PostgresUpgradeFence) -> None:
        self.advisory_lease = advisory_lease
        self.fence = fence
        self._token: UpgradeFenceToken | None = None

    def acquire(self) -> None:
        if self._token is not None:
            raise PostgresFencedRunLeaseError("PostgreSQL fenced run lease is already acquired")
        self.advisory_lease.acquire()
        try:
            self._token = self.fence.acquire_token()
        except Exception:
            try:
                self.advisory_lease.release()
            except Exception as release_exc:
                raise PostgresFencedRunLeaseError(
                    "unable to roll back PostgreSQL advisory lease after fence acquisition failure"
                ) from release_exc
            raise

    def require_token(self) -> UpgradeFenceToken:
        token = self._token
        if token is None:
            raise PostgresFencedRunLeaseError("PostgreSQL fenced run lease is not acquired")
        return token

    def release(self) -> None:
        if self._token is None:
            return
        self._token = None
        self.advisory_lease.release()

    def __enter__(self) -> PostgresFencedRunLease:
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


FenceTokenProvider = Callable[[], UpgradeFenceToken]


class FencedUpgradeEngineeringStore(EngineeringStore):
    """EngineeringStore view whose upgrade-task mutations require the active fence.

    `EngineeringStoreUpgradeLedger` only mutates tasks through `save_task`, so that
    operation is routed through the PostgreSQL fence. Attempt/checkpoint mutation
    methods fail closed instead of silently bypassing the fence. Read operations
    delegate to the existing PostgreSQL engineering store.
    """

    def __init__(
        self,
        delegate: EngineeringStore,
        fence: PostgresUpgradeFence,
        token_provider: FenceTokenProvider,
    ) -> None:
        self.delegate = delegate
        self.fence = fence
        self.token_provider = token_provider

    def save_task(self, task: EngineeringTask) -> None:
        self.fence.save_task(task, self.token_provider())

    def get_task(self, task_id: str) -> EngineeringTask | None:
        return self.delegate.get_task(task_id)

    def create_attempt(self, attempt: Attempt) -> None:
        raise PostgresFencedRunLeaseError("fenced upgrade store does not permit attempt mutations")

    def save_checkpoint(self, checkpoint: Checkpoint) -> None:
        raise PostgresFencedRunLeaseError("fenced upgrade store does not permit checkpoint-table mutations")

    def get_latest_checkpoint(self, attempt_id: str) -> Checkpoint | None:
        return self.delegate.get_latest_checkpoint(attempt_id)

    def list_tasks(self, status: str | None = None) -> list[EngineeringTask]:
        return self.delegate.list_tasks(status=status)

    def close(self) -> None:
        close = getattr(self.delegate, "close", None)
        if callable(close):
            close()
