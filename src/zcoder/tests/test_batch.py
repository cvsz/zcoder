"""Tests for zcoder.agent.orchestration.batch - Batch processor."""

from __future__ import annotations

import asyncio

import pytest

from zcoder.agent.orchestration.batch import BatchProcessor, QueueFullError


class TestBatchProcessor:
    """Tests for BatchProcessor - async batch queue with backpressure."""

    def test_create_default(self):
        bp = BatchProcessor()
        assert bp.max_queue_size == 0
        assert bp.is_empty()
        assert not bp.is_full()
        assert bp.queue_size() == 0

    def test_create_with_max_size(self):
        bp = BatchProcessor(max_queue_size=5)
        assert bp.max_queue_size == 5

    def test_create_negative_max_size_raises(self):
        with pytest.raises(ValueError, match="must be >= 0"):
            BatchProcessor(max_queue_size=-1)

    def test_enqueue_dequeue(self):
        bp = BatchProcessor()
        bp.enqueue("item1")
        bp.enqueue("item2")
        assert bp.queue_size() == 2
        assert bp.dequeue() == "item1"
        assert bp.dequeue() == "item2"
        assert bp.is_empty()

    def test_dequeue_empty_raises(self):
        bp = BatchProcessor()
        with pytest.raises(asyncio.QueueEmpty):
            bp.dequeue()

    def test_enqueue_unlimited_queue(self):
        bp = BatchProcessor(max_queue_size=0)
        for i in range(100):
            bp.enqueue(f"item-{i}")
        assert bp.queue_size() == 100

    def test_enqueue_bounded_queue_full(self):
        bp = BatchProcessor(max_queue_size=2)
        bp.enqueue("a")
        bp.enqueue("b")
        assert bp.is_full()
        with pytest.raises(QueueFullError, match="Queue is full"):
            bp.enqueue("c")

    def test_enqueue_block_false_when_full(self):
        bp = BatchProcessor(max_queue_size=1)
        bp.enqueue("a")
        assert bp.is_full()
        with pytest.raises(QueueFullError):
            bp.enqueue("b", block=False)

    def test_aenqueue_adequeue(self):
        bp = BatchProcessor()

        async def run():
            await bp.aenqueue("async-item")
            assert bp.queue_size() == 1
            item = await bp.adequeue()
            assert item == "async-item"
            assert bp.is_empty()

        asyncio.run(run())

    def test_is_empty_after_dequeue_all(self):
        bp = BatchProcessor()
        bp.enqueue("a")
        bp.enqueue("b")
        bp.dequeue()
        bp.dequeue()
        assert bp.is_empty()
        assert bp.queue_size() == 0

    def test_is_full_at_capacity(self):
        bp = BatchProcessor(max_queue_size=3)
        bp.enqueue("a")
        bp.enqueue("b")
        bp.enqueue("c")
        assert bp.is_full()
        assert not bp.is_empty()

    def test_mixed_types(self):
        bp = BatchProcessor()
        bp.enqueue(42)
        bp.enqueue({"key": "value"})
        bp.enqueue([1, 2, 3])
        assert bp.dequeue() == 42
        assert bp.dequeue() == {"key": "value"}
        assert bp.dequeue() == [1, 2, 3]
