"""Tests for zcoder.agent.orchestration.distributed - Distributed processing."""

from __future__ import annotations

import pytest

from zcoder.agent.orchestration.distributed import (
    CapabilityAwareLoadBalancer,
    DistributedProcessor,
    DistributedQueue,
    DistributedTask,
    LeastLoadedLoadBalancer,
    RoundRobinLoadBalancer,
    TaskPriority,
    TaskStatus,
    WorkerNode,
    WorkerStatus,
    create_distributed_processor,
)


class TestTaskStatus:
    """Tests for TaskStatus enum."""

    def test_values(self):
        assert TaskStatus.QUEUED == "queued"
        assert TaskStatus.ASSIGNED == "assigned"
        assert TaskStatus.RUNNING == "running"
        assert TaskStatus.COMPLETED == "completed"
        assert TaskStatus.FAILED == "failed"
        assert TaskStatus.RETRYING == "retrying"
        assert TaskStatus.CANCELLED == "cancelled"


class TestTaskPriority:
    """Tests for TaskPriority enum."""

    def test_values(self):
        assert TaskPriority.LOW == "low"
        assert TaskPriority.NORMAL == "normal"
        assert TaskPriority.HIGH == "high"
        assert TaskPriority.CRITICAL == "critical"


class TestWorkerStatus:
    """Tests for WorkerStatus enum."""

    def test_values(self):
        assert WorkerStatus.IDLE == "idle"
        assert WorkerStatus.BUSY == "busy"
        assert WorkerStatus.DRAINING == "draining"
        assert WorkerStatus.OFFLINE == "offline"
        assert WorkerStatus.ERROR == "error"


class TestDistributedTask:
    """Tests for DistributedTask dataclass."""

    def test_creation(self):
        task = DistributedTask(
            id="task_1",
            name="Process data",
            payload={"key": "value"},
        )
        assert task.id == "task_1"
        assert task.name == "Process data"
        assert task.payload == {"key": "value"}
        assert task.priority == TaskPriority.NORMAL
        assert task.max_retries == 3
        assert task.retry_count == 0
        assert task.depends_on == []
        assert task.status == TaskStatus.QUEUED
        assert task.assigned_worker is None
        assert task.result is None
        assert task.error is None
        assert task.created_at > 0
        assert task.timeout == 60.0

    def test_creation_full(self):
        task = DistributedTask(
            id="task_2",
            name="Complex task",
            payload={"data": [1, 2, 3]},
            priority=TaskPriority.CRITICAL,
            max_retries=5,
            depends_on=["task_0"],
            timeout=120.0,
        )
        assert task.priority == TaskPriority.CRITICAL
        assert task.max_retries == 5
        assert task.depends_on == ["task_0"]
        assert task.timeout == 120.0

    def test_lt_ordering(self):
        """Test that higher priority tasks sort first."""
        low = DistributedTask(id="low", name="Low", payload={}, priority=TaskPriority.LOW)
        high = DistributedTask(id="high", name="High", payload={}, priority=TaskPriority.HIGH)
        critical = DistributedTask(id="crit", name="Critical", payload={}, priority=TaskPriority.CRITICAL)

        # Critical should come before high, which should come before low
        assert critical < high
        assert high < low
        assert not (low < critical)


class TestWorkerNode:
    """Tests for WorkerNode dataclass."""

    def test_creation(self):
        worker = WorkerNode(
            id="worker_1",
            host="worker-1.internal",
            port=8080,
        )
        assert worker.id == "worker_1"
        assert worker.host == "worker-1.internal"
        assert worker.port == 8080
        assert worker.status == WorkerStatus.IDLE
        assert worker.capabilities == []
        assert worker.max_concurrent_tasks == 5
        assert worker.current_tasks == 0
        assert worker.completed_tasks == 0
        assert worker.failed_tasks == 0
        assert worker.last_heartbeat > 0
        assert worker.total_processing_time == 0.0

    def test_is_available(self):
        worker = WorkerNode(id="w1", host="h1", port=8080)
        assert worker.is_available is True

        worker.current_tasks = worker.max_concurrent_tasks
        assert worker.is_available is False

        worker.status = WorkerStatus.BUSY
        assert worker.is_available is False

    def test_utilization(self):
        worker = WorkerNode(id="w1", host="h1", port=8080, max_concurrent_tasks=10)
        assert worker.utilization == 0.0

        worker.current_tasks = 5
        assert worker.utilization == 0.5

        worker.current_tasks = 10
        assert worker.utilization == 1.0

    def test_heartbeat(self):
        worker = WorkerNode(id="w1", host="h1", port=8080)
        before = worker.last_heartbeat
        worker.heartbeat()
        assert worker.last_heartbeat > before

    def test_is_alive(self):
        worker = WorkerNode(id="w1", host="h1", port=8080)
        assert worker.is_alive() is True

        worker.last_heartbeat = 0
        assert worker.is_alive(timeout=30.0) is False


