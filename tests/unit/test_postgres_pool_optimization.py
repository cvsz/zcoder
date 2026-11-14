"""tests/unit/test_postgres_pool_optimization.py — Performance tests for PostgreSQL connection pool optimization.

Skips gracefully when no PostgreSQL is reachable (e.g. local development
without Docker).
"""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress

import psycopg2
import pytest

from zcoder.infrastructure.stores.postgres import PostgresControlPlaneStore

# Use the local postgres DSN from the test environment
TEST_DSN = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


def _pg_reachable() -> bool:
    """Return True only when a PostgreSQL instance accepts connections."""
    if not TEST_DSN or not TEST_DSN.startswith("postgresql"):
        return False
    with suppress(psycopg2.OperationalError, psycopg2.Error, OSError):
        with psycopg2.connect(TEST_DSN, connect_timeout=2):
            return True
    return False


pytestmark = pytest.mark.skipif(
    not _pg_reachable(),
    reason="PostgreSQL instance not reachable",
)


@pytest.fixture(scope="session")
def pg_store():
    """Create a store with test DSN."""
    if not _pg_reachable():
        pytest.skip("PostgreSQL instance not reachable")
    store = PostgresControlPlaneStore(dsn=TEST_DSN, min_conn=5, max_conn=20)
    store.init_schema()
    yield store
    store.close()


class TestPoolConfiguration:
    """Tests for configurable connection pool parameters."""

    def test_pool_size_configurable(self):
        """Test that pool_size (min_conn) and max_overflow (max_conn - min_conn) are configurable."""
        if not _pg_reachable():
            pytest.skip("PostgreSQL instance not reachable")
        store = PostgresControlPlaneStore(dsn=TEST_DSN, min_conn=5, max_conn=15)
        # Access internal pool to verify configuration
        pool = store._pool
        assert pool is not None
        # For psycopg2, minconn and maxconn are stored
        if hasattr(pool, "minconn"):
            assert pool.minconn == 5
            assert pool.maxconn == 15
        elif hasattr(pool, "min_size"):  # psycopg3
            assert pool.min_size == 5
            assert pool.max_size == 15
        store.close()

    def test_pool_stats_available(self):
        """Test that pool_stats() method returns pool statistics."""
        if not _pg_reachable():
            pytest.skip("PostgreSQL instance not reachable")
        store = PostgresControlPlaneStore(dsn=TEST_DSN, min_conn=5, max_conn=15)
        stats = store.pool_stats()
        assert "size" in stats
        assert "available" in stats
        assert "in_use" in stats
        assert stats["size"] == 15  # max_conn
        assert stats["available"] >= 0
        assert stats["in_use"] >= 0
        store.close()

    def test_concurrent_claims_no_pool_exhaustion(self, pg_store):
        """Test that concurrent job claims don't exhaust the pool."""
        import time
        import uuid

        from zcoder.domain.models.legacy_job import Job, JobStatus

        # Enqueue enough jobs for all workers with unique IDs
        run_id = uuid.uuid4().hex[:8]
        for i in range(20):
            job = Job(
                id=f"perf_job_{run_id}_{i}",
                task=f"perf.action.{i}",
                runtime="direct",
                status=JobStatus.READY,
                workspace=".",
                created_at=time.time(),
                updated_at=time.time(),
                model="test-model",
                budget_usd=0.0,
                cost_usd=0.0,
                metadata={"i": i},
            )
            pg_store.enqueue_job(job)

        claimed_ids = []

        def claim_one():
            claimed = pg_store.claim_job_with_fencing("perf_worker", lease_duration=60.0)
            if claimed:
                job, _ = claimed
                claimed_ids.append(job.id)

        # Use more workers than min_conn but less than max_conn
        with ThreadPoolExecutor(max_workers=15) as pool:
            futures = [pool.submit(claim_one) for _ in range(15)]
            for f in futures:
                f.result()

        # All 15 workers should have claimed a job
        assert len(claimed_ids) == 15, f"Expected 15 claims, got {len(claimed_ids)}"

    def test_pool_stats_reflect_usage(self, pg_store):
        """Test that pool_stats reflects actual connection usage."""
        initial_stats = pg_store.pool_stats()
        initial_available = initial_stats["available"]

        # Get a connection
        with pg_store._get_conn() as _conn:
            during_stats = pg_store.pool_stats()
            # One connection should be in use
            assert during_stats["in_use"] == initial_stats["in_use"] + 1
            assert during_stats["available"] == initial_available - 1

        # After releasing, should be back to initial
        final_stats = pg_store.pool_stats()
        assert final_stats["available"] == initial_available
        assert final_stats["in_use"] == initial_stats["in_use"]


class TestPoolPerformance:
    """Performance tests for connection pool operations."""

    def test_connection_acquisition_latency(self, pg_store):
        """Test that acquiring a connection is fast (<5ms)."""
        latencies = []
        for _ in range(100):
            start = time.perf_counter()
            with pg_store._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
            elapsed = (time.perf_counter() - start) * 1000
            latencies.append(elapsed)

        avg_latency = sum(latencies) / len(latencies)
        p99_latency = sorted(latencies)[int(len(latencies) * 0.99)]
        assert avg_latency < 5, f"Average connection acquisition too slow: {avg_latency:.2f}ms"
        assert p99_latency < 20, f"P99 connection acquisition too slow: {p99_latency:.2f}ms"

    def test_concurrent_connection_throughput(self, pg_store):
        """Test throughput under concurrent connection acquisition."""

        def acquire_and_query():
            with pg_store._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    return cur.fetchone()

        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=20) as pool:
            futures = [pool.submit(acquire_and_query) for _ in range(200)]
            results = [f.result() for f in futures]
        elapsed = time.perf_counter() - start

        assert len(results) == 200
        assert all(r[0] == 1 for r in results)
        # 200 queries in under 2 seconds
        assert elapsed < 2.0, f"Concurrent throughput too slow: {elapsed:.3f}s for 200 queries"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
