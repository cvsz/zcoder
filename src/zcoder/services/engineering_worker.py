"""engineering_worker.py — Executes claimed engineering tasks.

Bounded drain loop: claim -> execute via injected handler -> record
attempt/checkpoint -> complete. Fail-closed: handler exceptions mark the task
FAILED and the loop continues. Exits cleanly when no claimable task remains
(drain-complete) or when ``max_tasks`` is reached.
"""

from __future__ import annotations

import inspect
import logging
import time
from typing import Any, Callable

from zcoder.domain.interfaces.engineering_store import EngineeringStore
from zcoder.domain.models.engineering import Attempt, Checkpoint, EngineeringTask, TaskStatus

logger = logging.getLogger(__name__)

Handler = Callable[[EngineeringTask], Any]


def _default_handler(task: EngineeringTask) -> dict[str, Any]:
    """Default no-op execution preserving prior stub behavior."""
    logger.info("Worker executed task %s (no handler injected)", task.id)
    return {"status": "completed"}


class EngineeringWorker:
    def __init__(
        self,
        store: EngineeringStore,
        worker_id: str,
        handler: Handler | None = None,
        lease_seconds: float = 60.0,
    ):
        self.store = store
        self.worker_id = worker_id
        self.handler = handler or _default_handler
        self.lease_seconds = lease_seconds
        # Older store implementations (e.g. Postgres) expose a no-arg claim_task().
        params = inspect.signature(self.store.claim_task).parameters
        self._store_supports_lease_claim = "claimed_by" in params

    def _claim(self, task_id: str | None = None) -> EngineeringTask | None:
        if self._store_supports_lease_claim:
            return self.store.claim_task(
                task_id=task_id, claimed_by=self.worker_id, lease_seconds=self.lease_seconds
            )
        return self.store.claim_task()

    def run_once(self) -> bool:
        """Claim and process a single task. Returns False when nothing is claimable."""
        task = self._claim()
        if task is None:
            return False
        logger.info("Worker %s claimed task %s", self.worker_id, task.id)
        attempt = Attempt(task_id=task.id)
        try:
            result = self.handler(task)
        except Exception as exc:
            # Fail-closed: record the failure, never crash the drain loop.
            logger.exception("Handler failed for task %s: %s", task.id, exc)
            attempt.status = "FAILED"
            attempt.completed_at = time.time()
            self.store.create_attempt(attempt)
            task.status = TaskStatus.FAILED
            self.store.save_task(task)
            return True

        attempt.status = "SUCCEEDED"
        attempt.completed_at = time.time()
        self.store.create_attempt(attempt)
        self.store.save_checkpoint(
            Checkpoint(
                task_id=task.id,
                attempt_id=attempt.id,
                sequence=1,
                phase="execute",
                state_snapshot={"result": result},
            )
        )
        task.status = TaskStatus.SUCCEEDED
        self.store.save_task(task)
        return True

    def run(self, max_tasks: int | None = None) -> int:
        """Drain claimable tasks until the queue is empty (or ``max_tasks`` hit).

        Returns the number of tasks processed. A clean drain-complete exit is an
        empty claim result, which also covers expired-lease tasks once they have
        been reclaimed and finished.
        """
        processed = 0
        while max_tasks is None or processed < max_tasks:
            if not self.run_once():
                break
            processed += 1
        logger.info("Worker %s drained %d task(s); exiting.", self.worker_id, processed)
        return processed
