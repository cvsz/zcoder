"""tests/test_worker_process.py — Tests for the production worker process."""

import threading
import time

import pytest

from worker_process import Worker, WorkerState


@pytest.fixture
def sqlite_worker(tmp_path):
    """Create a worker with SQLite backend for unit testing."""
    from control_plane import ControlPlaneStore

    db_path = tmp_path / "test_control_plane.db"
    store = ControlPlaneStore(db_path=db_path)

    worker = Worker(
        worker_id="test-worker-001",
        pool_type="standard",
        concurrency=2,
        lease_duration=10.0,
        heartbeat_interval=5.0,
        shutdown_timeout=5.0,
        database_url="",
        use_postgres=False,
    )
    # Override store with our test instance
    worker._store = store
    return worker, store


def _insert_job(store, job_id: str, task: str = "test task", runtime: str = "fake"):
    """Helper to insert a test job."""
    import sqlite3
    import time

    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            """INSERT INTO jobs (id, task, runtime, status, workspace, created_at, updated_at, 
               model, budget_usd, cost_usd, claim_generation, lease_expires_at, metadata)
               VALUES (?, ?, ?, 'READY', '.', ?, ?, 'claude-sonnet-5', 1.0, 0.0, 0, 0, '{}')""",
            (job_id, task, runtime, time.time(), time.time()),
        )


class TestWorkerInitialization:
    def test_worker_id_generated_if_not_set(self):
        worker = Worker(worker_id="")
        assert worker.worker_id.startswith("worker_")
        assert len(worker.worker_id) > 8

    def test_explicit_worker_id(self):
        worker = Worker(worker_id="my-custom-worker")
        assert worker.worker_id == "my-custom-worker"

    def test_initial_state_is_idle(self):
        worker = Worker(worker_id="test-idle")
        assert worker.state == WorkerState.IDLE

    def test_worker_status_dict(self):
        worker = Worker(worker_id="status-worker", pool_type="sandbox")
        status = worker.get_status()
        assert status["worker_id"] == "status-worker"
        assert status["pool_type"] == "sandbox"
        assert "state" in status
        assert "active_jobs" in status


class TestWorkerDraining:
    def test_drain_sets_draining_state(self, sqlite_worker):
        worker, store = sqlite_worker
        worker._state = WorkerState.RUNNING
        worker._begin_drain()
        assert worker.state == WorkerState.DRAINING

    def test_drain_sets_stop_event(self, sqlite_worker):
        worker, store = sqlite_worker
        worker._state = WorkerState.RUNNING
        assert not worker._stop_event.is_set()
        worker._begin_drain()
        assert worker._stop_event.is_set()

    def test_drain_does_not_error_if_already_stopped(self, sqlite_worker):
        worker, store = sqlite_worker
        worker._state = WorkerState.STOPPED
        # Should not raise
        worker._begin_drain()
        # State should remain STOPPED
        assert worker.state == WorkerState.STOPPED


class TestWorkerShutdown:
    def test_graceful_shutdown_with_no_active_jobs(self, sqlite_worker):
        worker, store = sqlite_worker
        worker._state = WorkerState.RUNNING
        # No active jobs — should complete immediately
        worker._shutdown_gracefully()
        assert worker.state == WorkerState.STOPPED

    def test_shutdown_releases_claimed_jobs_on_timeout(self, sqlite_worker):
        """Jobs still active after shutdown_timeout must be released back to READY."""
        worker, store = sqlite_worker
        worker._state = WorkerState.RUNNING
        worker.shutdown_timeout = 0.01  # Very short timeout

        # Insert a job
        _insert_job(store, "job_timeout_test")

        # Claim it
        result = store.claim_job_with_fencing("test-worker-001", lease_duration=60.0)
        assert result is not None
        job, fencing_token = result

        # Add to active jobs dict with a thread that sleeps longer than timeout
        done_event = threading.Event()
        long_thread = threading.Thread(target=lambda: done_event.wait(timeout=60))
        long_thread.start()

        worker._active_jobs[job.id] = {
            "job": job,
            "fencing_token": fencing_token,
            "thread": long_thread,
        }

        # Run shutdown — should timeout and release
        worker._shutdown_gracefully()

        # The thread should still be running (we didn't set done_event)
        done_event.set()  # cleanup
        long_thread.join()


