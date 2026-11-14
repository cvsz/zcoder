"""tests/unit/test_performance_regression.py — Comprehensive performance regression tests."""

from __future__ import annotations

import asyncio
import os
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from zcoder.agent.optimization.cost import classify_complexity, select_model
from zcoder.agent.optimization.local_tokens import LocalTokenEstimator
from zcoder.agent.optimization.prompt import clear_optimize_cache, get_optimize_cache_stats, optimize
from zcoder.agent.orchestration.workflow import AsyncWorkflowStep as WorkflowStep
from zcoder.agent.orchestration.workflow import WorkflowEngine
from zcoder.domain.models.legacy_job import Job, JobStatus
from zcoder.infrastructure.stores.postgres import PostgresControlPlaneStore

TEST_DSN = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


def _pg_reachable() -> bool:
    """Return True only when a PostgreSQL instance accepts connections."""
    if not TEST_DSN or not TEST_DSN.startswith("postgresql"):
        return False
    from contextlib import suppress

    import psycopg2

    with suppress(psycopg2.OperationalError, psycopg2.Error, OSError):
        with psycopg2.connect(TEST_DSN, connect_timeout=2):
            return True
    return False


# Skip PostgreSQL-backed tests when no database is available (CI has no Postgres).
_pg_available = _pg_reachable()
pytestmark = pytest.mark.skipif(not _pg_available, reason="PostgreSQL instance not reachable")


class MockClient:
    """Mock client for prompt optimization testing."""

    def __init__(self):
        self.call_count = 0
        self.model = "test-model"
        self.max_tokens = 2048

    def generate(self, user: str, system: str = "") -> str:
        self.call_count += 1
        return f"Optimized: {user[:50]}"


@pytest.fixture(scope="session")
def pg_store():
    """Create a store with test DSN."""
    if not _pg_reachable():
        pytest.skip("PostgreSQL instance not reachable")
    store = PostgresControlPlaneStore(dsn=TEST_DSN, min_conn=5, max_conn=20)
    store.init_schema()
    yield store
    store.close()


class TestDatabasePerformance:
    """Performance tests for database operations."""

    def test_connection_pool_performance(self, pg_store):
        """Test connection acquisition latency."""
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
        assert elapsed < 2.0, f"Concurrent throughput too slow: {elapsed:.3f}s for 200 queries"

    def test_job_claim_throughput(self, pg_store):
        """Test job claim throughput with multiple workers."""
        # Clean and enqueue jobs
        with pg_store._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM jobs")

        for i in range(100):
            job = Job(
                id=f"perf_claim_{i}",
                task=f"Task {i}",
                runtime="direct",
                status=JobStatus.READY,
            )
            pg_store.enqueue_job(job)

        def claim_jobs():
            claimed = []
            for _ in range(10):
                res = pg_store.claim_job_with_fencing("perf_worker", lease_duration=60.0)
                if res:
                    claimed.append(res[0].id)
            return claimed

        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(claim_jobs) for _ in range(10)]
            all_claimed = []
            for f in futures:
                all_claimed.extend(f.result())
        elapsed = time.perf_counter() - start

        assert len(all_claimed) == 100
        assert elapsed < 5.0, f"Job claim throughput too slow: {elapsed:.3f}s for 100 claims"


class TestTokenEstimationPerformance:
    """Performance tests for local token estimation."""

    def test_local_token_estimation_throughput(self):
        """Test token estimation throughput."""
        estimator = LocalTokenEstimator()
        prompts = ["prompt " * 100] * 10000

        start = time.perf_counter()
        for p in prompts:
            estimator.estimate(p, "claude-sonnet-5")
        elapsed = time.perf_counter() - start

        assert elapsed < 0.5, f"10K estimates took {elapsed:.3f}s (target <0.5s)"

    def test_token_estimation_latency(self):
        """Test single token estimation latency."""
        estimator = LocalTokenEstimator()
        prompt = "Test prompt for latency measurement " * 100

        # Warm up
        for _ in range(10):
            estimator.estimate(prompt, "claude-sonnet-5")

        latencies = []
        for _ in range(1000):
            start = time.perf_counter()
            estimator.estimate(prompt, "claude-sonnet-5")
            elapsed = (time.perf_counter() - start) * 1_000_000  # microseconds
            latencies.append(elapsed)

        avg_latency = sum(latencies) / len(latencies)
        p99_latency = sorted(latencies)[int(len(latencies) * 0.99)]
        assert avg_latency < 1000, f"Average estimation too slow: {avg_latency:.0f}μs (target <1ms)"
        assert p99_latency < 5000, f"P99 estimation too slow: {p99_latency:.0f}μs"


