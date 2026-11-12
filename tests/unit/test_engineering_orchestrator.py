"""Tests for EngineeringOrchestrator service."""

from __future__ import annotations

from zcoder.domain.interfaces.engineering_store import EngineeringStore
from zcoder.domain.models.engineering import Attempt, Checkpoint, EngineeringTask, TaskStatus
from zcoder.services.engineering_orchestrator import EngineeringOrchestrator


class FakeEngineeringStore(EngineeringStore):
    """Fake in-memory implementation of EngineeringStore for testing."""

    def __init__(self) -> None:
        self.tasks: dict[str, EngineeringTask] = {}
        self.attempts: dict[str, list[Attempt]] = {}
        self.checkpoints: dict[str, Checkpoint] = {}

    def save_task(self, task: EngineeringTask) -> None:
        self.tasks[task.id] = task

    def get_task(self, task_id: str) -> EngineeringTask | None:
        return self.tasks.get(task_id)

    def claim_task(self) -> EngineeringTask | None:
        for task in self.tasks.values():
            if task.status == TaskStatus.CREATED:
                task.status = TaskStatus.RUNNING
                return task
        return None

    def create_attempt(self, attempt: Attempt) -> None:
        self.attempts.setdefault(attempt.task_id, []).append(attempt)

    def get_attempts(self, task_id: str) -> list[Attempt]:
        return self.attempts.get(task_id, [])

    def save_checkpoint(self, checkpoint: Checkpoint) -> None:
        self.checkpoints[checkpoint.attempt_id] = checkpoint

    def get_latest_checkpoint(self, attempt_id: str) -> Checkpoint | None:
        return self.checkpoints.get(attempt_id)

    def list_tasks(self, status: str | None = None) -> list[EngineeringTask]:
        if status is None:
            return list(self.tasks.values())
        return [t for t in self.tasks.values() if t.status == status]


class TestEngineeringOrchestrator:
    """Tests for EngineeringOrchestrator."""

    def test_create_task_persists_and_returns_task(self) -> None:
        store = FakeEngineeringStore()
        orchestrator = EngineeringOrchestrator(store)

        task = orchestrator.create_task("Build a REST API")

        assert task.task_description == "Build a REST API"
        assert task.status == TaskStatus.CREATED
        assert task.id in store.tasks
        assert store.tasks[task.id] is task

    def test_create_task_generates_unique_ids(self) -> None:
        store = FakeEngineeringStore()
        orchestrator = EngineeringOrchestrator(store)

        task1 = orchestrator.create_task("Task 1")
        task2 = orchestrator.create_task("Task 2")

        assert task1.id != task2.id
        assert len(store.tasks) == 2

    def test_start_task_returns_attempt_and_updates_status(self) -> None:
        store = FakeEngineeringStore()
        orchestrator = EngineeringOrchestrator(store)

        task = orchestrator.create_task("Test task")
        attempt = orchestrator.start_task(task.id)

        assert attempt is not None
        assert attempt.task_id == task.id
        assert task.status == TaskStatus.RUNNING
        assert store.tasks[task.id].status == TaskStatus.RUNNING
        assert len(store.attempts[task.id]) == 1
        assert store.attempts[task.id][0] is attempt

    def test_start_task_returns_none_for_nonexistent_task(self) -> None:
        store = FakeEngineeringStore()
        orchestrator = EngineeringOrchestrator(store)

        attempt = orchestrator.start_task("nonexistent-id")

        assert attempt is None

    def test_start_task_idempotent_on_already_running(self) -> None:
        store = FakeEngineeringStore()
        orchestrator = EngineeringOrchestrator(store)

        task = orchestrator.create_task("Test task")
        attempt1 = orchestrator.start_task(task.id)
        attempt2 = orchestrator.start_task(task.id)

        # Both calls should succeed and return attempts
        assert attempt1 is not None
        assert attempt2 is not None
        assert attempt1.task_id == attempt2.task_id
        # Status should remain RUNNING
        assert task.status == TaskStatus.RUNNING

    def test_update_task_status_changes_status(self) -> None:
        store = FakeEngineeringStore()
        orchestrator = EngineeringOrchestrator(store)

        task = orchestrator.create_task("Test task")
        orchestrator.start_task(task.id)
        orchestrator.update_task_status(task.id, TaskStatus.SUCCEEDED)

        assert task.status == TaskStatus.SUCCEEDED
        assert store.tasks[task.id].status == TaskStatus.SUCCEEDED

    def test_update_task_status_noop_for_nonexistent_task(self) -> None:
        store = FakeEngineeringStore()
        orchestrator = EngineeringOrchestrator(store)

        # Should not raise
        orchestrator.update_task_status("nonexistent-id", TaskStatus.SUCCEEDED)

    def test_update_task_status_all_statuses(self) -> None:
        store = FakeEngineeringStore()
        orchestrator = EngineeringOrchestrator(store)

        task = orchestrator.create_task("Test task")
        orchestrator.start_task(task.id)

        for status in TaskStatus:
            orchestrator.update_task_status(task.id, status)
            assert task.status == status
            assert store.tasks[task.id].status == status

    def test_multiple_tasks_independent(self) -> None:
        store = FakeEngineeringStore()
        orchestrator = EngineeringOrchestrator(store)

        task1 = orchestrator.create_task("Task 1")
        task2 = orchestrator.create_task("Task 2")

        orchestrator.start_task(task1.id)
        orchestrator.update_task_status(task1.id, TaskStatus.SUCCEEDED)

        # Task 2 should be unaffected
        assert store.tasks[task1.id].status == TaskStatus.SUCCEEDED
        assert store.tasks[task2.id].status == TaskStatus.CREATED

        orchestrator.start_task(task2.id)
        orchestrator.update_task_status(task2.id, TaskStatus.FAILED)

        assert store.tasks[task1.id].status == TaskStatus.SUCCEEDED
        assert store.tasks[task2.id].status == TaskStatus.FAILED

    def test_attempt_creation_records_multiple_attempts(self) -> None:
        store = FakeEngineeringStore()
        orchestrator = EngineeringOrchestrator(store)

        task = orchestrator.create_task("Test task")
        orchestrator.start_task(task.id)
        orchestrator.update_task_status(task.id, TaskStatus.FAILED)

        # Start again (simulating retry)
        orchestrator.start_task(task.id)

        attempts = store.get_attempts(task.id)
        assert len(attempts) == 2
        assert attempts[0].task_id == task.id
        assert attempts[1].task_id == task.id
        assert attempts[0] is not attempts[1]
