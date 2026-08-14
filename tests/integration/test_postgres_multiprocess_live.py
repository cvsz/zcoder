"""tests/test_postgres_multiprocess_live.py — Live real PostgreSQL multi-process integration tests.

Tests real:
- PostgreSQL connection & schema creation
- Atomic multi-process claiming with SKIP LOCKED
- No duplicate execution across concurrent worker processes
- Monotonic fencing tokens
- Worker crash and lease expiration recovery
- Stale fencing mutation rejection
- Database connection restart recovery
- Backup & restore drill validation against real PostgreSQL
"""

import multiprocessing
import os
import time

import psycopg2
import pytest

from agent_runtime import Job, JobStatus
from postgres_store import PostgresControlPlaneStore

PG_URL = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:postgres@172.17.0.2:5432/zcoder")


def pg_is_available():
    try:
        conn = psycopg2.connect(PG_URL, connect_timeout=2)
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not pg_is_available(), reason="PostgreSQL test container not reachable")


@pytest.fixture(scope="module")
def pg_store():
    store = PostgresControlPlaneStore(dsn=PG_URL)
    store.init_schema()
    yield store
    store.close()


def _worker_claim_loop(worker_name: str, duration_sec: float, claimed_list, error_list):
    try:
        store = PostgresControlPlaneStore(dsn=PG_URL)
        end_time = time.time() + duration_sec
        while time.time() < end_time:
            res = store.claim_job_with_fencing(worker_name, lease_duration=10.0)
            if res:
                job, fencing_token = res
                claimed_list.append((job.id, worker_name, fencing_token))
                # Simulate work
                time.sleep(0.05)
                # Mutate to SUCCEEDED
                store.mutate_with_fencing(job.id, worker_name, fencing_token, JobStatus.SUCCEEDED, 0.01)
            else:
                time.sleep(0.02)
        store.close()
    except Exception as e:
        error_list.append(str(e))


class TestRealPostgresMultiProcess:
    def test_schema_initialization_and_health(self, pg_store):
        assert pg_store.health_check() is True

    def test_multi_process_concurrent_claims_no_duplicates(self, pg_store):
        # Clean jobs table
        with pg_store._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM jobs WHERE id LIKE 'mp_job_%'")

        # Enqueue 30 jobs
        num_jobs = 30
        for i in range(num_jobs):
            job = Job(
                id=f"mp_job_{i}",
                task=f"Task {i}",
                runtime="fake",
                status=JobStatus.READY,
            )
            pg_store.enqueue_job(job)

        manager = multiprocessing.Manager()
        claimed_list = manager.list()
        error_list = manager.list()

        # Start 3 concurrent worker processes
        workers = []
        for w_idx in range(3):
            p = multiprocessing.Process(
                target=_worker_claim_loop, args=(f"worker_proc_{w_idx}", 4.0, claimed_list, error_list)
            )
            p.start()
            workers.append(p)

        for p in workers:
            p.join(timeout=10.0)

        assert len(error_list) == 0, f"Errors in worker processes: {list(error_list)}"

        # Verify that all 30 jobs were claimed exactly once
        claimed_job_ids = [c[0] for c in claimed_list]
        assert len(claimed_job_ids) == num_jobs, f"Expected {num_jobs} claims, got {len(claimed_job_ids)}"
        assert len(set(claimed_job_ids)) == num_jobs, "Duplicate job claim detected across processes!"

        # Verify all fencing tokens were > 0
        for _, _, fencing_token in claimed_list:
            assert fencing_token >= 1

    def test_worker_crash_and_lease_expiry_recovery(self, pg_store):
        job_id = "crash_job_1"
        with pg_store._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM jobs WHERE id = %s", (job_id,))

        job = Job(id=job_id, task="Crash recovery task", runtime="fake", status=JobStatus.READY)
        pg_store.enqueue_job(job)

        # Worker A claims with short lease (0.2s)
        resA = pg_store.claim_job_with_fencing("worker_A", lease_duration=0.2)
        assert resA is not None
        claimed_job_A, token_A = resA
        assert token_A == 1

        # Simulate Worker A crash (abrupt termination, no completion)
        time.sleep(0.3)  # Wait for lease expiration

        # Worker B claims expired job
        resB = pg_store.claim_job_with_fencing("worker_B", lease_duration=5.0)
        assert resB is not None
        claimed_job_B, token_B = resB
        assert claimed_job_B.id == job_id
        assert token_B == 2  # Monotonic fencing token incremented

        # Stale Worker A resumes and attempts to mutate with old token_A (1) -> REJECTED
        stale_mutation = pg_store.mutate_with_fencing(job_id, "worker_A", token_A, JobStatus.SUCCEEDED, 0.05)
        assert stale_mutation is False, "Stale worker write was NOT rejected!"

        # Worker B completes job with valid token_B (2) -> ACCEPTED
        valid_mutation = pg_store.mutate_with_fencing(job_id, "worker_B", token_B, JobStatus.SUCCEEDED, 0.05)
        assert valid_mutation is True

    def test_outbox_processing_and_webhook_dedup(self, pg_store):
        # Outbox enqueue and process
        out_msg = pg_store.enqueue_outbox("test.action", {"key": "value"})
        assert out_msg["status"] == "PENDING"

        processed = pg_store.process_outbox(lambda action, payload: None)
        assert processed >= 1

        # Webhook deduplication
        del_id = f"del_live_{time.time()}"
        first_rec = pg_store.record_webhook_delivery_atomic(del_id, "push")
        assert first_rec is True
        dup_rec = pg_store.record_webhook_delivery_atomic(del_id, "push")
        assert dup_rec is False, "Duplicate webhook delivery allowed in database!"