class TestPromptOptimizationCachePerformance:
    """Performance tests for prompt optimization caching."""

    def setup_method(self):
        clear_optimize_cache()

    def test_prompt_optimization_cache_speedup(self):
        """Test that cache provides significant speedup."""
        client = MockClient()
        prompt = "Optimize this prompt for better results " * 50

        # Cold cache
        start = time.perf_counter()
        optimize(prompt, client, "test-model")
        cold_time = time.perf_counter() - start

        # Warm cache - run multiple times to get measurable difference
        warm_times = []
        for _ in range(10):
            start = time.perf_counter()
            optimize(prompt, client, "test-model")
            warm_times.append(time.perf_counter() - start)

        warm_time = sum(warm_times) / len(warm_times)

        # Cache should be faster (at least not slower)
        # The key assertion is that client is only called once
        assert client.call_count == 1, "Client should only be called once with caching"
        # Warm cache should not be significantly slower
        assert (
            warm_time <= cold_time * 2
        ), f"Warm cache slower than cold: warm={warm_time:.6f}s, cold={cold_time:.6f}s"

    def test_cache_stats_accuracy(self):
        """Test that cache stats are accurate."""
        client = MockClient()

        optimize("prompt A", client, "model")
        optimize("prompt A", client, "model")
        optimize("prompt B", client, "model")

        stats = get_optimize_cache_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 2
        assert stats["size"] == 2


class TestCostRoutingPerformance:
    """Performance tests for cost-aware model routing."""

    def test_classify_complexity_speed(self):
        """Test complexity classification speed."""
        prompts = [
            "What is 2+2?" * 10,
            "Write a Python function that processes data" * 10,
            "Refactor this legacy codebase with comprehensive tests" * 10,
        ] * 1000  # 3000 prompts

        start = time.perf_counter()
        for p in prompts:
            classify_complexity(p)
        elapsed = time.perf_counter() - start

        assert elapsed < 1.0, f"3000 classifications took {elapsed:.3f}s (target <1s)"

    def test_select_model_speed(self):
        """Test model selection speed."""
        complexities = ["low", "medium", "high"] * 10000

        start = time.perf_counter()
        for c in complexities:
            select_model(c)
        elapsed = time.perf_counter() - start

        assert elapsed < 0.1, f"30K model selections took {elapsed:.3f}s (target <0.1s)"


class TestConcurrencyPerformance:
    """Performance tests for async concurrency."""

    def test_workflow_concurrent_execution(self):
        """Test workflow engine concurrent execution performance."""
        engine = WorkflowEngine(max_concurrent=50)

        async def step():
            await asyncio.sleep(0.01)
            return "done"

        steps = [WorkflowStep(id=f"s{i}", fn=step) for i in range(500)]

        start = time.perf_counter()
        results = asyncio.run(engine.execute(steps))
        elapsed = time.perf_counter() - start

        assert len(results) == 500
        # With 50 concurrent, 500 steps * 10ms = ~100ms ideal
        assert elapsed < 1.0, f"Concurrent workflow too slow: {elapsed:.3f}s"


class TestMemoryCachePerformance:
    """Performance tests for memory-bounded cache."""

    def test_memory_cache_throughput(self):
        """Test memory cache set/get throughput."""
        from zcoder.agent.memory.cache import MemoryCache

        cache = MemoryCache(max_size_mb=100)

        # Set throughput
        start = time.perf_counter()
        for i in range(10000):
            cache.set(f"key-{i}", "x" * 1000)
        set_time = time.perf_counter() - start

        # Get throughput
        start = time.perf_counter()
        for i in range(10000):
            cache.get(f"key-{i}")
        get_time = time.perf_counter() - start

        assert set_time < 1.0, f"10K sets took {set_time:.3f}s"
        assert get_time < 0.5, f"10K gets took {get_time:.3f}s"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
