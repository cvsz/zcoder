"""Tests for zcoder.agent.memory.cache - MemoryCache LRU cache."""

from __future__ import annotations

import threading

from zcoder.agent.memory.cache import MemoryCache


class TestMemoryCache:
    """Tests for MemoryCache - memory-bounded LRU cache."""

    def test_set_and_get(self):
        cache = MemoryCache(max_size_mb=100)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_none_for_missing_key(self):
        cache = MemoryCache(max_size_mb=100)
        assert cache.get("nonexistent") is None

    def test_overwrite_existing_key(self):
        cache = MemoryCache(max_size_mb=100)
        cache.set("key1", "value1")
        cache.set("key1", "value2")
        assert cache.get("key1") == "value2"
        assert cache.size() == 1

    def test_get_marks_as_recently_used(self):
        """get() moves item to MRU position, so LRU items are evicted first."""
        cache = MemoryCache(max_size_mb=0.000001)  # ~1 byte limit
        cache.set("a", "1")  # 1 byte, fits
        cache.set("b", "2")  # Evicts "a", total would be 2 > 1
        assert cache.get("a") is None  # "a" was LRU, evicted
        assert cache.get("b") == "2"

    def test_eviction_when_memory_limit_exceeded(self):
        cache = MemoryCache(max_size_mb=0.000001)  # ~1 byte limit
        cache.set("small", "hi")  # 2 bytes, fits (cache was empty)
        cache.set("another", "hello world")  # Evicts "small"
        assert cache.get("small") is None
        assert cache.get("another") == "hello world"

    def test_memory_usage_mb(self):
        cache = MemoryCache(max_size_mb=100)
        cache.set("key1", "hello")  # 5 bytes
        usage = cache.memory_usage_mb()
        assert usage >= 0
        assert usage < 0.001  # Should be tiny

    def test_size_returns_count(self):
        cache = MemoryCache(max_size_mb=100)
        assert cache.size() == 0
        cache.set("a", "1")
        cache.set("b", "2")
        assert cache.size() == 2

    def test_clear(self):
        cache = MemoryCache(max_size_mb=100)
        cache.set("a", "1")
        cache.set("b", "2")
        cache.clear()
        assert cache.size() == 0
        assert cache.get("a") is None
        assert cache.get("b") is None
        assert cache.memory_usage_mb() == 0.0

    def test_lru_order_after_get(self):
        """get() marks item as recently used, affecting eviction order."""
        cache = MemoryCache(max_size_mb=0.000001)  # ~1 byte limit
        cache.set("first", "1")
        cache.set("second", "2")  # Evicts "first"
        assert cache.get("first") is None
        assert cache.get("second") == "2"

        # Access "second" to mark it MRU, then add third
        cache.get("second")
        cache.set("third", "3")  # Evicts "second" (only slot)
        assert cache.get("second") is None
        assert cache.get("third") == "3"

    def test_thread_safety(self):
        cache = MemoryCache(max_size_mb=10)
        errors = []

        def worker(thread_id: int):
            try:
                for i in range(100):
                    key = f"t{thread_id}-k{i}"
                    cache.set(key, f"v{i}")
                    val = cache.get(key)
                    assert val == f"v{i}"
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread safety errors: {errors}"

    def test_estimate_size_string(self):
        cache = MemoryCache(max_size_mb=100)
        assert cache._estimate_size("hello") == 5
        assert cache._estimate_size("") == 0

    def test_estimate_size_dict(self):
        cache = MemoryCache(max_size_mb=100)
        d = {"a": "1", "b": "22"}
        assert cache._estimate_size(d) == 5

    def test_estimate_size_list(self):
        cache = MemoryCache(max_size_mb=100)
        lst = ["a", "bb", "ccc"]
        assert cache._estimate_size(lst) == 6

    def test_default_max_size(self):
        cache = MemoryCache()
        assert cache.max_size_bytes == 100 * 1024 * 1024  # 100 MB default
