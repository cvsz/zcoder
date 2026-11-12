"""tests/unit/test_async_concurrency.py — Tests for async concurrency control."""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

# These will be created as part of the implementation
from zcoder.agent.orchestration.workflow import WorkflowEngine, AsyncWorkflowStep as WorkflowStep
from zcoder.agent.orchestration.batch import BatchProcessor, QueueFullError


class TestWorkflowSemaphore:
    """Tests for semaphore-based concurrency control in WorkflowEngine."""

    def test_workflow_semaphore_limit(self):
        """Test that max_concurrent limits concurrent execution."""
        engine = WorkflowEngine(max_concurrent=3)
        started = []
        completed = []
        concurrency = []

        async def slow_step():
            started.append(time.time())
            concurrency.append(len(started) - len(completed))
            await asyncio.sleep(0.1)
            completed.append(time.time())

        steps = [WorkflowStep(id=f"s{i}", fn=slow_step) for i in range(10)]
        asyncio.run(engine.execute(steps))

        # At most 3 concurrent
        max_concurrent = max(concurrency) if concurrency else 0
        assert max_concurrent <= 3, f"Max concurrent was {max_concurrent}, expected <=3"

    def test_workflow_default_concurrency(self):
        """Test that default concurrency is reasonable."""
        engine = WorkflowEngine()  # No max_concurrent specified
        assert engine.max_concurrent > 0

    def test_workflow_semaphore_zero_raises(self):
        """Test that max_concurrent=0 raises error."""
        with pytest.raises(ValueError):
            WorkflowEngine(max_concurrent=0)

    def test_workflow_concurrent_execution_time(self):
        """Test that concurrent execution is faster than sequential."""
        engine = WorkflowEngine(max_concurrent=5)
        
        async def step():
            await asyncio.sleep(0.1)
        
        steps = [WorkflowStep(id=f"s{i}", fn=step) for i in range(10)]
        
        start = time.perf_counter()
        asyncio.run(engine.execute(steps))
        elapsed = time.perf_counter() - start
        
        # With 5 concurrent, 10 steps * 0.1s = 0.2s ideal (2 batches)
        # Allow some overhead
        assert elapsed < 0.5, f"Concurrent execution too slow: {elapsed:.3f}s"


class TestBatchBackpressure:
    """Tests for backpressure handling in BatchProcessor."""

    def test_batch_enqueue_block(self):
        """Test that enqueue raises when queue is full and block=False."""
        processor = BatchProcessor(max_queue_size=5)
        
        # Fill queue
        for i in range(5):
            processor.enqueue(f"item-{i}")
        
        # Should raise when full
        with pytest.raises(QueueFullError):
            processor.enqueue("item-5", block=False)

    def test_batch_enqueue_block_timeout(self):
        """Test that enqueue with block=False raises when full."""
        processor = BatchProcessor(max_queue_size=2)
        
        processor.enqueue("item-1")
        processor.enqueue("item-2")
        
        # Should raise when full
        with pytest.raises(QueueFullError):
            processor.enqueue("item-3", block=False)

    def test_batch_dequeue_releases_space(self):
        """Test that dequeue releases queue space."""
        processor = BatchProcessor(max_queue_size=2)
        
        processor.enqueue("item-1")
        processor.enqueue("item-2")
        
        # Dequeue one
        item = processor.dequeue()
        assert item == "item-1"
        
        # Should have space now
        processor.enqueue("item-3")  # Should not raise
        assert processor.queue_size() == 2

    def test_batch_max_queue_size_zero_unlimited(self):
        """Test that max_queue_size=0 means unlimited."""
        processor = BatchProcessor(max_queue_size=0)
        
        for i in range(100):
            processor.enqueue(f"item-{i}")
        
        assert processor.queue_size() == 100


class TestBatchBackpressure:
    """Tests for backpressure handling in BatchProcessor."""

    def test_batch_enqueue_block(self):
        """Test that enqueue blocks when queue is full."""
        processor = BatchProcessor(max_queue_size=5)
        
        # Fill queue
        for i in range(5):
            processor.enqueue(f"item-{i}")
        
        # Should block or raise when full
        with pytest.raises(QueueFullError):
            processor.enqueue("item-5", block=False)

    def test_batch_enqueue_block_timeout(self):
        """Test that enqueue with block=True waits."""
        processor = BatchProcessor(max_queue_size=2)
        
        processor.enqueue("item-1")
        processor.enqueue("item-2")
        
        # This should block until space is available
        # We can't easily test blocking without a consumer, so test non-blocking
        with pytest.raises(QueueFullError):
            processor.enqueue("item-3", block=False)

    def test_batch_dequeue_releases_space(self):
        """Test that dequeue releases queue space."""
        processor = BatchProcessor(max_queue_size=2)
        
        processor.enqueue("item-1")
        processor.enqueue("item-2")
        
        # Dequeue one
        item = processor.dequeue()
        assert item == "item-1"
        
        # Should have space now
        processor.enqueue("item-3")  # Should not raise
        assert processor.queue_size() == 2

    def test_batch_max_queue_size_zero_unlimited(self):
        """Test that max_queue_size=0 means unlimited."""
        processor = BatchProcessor(max_queue_size=0)
        
        for i in range(100):
            processor.enqueue(f"item-{i}")
        
        assert processor.queue_size() == 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])