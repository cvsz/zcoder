"""Tests for zcoder.agent.optimization.pooling - Connection pool."""

from __future__ import annotations

import time

from zcoder.agent.optimization.pooling import (
    ConnectionPool,
    PooledConnection,
    PoolMetrics,
    PoolStatus,
    cleanup_pool,
    get_connection,
    get_connection_pool,
    return_connection,
)


class TestPoolStatus:
    """Tests for PoolStatus enum."""

    def test_values(self):
        assert PoolStatus.HEALTHY.value == "healthy"
        assert PoolStatus.DEGRADED.value == "degraded"
        assert PoolStatus.EXHAUSTED.value == "exhausted"
        assert PoolStatus.ERROR.value == "error"


class TestPoolMetrics:
    """Tests for PoolMetrics dataclass."""

    def test_defaults(self):
        m = PoolMetrics()
        assert m.total_connections == 0
        assert m.active_connections == 0
        assert m.idle_connections == 0
        assert m.peak_connections == 0
        assert m.total_requests == 0
        assert m.total_wait_time == 0.0
        assert m.cache_hits == 0
        assert m.cache_misses == 0


class TestPooledConnection:
    """Tests for PooledConnection."""

    def test_creation(self):
        conn = PooledConnection(
            model_id="test-model",
            provider="test-provider",
            connection_string="",
        )
        assert conn.model_id == "test-model"
        assert conn.provider == "test-provider"
        assert conn.connection_string == ""
        assert conn.usage_count == 0
        assert conn.error_count == 0
        assert conn.last_error is None
        assert conn.ttl_seconds is None

    def test_mark_used(self):
        conn = PooledConnection(model_id="m", provider="p", connection_string="")
        before = time.time()
        conn.mark_used()
        assert conn.usage_count == 1
        assert conn.last_used >= before

    def test_is_stale_no_ttl(self):
        conn = PooledConnection(model_id="m", provider="p", connection_string="")
        assert conn.is_stale() is False

    def test_is_stale_with_ttl(self):
        conn = PooledConnection(model_id="m", provider="p", connection_string="", ttl_seconds=1)
        assert conn.is_stale() is False
        time.sleep(1.1)
        assert conn.is_stale() is True

    def test_record_error(self):
        conn = PooledConnection(model_id="m", provider="p", connection_string="")
        conn.record_error("timeout")
        assert conn.error_count == 1
        assert conn.last_error == "timeout"

    def test_get_metrics(self):
        conn = PooledConnection(model_id="m", provider="p", connection_string="", usage_count=5)
        metrics = conn.get_metrics()
        assert metrics.total_connections == 1
        assert metrics.active_connections == 1
        assert metrics.idle_connections == 0
        assert metrics.total_requests == 5


class TestConnectionPool:
    """Tests for ConnectionPool."""

    def test_create_pool_defaults(self):
        pool = ConnectionPool()
        assert pool.max_size == 10
        assert pool.ttl_seconds is None
        assert pool.max_usage_per_connection is None
        assert pool.geo_constraint is None

    def test_get_connection_creates_new(self):
        pool = ConnectionPool()
        conn = pool.get_connection("anthropic", "claude-3")
        assert conn is not None
        assert conn.provider == "anthropic"
        assert conn.model_id == "claude-3"
        # New connections are not marked as used (mark_used only on cache hit)
        assert conn.usage_count == 0

    def test_get_connection_returns_cached(self):
        pool = ConnectionPool()
        conn1 = pool.get_connection("anthropic", "claude-3")
        conn2 = pool.get_connection("anthropic", "claude-3")
        assert conn1 is conn2  # Same connection returned from pool
        metrics = pool.get_metrics()
        assert metrics.cache_hits >= 1

    def test_force_new_connection(self):
        pool = ConnectionPool()
        conn1 = pool.get_connection("anthropic", "claude-3")
        conn2 = pool.get_connection("anthropic", "claude-3", force_new=True)
        assert conn1 is not conn2  # Different connections

    def test_different_providers_separate_pools(self):
        pool = ConnectionPool()
        conn_a = pool.get_connection("anthropic", "claude-3")
        conn_o = pool.get_connection("openai", "gpt-4")
        assert conn_a.provider == "anthropic"
        assert conn_o.provider == "openai"

    def test_max_size_eviction(self):
        pool = ConnectionPool(max_size=2)
        pool.get_connection("anthropic", "model-a")
        pool.get_connection("anthropic", "model-b")
        pool.get_connection("anthropic", "model-c")  # Should evict oldest
        metrics = pool.get_metrics()
        assert metrics.peak_connections <= 2

    def test_release_connection_no_op(self):
        pool = ConnectionPool()
        conn = pool.get_connection("anthropic", "claude-3")
        pool.release_connection(conn)  # Should not raise

    def test_return_connection_moves_to_end(self):
        pool = ConnectionPool()
        conn = pool.get_connection("anthropic", "claude-3")
        pool.return_connection(conn)  # Should not raise

    def test_cleanup_removes_stale(self):
        pool = ConnectionPool(ttl_seconds=0)  # Immediately stale
        pool.get_connection("anthropic", "claude-3")
        time.sleep(0.01)
        pool.cleanup()
        # Connection should be cleaned up since ttl=0 means immediately stale
        metrics = pool.get_metrics()
        assert metrics.total_connections == 0

    def test_global_pool_singleton(self):
        pool1 = get_connection_pool()
        pool2 = get_connection_pool()
        assert pool1 is pool2

    def test_global_get_connection(self):
        conn = get_connection("anthropic", "claude-3")
        assert conn is not None
        assert conn.provider == "anthropic"

    def test_global_return_connection(self):
        conn = get_connection("anthropic", "claude-3")
        return_connection(conn)  # Should not raise

    def test_global_cleanup_pool(self):
        cleanup_pool()  # Should not raise even if no pool exists
        pool = get_connection_pool()
        assert pool is not None
