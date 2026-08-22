import unittest

from zcoder.domain.models.engineering import EngineeringTask, TaskStatus
from zcoder.services.engineering_worker import EngineeringWorker


class FakeStore:
    """In-memory stand-in mirroring SQLiteEngineeringStore claim semantics."""

    def __init__(self):
        self.tasks: dict[str, EngineeringTask] = {}
        self.attempts = []
        self.checkpoints = []
        self.now = 1000.0
        self.lease_kwargs_seen = []

    def seed(self, task_id, status=TaskStatus.CREATED, lease_expires_at=None):
        task = EngineeringTask(id=task_id, task_description=f"desc-{task_id}")
        task.status = status
        self.tasks[task.id] = task
        if lease_expires_at is not None:
            # Simulate persisted lease metadata via a side channel.
            self._leases = getattr(self, "_leases", {})
            self._leases[task.id] = lease_expires_at
        return task

    def claim_task(self, task_id=None, claimed_by="default-worker", lease_seconds=60.0):
        self.lease_kwargs_seen.append((claimed_by, lease_seconds))
        now = self.now
        candidates = [
            t
            for t in self.tasks.values()
            if t.status == TaskStatus.CREATED
            or (t.status == TaskStatus.RUNNING and getattr(self, "_leases", {}).get(t.id, 0) < now)
        ]
        if task_id is not None:
            candidates = [t for t in candidates if t.id == task_id]
        if not candidates:
            return None
        task = sorted(candidates, key=lambda t: t.created_at)[0]
        task.status = TaskStatus.RUNNING
        return task

    def create_attempt(self, attempt):
        self.attempts.append(attempt)

    def save_checkpoint(self, checkpoint):
        self.checkpoints.append(checkpoint)

    def save_task(self, task):
        self.tasks[task.id] = task


class TestEngineeringWorker(unittest.TestCase):
    def setUp(self):
        self.store = FakeStore()
        self.worker = EngineeringWorker(self.store, "w1")

    def test_success_path_writes_attempt_and_checkpoint(self):
        self.store.seed("t1")
        calls = []

        def handler(task):
            calls.append(task.id)
            return {"ok": True}

        worker = EngineeringWorker(self.store, "w1", handler=handler)
        processed = worker.run(max_tasks=5)

        self.assertEqual(processed, 1)
        self.assertEqual(calls, ["t1"])
        self.assertEqual(len(self.store.attempts), 1)
        self.assertEqual(self.store.attempts[0].status, "SUCCEEDED")
        self.assertEqual(self.store.attempts[0].task_id, "t1")
        self.assertIsNotNone(self.store.attempts[0].completed_at)
        self.assertEqual(len(self.store.checkpoints), 1)
        self.assertEqual(self.store.checkpoints[0].attempt_id, self.store.attempts[0].id)
        self.assertEqual(self.store.tasks["t1"].status, TaskStatus.SUCCEEDED)
        # Lease parameters forwarded to the store claim.
        self.assertIn(("w1", 60.0), self.store.lease_kwargs_seen)

    def test_handler_exception_marks_failed_without_crashing(self):
        self.store.seed("bad")
        self.store.seed("good")

        def handler(task):
            if task.id == "bad":
                raise RuntimeError("boom")
            return {"ok": True}

        worker = EngineeringWorker(self.store, "w1", handler=handler)
        processed = worker.run()

        self.assertEqual(processed, 2)
        failed_attempt = [a for a in self.store.attempts if a.task_id == "bad"][0]
        self.assertEqual(failed_attempt.status, "FAILED")
        good_attempt = [a for a in self.store.attempts if a.task_id == "good"][0]
        self.assertEqual(good_attempt.status, "SUCCEEDED")
        self.assertEqual(self.store.tasks["bad"].status, TaskStatus.FAILED)
        self.assertEqual(self.store.tasks["good"].status, TaskStatus.SUCCEEDED)
        # A failed task produces no checkpoint.
        self.assertTrue(all(c.task_id != "bad" for c in self.store.checkpoints))

    def test_drain_exit_on_empty_queue(self):
        processed = self.worker.run()
        self.assertEqual(processed, 0)
        self.assertEqual(self.store.attempts, [])

    def test_drain_exit_after_processing_all_work(self):
        for i in range(3):
            self.store.seed(f"t{i}")
        processed = self.worker.run()
        self.assertEqual(processed, 3)
        statuses = {tid: t.status for tid, t in self.store.tasks.items()}
        self.assertEqual(statuses, {f"t{i}": TaskStatus.SUCCEEDED for i in range(3)})

    def test_expired_lease_running_task_is_reclaimable(self):
        # RUNNING task whose lease expired before the worker started.
        self.store.seed("stale", status=TaskStatus.RUNNING, lease_expires_at=self.store.now - 10)
        self.worker.run()
        attempt = self.store.attempts[0]
        self.assertEqual(attempt.task_id, "stale")
        self.assertEqual(attempt.status, "SUCCEEDED")
        self.assertEqual(self.store.tasks["stale"].status, TaskStatus.SUCCEEDED)

    def test_unexpired_lease_running_task_is_not_claimed(self):
        self.store.seed("fresh", status=TaskStatus.RUNNING, lease_expires_at=self.store.now + 999)
        processed = self.worker.run()
        self.assertEqual(processed, 0)


if __name__ == "__main__":
    unittest.main()