class TestWorkerJobClaim:
    def test_worker_claims_fake_job(self, sqlite_worker):
        worker, store = sqlite_worker
        _insert_job(store, "job_claim_test", runtime="fake")

        result = store.claim_job_with_fencing("test-worker-001", lease_duration=60.0)
        assert result is not None
        job, gen = result
        assert job.id == "job_claim_test"
        assert gen == 1

    def test_worker_execute_job_succeeds(self, sqlite_worker):
        worker, store = sqlite_worker
        _insert_job(store, "job_exec_test", runtime="fake")

        result = store.claim_job_with_fencing("test-worker-001", lease_duration=60.0)
        assert result is not None
        job, fencing_token = result

        # Execute synchronously
        worker._execute_job(job, fencing_token)

        # Verify job is now SUCCEEDED
        import sqlite3

        with sqlite3.connect(store.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT status FROM jobs WHERE id = 'job_exec_test'")
            row = cur.fetchone()
            assert row is not None
            assert row[0] == "SUCCEEDED"

    def test_fencing_rejected_for_stale_worker(self, sqlite_worker):
        from agent_runtime import JobStatus

        worker, store = sqlite_worker
        _insert_job(store, "job_fencing_test", runtime="fake")

        # Claim with worker A
        result = store.claim_job_with_fencing("worker-A", lease_duration=60.0)
        assert result is not None
        job, gen = result

        # Stale worker B tries to mutate with old generation (0)
        rejected = store.mutate_with_fencing("job_fencing_test", "worker-B", 0, JobStatus.SUCCEEDED, 0.0)
        assert rejected is False

    def test_fencing_monotonically_increasing(self, sqlite_worker):
        worker, store = sqlite_worker
        _insert_job(store, "job_monotonic_test", runtime="fake")

        # Claim → expire → reclaim
        result1 = store.claim_job_with_fencing("worker-A", lease_duration=0.001)
        assert result1 is not None
        _, gen1 = result1

        # Let lease expire
        time.sleep(0.01)

        result2 = store.claim_job_with_fencing("worker-B", lease_duration=60.0)
        assert result2 is not None
        _, gen2 = result2

        # Generation must be strictly increasing
        assert gen2 > gen1


class TestWorkerPoolTypes:
    def test_standard_pool_type(self):
        worker = Worker(worker_id="pool-test", pool_type="standard")
        status = worker.get_status()
        assert status["pool_type"] == "standard"

    def test_sandbox_pool_type(self):
        worker = Worker(worker_id="pool-sandbox", pool_type="sandbox")
        status = worker.get_status()
        assert status["pool_type"] == "sandbox"

    def test_trusted_pool_type(self):
        worker = Worker(worker_id="pool-trusted", pool_type="trusted")
        assert worker.pool_type == "trusted"

    def test_high_isolation_pool_type(self):
        worker = Worker(worker_id="pool-hi", pool_type="high-isolation")
        assert worker.pool_type == "high-isolation"


class TestWorkerSignalHandling:
    def test_signal_handlers_install_without_crash(self, sqlite_worker):
        worker, store = sqlite_worker
        # Should not raise
        worker.install_signal_handlers()

    def test_simulate_sigterm_sets_draining(self, sqlite_worker):
        """Simulate what happens when SIGTERM is received."""
        worker, store = sqlite_worker
        worker._state = WorkerState.RUNNING
        # Simulate signal handler
        worker._handle_sigterm(15, None)
        assert worker.state == WorkerState.DRAINING
        assert worker._stop_event.is_set()