class TestLoadBalancer:
    """Tests for LoadBalancer implementations."""

    def test_round_robin(self):
        lb = RoundRobinLoadBalancer()
        workers = [
            WorkerNode(id="w1", host="h1", port=8080),
            WorkerNode(id="w2", host="h2", port=8081),
            WorkerNode(id="w3", host="h3", port=8082),
        ]
        task = DistributedTask(id="t1", name="Task", payload={})

        # First selection should be w1
        decision = lb.select_worker(workers, task)
        assert decision is not None
        assert decision.worker_id == "w1"

        # Second should be w2
        decision = lb.select_worker(workers, task)
        assert decision.worker_id == "w2"

        # Third should be w3
        decision = lb.select_worker(workers, task)
        assert decision.worker_id == "w3"

        # Fourth should wrap around to w1
        decision = lb.select_worker(workers, task)
        assert decision.worker_id == "w1"

    def test_least_loaded(self):
        lb = LeastLoadedLoadBalancer()
        w1 = WorkerNode(id="w1", host="h1", port=8080, max_concurrent_tasks=10)
        w2 = WorkerNode(id="w2", host="h2", port=8081, max_concurrent_tasks=10)
        w3 = WorkerNode(id="w3", host="h3", port=8082, max_concurrent_tasks=10)
        workers = [w1, w2, w3]
        task = DistributedTask(id="t1", name="Task", payload={})

        # All idle, first one should be selected (lowest utilization = 0, first one wins)
        decision = lb.select_worker(workers, task)
        assert decision.worker_id == "w1"

        # Make w1 busy
        w1.current_tasks = 5
        decision = lb.select_worker(workers, task)
        assert decision.worker_id == "w2"  # w2 has 0/10 utilization

    def test_capability_aware(self):
        lb = CapabilityAwareLoadBalancer()
        w1 = WorkerNode(id="w1", host="h1", port=8080, capabilities=["python"])
        w2 = WorkerNode(id="w2", host="h2", port=8081, capabilities=["javascript"])
        workers = [w1, w2]
        task = DistributedTask(
            id="t1",
            name="Task",
            payload={"required_capability": "python"},
        )

        decision = lb.select_worker(workers, task)
        assert decision.worker_id == "w1"

    def test_no_available_workers(self):
        lb = LeastLoadedLoadBalancer()
        w1 = WorkerNode(id="w1", host="h1", port=8080, max_concurrent_tasks=1)
        w1.current_tasks = 1  # Full
        workers = [w1]
        task = DistributedTask(id="t1", name="Task", payload={})

        decision = lb.select_worker(workers, task)
        assert decision is None


class TestDistributedQueue:
    """Tests for DistributedQueue."""

    @pytest.fixture
    def queue(self):
        return DistributedQueue(max_size=10)

    def test_creation(self):
        queue = DistributedQueue(max_size=5)
        assert queue.max_size == 5
        assert queue.size() == 0
        assert queue.is_full() is False

    @pytest.mark.asyncio
    async def test_enqueue_dequeue(self, queue):
        task = DistributedTask(id="t1", name="Task", payload={})
        result = await queue.enqueue(task)
        assert result is True
        assert queue.size() == 1
        assert queue.is_full() is False

        dequeued = await queue.dequeue()
        assert dequeued is not None
        assert dequeued.id == "t1"
        assert queue.size() == 0

    @pytest.mark.asyncio
    async def test_queue_full(self, queue):
        # Fill the queue
        for i in range(10):
            task = DistributedTask(id=f"t{i}", name=f"Task {i}", payload={})
            await queue.enqueue(task)

        assert queue.is_full() is True

        # Try to add one more
        task = DistributedTask(id="t10", name="Task 10", payload={})
        result = await queue.enqueue(task)
        assert result is False

    @pytest.mark.asyncio
    async def test_priority_ordering(self, queue):
        # Add tasks with different priorities
        low = DistributedTask(id="low", name="Low", payload={}, priority=TaskPriority.LOW)
        high = DistributedTask(id="high", name="High", payload={}, priority=TaskPriority.HIGH)
        critical = DistributedTask(id="crit", name="Critical", payload={}, priority=TaskPriority.CRITICAL)
        normal = DistributedTask(id="norm", name="Normal", payload={}, priority=TaskPriority.NORMAL)

        await queue.enqueue(low)
        await queue.enqueue(high)
        await queue.enqueue(critical)
        await queue.enqueue(normal)

        # Dequeue should return in priority order: critical, high, normal, low
        first = await queue.dequeue()
        assert first.id == "crit"
        second = await queue.dequeue()
        assert second.id == "high"
        third = await queue.dequeue()
        assert third.id == "norm"
        fourth = await queue.dequeue()
        assert fourth.id == "low"

    @pytest.mark.asyncio
    async def test_get_task(self, queue):
        task = DistributedTask(id="t1", name="Task", payload={})
        await queue.enqueue(task)

        found = queue.get_task("t1")
        assert found is not None
        assert found.id == "t1"

        not_found = queue.get_task("t999")
        assert not_found is None

    @pytest.mark.asyncio
    async def test_remove_task(self, queue):
        task = DistributedTask(id="t1", name="Task", payload={})
        await queue.enqueue(task)

        result = queue.remove_task("t1")
        assert result is True
        assert queue.size() == 0
        assert queue.get_task("t1") is None

        result = queue.remove_task("t999")
        assert result is False


