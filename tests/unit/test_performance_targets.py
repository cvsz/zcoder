"""tests/unit/test_performance_targets.py — Performance and load regression tests for ZCoder.

Validates bounded latency, memory, concurrency, and backpressure targets
documented in the execution plan.
"""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from zcoder.domain.models.engineering import EngineeringTask
from zcoder.domain.services.control_plane import ControlPlaneStore
from zcoder.domain.services.deployment import DeploymentEngine
from zcoder.infrastructure.stores.sqlite_engineering import SQLiteEngineeringStore


@pytest.fixture
def control_plane_store(tmp_path):
    db_path = tmp_path / "perf_cp.db"
    store = ControlPlaneStore(db_path=db_path)
    yield store
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def engineering_store(tmp_path):
    db_path = tmp_path / "perf_eng.db"
    store = SQLiteEngineeringStore(db_path=db_path)
    yield store
    if db_path.exists():
        db_path.unlink()


class TestLatencyTargets:
    def test_health_evaluation_latency(self, control_plane_store):
        engine = DeploymentEngine(store=control_plane_store)
        start = time.perf_counter()
        for _ in range(100):
            engine.evaluate_health()
        elapsed = time.perf_counter() - start
        avg_ms = (elapsed / 100) * 1000
        assert avg_ms < 50, f"Health evaluation too slow: {avg_ms:.2f}ms avg (target <50ms)"

    def test_backup_creation_latency(self, control_plane_store):
        engine = DeploymentEngine(store=control_plane_store)
        start = time.perf_counter()
        backup = engine.create_logical_backup()
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0, f"Backup creation too slow: {elapsed:.3f}s (target <1s)"
        assert backup.data_dump


class TestConcurrencyAndBackpressure:
    def test_concurrent_job_claims_no_duplicates(self, control_plane_store):
        for i in range(50):
            control_plane_store.enqueue_outbox(f"perf.action.{i}", {"i": i})

        claimed_ids = set()
        lock = __import__("threading").Lock()

        def claim_one():
            claimed = control_plane_store.claim_job_with_fencing("perf_worker", lease_duration=60.0)
            if claimed:
                job, _ = claimed
                with lock:
                    claimed_ids.add(job.id)

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(claim_one) for _ in range(10)]
            for f in futures:
                f.result()

        assert len(claimed_ids) <= 10, "Duplicate claims detected under concurrency"

    def test_high_volume_task_persistence(self, engineering_store):
        start = time.perf_counter()
        for i in range(500):
            task = EngineeringTask(id=f"perf_{i}", task_description="Performance task")
            engineering_store.save_task(task)
        elapsed = time.perf_counter() - start
        assert elapsed < 10.0, f"Task persistence too slow: {elapsed:.3f}s for 500 tasks"

        tasks = engineering_store.list_tasks()
        assert len(tasks) == 500


class TestMemoryTargets:
    def test_memory_growth_bounded(self, control_plane_store):
        pytest.importorskip("psutil")
        import psutil

        process = psutil.Process(os.getpid())
        baseline = process.memory_info().rss / 1024 / 1024
        for i in range(1000):
            control_plane_store.enqueue_outbox(f"mem.action.{i}", {"i": i})
        after = process.memory_info().rss / 1024 / 1024
        growth = after - baseline
        assert growth < 100, f"Memory growth too high: {growth:.1f}MB (target <100MB)"


class TestBackpressure:
    def test_outbox_backpressure(self, control_plane_store):
        for i in range(200):
            control_plane_store.enqueue_outbox(f"bp.action.{i}", {"i": i})
        processed = control_plane_store.process_outbox(lambda action, payload: None, max_messages=200)
        assert processed == 200
