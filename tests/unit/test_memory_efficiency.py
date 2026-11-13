"""tests/unit/test_memory_efficiency.py — Tests for memory-efficient data structures."""

from __future__ import annotations

import pytest

from zcoder.agent.memory.cache import MemoryCache
from zcoder.domain.models.engineering import Attempt, Checkpoint, EngineeringTask, TaskStatus


class TestDataclassSlots:
    """Tests for __slots__ optimization on dataclasses."""

    def test_engineering_task_has_slots(self):
        """Test that EngineeringTask has __slots__ and no __dict__."""
        task = EngineeringTask(
            id="t1",
            task_description="test",
            status=TaskStatus.CREATED,
            created_at=0,
            updated_at=0,
            metadata={},
        )
        # With __slots__, no __dict__ attribute
        assert not hasattr(task, "__dict__"), "EngineeringTask should not have __dict__"
        assert hasattr(EngineeringTask, "__slots__"), "EngineeringTask should have __slots__"

    def test_attempt_has_slots(self):
        """Test that Attempt has __slots__."""
        attempt = Attempt(
            id="a1", task_id="t1", generation=1, status="PENDING", started_at=0, completed_at=None
        )
        assert not hasattr(attempt, "__dict__"), "Attempt should not have __dict__"
        assert hasattr(Attempt, "__slots__"), "Attempt should have __slots__"

    def test_checkpoint_has_slots(self):
        """Test that Checkpoint has __slots__."""
        checkpoint = Checkpoint(
            id="c1",
            task_id="t1",
            attempt_id="a1",
            sequence=1,
            phase="analysis",
            state_snapshot={"step": "done"},
            timestamp=0,
        )
        assert not hasattr(checkpoint, "__dict__"), "Checkpoint should not have __dict__"
        assert hasattr(Checkpoint, "__slots__"), "Checkpoint should have __slots__"

    def test_slots_prevent_arbitrary_attributes(self):
        """Test that __slots__ prevents setting arbitrary attributes."""
        task = EngineeringTask(
            id="t1",
            task_description="test",
            status=TaskStatus.CREATED,
            created_at=0,
            updated_at=0,
            metadata={},
        )
        with pytest.raises(AttributeError):
            task.arbitrary_attr = "not allowed"


class TestMemoryBoundedCache:
    """Tests for memory-bounded cache."""

    def test_cache_memory_bounded(self):
        """Test that cache evicts when memory limit exceeded."""
        cache = MemoryCache(max_size_mb=1)  # 1MB limit

        # Add items that exceed 1MB
        # Each item ~200KB, so 10 items = 2MB
        for i in range(10):
            cache.set(f"key-{i}", "x" * 200000)  # ~200KB each

        # Should evict to stay under limit (with some overhead)
        assert cache.memory_usage_mb() <= 2, f"Cache memory usage {cache.memory_usage_mb()}MB exceeds limit"

    def test_cache_lru_eviction(self):
        """Test that cache uses LRU eviction."""
        cache = MemoryCache(max_size_mb=1)  # 1MB limit

        # Fill cache with ~100KB items
        for i in range(10):
            cache.set(f"key-{i}", "x" * 100000)  # ~100KB each

        # Access first few to make them recently used
        cache.get("key-0")
        cache.get("key-1")

        # Add more to trigger eviction (need > 1MB total)
        # 10 existing * 100KB = 1MB, adding 5 more = 1.5MB > limit
        for i in range(10, 15):
            cache.set(f"key-{i}", "x" * 100000)

        # Recently accessed should still be there
        assert cache.get("key-0") is not None
        assert cache.get("key-1") is not None

        # Older unused should be evicted (at least some)
        evicted = sum(1 for i in range(2, 10) if cache.get(f"key-{i}") is None)
        assert evicted > 0, "No items were evicted despite exceeding memory limit"

    def test_cache_memory_usage_tracking(self):
        """Test that cache tracks memory usage accurately."""
        cache = MemoryCache(max_size_mb=10)

        initial_usage = cache.memory_usage_mb()
        cache.set("key1", "x" * 1000000)  # ~1MB
        after_usage = cache.memory_usage_mb()

        assert after_usage > initial_usage
        assert after_usage - initial_usage >= 0.9  # At least ~1MB


class TestObjectPool:
    """Tests for object pooling."""

    def test_checkpoint_pool_reuse(self):
        """Test that CheckpointPool reuses objects."""
        from zcoder.domain.models.engineering import CheckpointPool

        pool = CheckpointPool(initial_size=2)
        # Acquire all initial objects
        chk1 = pool.acquire()
        chk2 = pool.acquire()

        # Modify chk1
        chk1.id = "test-1"
        chk1.task_id = "task-1"
        chk1.attempt_id = "attempt-1"
        chk1.sequence = 1
        chk1.phase = "test"
        chk1.state_snapshot = {"data": "test"}
        chk1.timestamp = 12345

        # Release chk1
        pool.release(chk1)

        # Acquire again - should get chk1 back (or chk2, but one of the reused objects)
        chk3 = pool.acquire()
        # Should be one of the previously acquired objects
        assert chk3 is chk1 or chk3 is chk2

        # Release all
        pool.release(chk2)
        pool.release(chk3)

        # Acquire again - should reuse
        chk4 = pool.acquire()
        assert chk4 is chk1 or chk4 is chk2 or chk4 is chk3

    def test_pool_exhaustion_creates_new(self):
        """Test that pool creates new objects when exhausted."""
        from zcoder.domain.models.engineering import CheckpointPool

        pool = CheckpointPool(initial_size=2)
        # Acquire more than initial pool size
        objects = [pool.acquire() for _ in range(5)]

        # All should be unique objects
        assert len(set(id(obj) for obj in objects)) == 5

        # Release all
        for obj in objects:
            pool.release(obj)

        # Re-acquire should reuse
        objects2 = [pool.acquire() for _ in range(5)]
        # Should reuse some objects
        reused = sum(1 for o1, o2 in zip(objects, objects2, strict=True) if o1 is o2)
        assert reused > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