class TestDistributedProcessor:
    """Tests for DistributedProcessor."""

    @pytest.fixture
    def processor(self):
        return DistributedProcessor()

    def test_creation(self):
        processor = DistributedProcessor()
        assert processor.max_concurrent_tasks == 10
        assert processor.task_timeout == 60.0
        assert processor.heartbeat_timeout == 30.0
        assert processor.queue.size() == 0
        assert len(processor.workers) == 0

    def test_register_worker(self, processor):
        worker = WorkerNode(id="w1", host="h1", port=8080)
        processor.register_worker(worker)
        assert "w1" in processor.workers
        assert processor.get_worker("w1") is worker

    def test_get_available_workers(self, processor):
        w1 = WorkerNode(id="w1", host="h1", port=8080)
        w2 = WorkerNode(id="w2", host="h2", port=8081)
        w3 = WorkerNode(id="w3", host="h3", port=8082, max_concurrent_tasks=0)  # Not available
        processor.register_worker(w1)
        processor.register_worker(w2)
        processor.register_worker(w3)

        available = processor.get_available_workers()
        assert len(available) == 2
        assert w1 in available
        assert w2 in available
        assert w3 not in available

    @pytest.mark.asyncio
    async def test_process_task(self, processor):
        worker = WorkerNode(id="w1", host="h1", port=8080)
        processor.register_worker(worker)

        task = DistributedTask(id="t1", name="Test task", payload={})
        result = await processor._process_task(task)

        assert result.task_id == "t1"
        assert result.worker_id == "w1"
        assert result.status == TaskStatus.COMPLETED
        assert result.error is None
        assert result.duration > 0

    @pytest.mark.asyncio
    async def test_process_queue(self, processor):
        w1 = WorkerNode(id="w1", host="h1", port=8080)
        w2 = WorkerNode(id="w2", host="h2", port=8081)
        processor.register_worker(w1)
        processor.register_worker(w2)

        await processor.queue.enqueue(DistributedTask(id="t1", name="Task 1", payload={}))
        await processor.queue.enqueue(DistributedTask(id="t2", name="Task 2", payload={}))

        results = await processor.process_queue()
        assert len(results) == 2
        assert all(r.status == TaskStatus.COMPLETED for r in results)

    @pytest.mark.asyncio
    async def test_process_with_dependencies(self, processor):
        processor.register_worker(WorkerNode(id="w1", host="h1", port=8080))

        task1 = DistributedTask(id="t1", name="Task 1", payload={})
        task2 = DistributedTask(id="t2", name="Task 2", payload={}, depends_on=["t1"])

        await processor.queue.enqueue(task2)  # Add dependent first
        await processor.queue.enqueue(task1)  # Then dependency

        results = await processor.process_queue()
        assert len(results) == 2
        assert all(r.status == TaskStatus.COMPLETED for r in results)

    def test_get_processor_metrics(self, processor):
        processor.register_worker(WorkerNode(id="w1", host="h1", port=8080))
        processor.register_worker(WorkerNode(id="w2", host="h2", port=8081))

        metrics = processor.get_processor_metrics()
        assert metrics["total_workers"] == 2
        assert metrics["active_workers"] == 2
        assert metrics["total_tasks_processed"] == 0
        assert metrics["queue_size"] == 0


class TestCreateDistributedProcessor:
    """Tests for create_distributed_processor factory function."""

    @pytest.mark.asyncio
    async def test_create_default(self):
        processor = await create_distributed_processor(num_workers=3)
        assert len(processor.workers) == 3
        assert processor.max_concurrent_tasks == 10

    @pytest.mark.asyncio
    async def test_create_custom(self):
        processor = await create_distributed_processor(
            num_workers=2,
            load_balancer_strategy="round_robin",
            max_concurrent_tasks=5,
        )
        assert len(processor.workers) == 2
        assert processor.max_concurrent_tasks == 5
        assert isinstance(processor.load_balancer, RoundRobinLoadBalancer)

    @pytest.mark.asyncio
    async def test_create_capability_aware(self):
        processor = await create_distributed_processor(
            num_workers=2,
            load_balancer_strategy="capability_aware",
        )
        assert isinstance(processor.load_balancer, CapabilityAwareLoadBalancer)


class TestProcessAndCollect:
    """Integration tests for process and collect results."""

    @pytest.mark.asyncio
    async def test_process_and_collect(self):
        processor = await create_distributed_processor(num_workers=2)

        await processor.queue.enqueue(DistributedTask(id="t1", name="Task 1", payload={}))
        await processor.queue.enqueue(DistributedTask(id="t2", name="Task 2", payload={}))

        results = await processor.process_queue()
        assert len(results) == 2
        assert all(r.status == TaskStatus.COMPLETED for r in results)
        assert results[0].worker_id is not None
        assert results[1].worker_id is not None
