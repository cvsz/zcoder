"""Unit tests for PostgresControlPlaneStore (mocked database)."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from zcoder.domain.models.legacy_job import Job, JobStatus
from zcoder.infrastructure.stores.postgres import PostgresControlPlaneStore


class TestPostgresControlPlaneStore:
    """Tests for PostgresControlPlaneStore with mocked database."""

    @pytest.fixture
    def mock_pool(self):
        """Create a mock connection pool."""
        with patch("zcoder.infrastructure.stores.postgres._PSYCOPG2_AVAILABLE", True):
            with patch("zcoder.infrastructure.stores.postgres.psycopg2") as mock_psycopg2:
                mock_pool = MagicMock()
                mock_psycopg2.pool.ThreadedConnectionPool.return_value = mock_pool
                yield mock_pool

    @pytest.fixture
    def mock_conn(self, mock_pool):
        """Create a mock connection."""
        mock_conn = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        yield mock_conn, mock_cursor

    @pytest.fixture
    def store(self, mock_pool):
        """Create a store instance with mocked pool."""
        with patch.dict("os.environ", {"DATABASE_URL": "postgresql://test@localhost/test"}):
            store = PostgresControlPlaneStore(dsn="postgresql://test@localhost/test")
            # Replace the pool with our mock
            store._pool = mock_pool
            yield store

    def test_init_requires_dsn(self, mock_pool):
        """Test that initialization requires a DSN."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="DATABASE_URL must be set"):
                PostgresControlPlaneStore(dsn="")

    def test_init_schema_creates_tables(self, store, mock_conn):
        """Test that init_schema executes DDL."""
        mock_conn, mock_cursor = mock_conn

        store.init_schema()

        mock_cursor.execute.assert_called_once()
        # Verify the schema SQL was executed
        call_args = mock_cursor.execute.call_args[0][0]
        assert "CREATE TABLE IF NOT EXISTS jobs" in call_args
        assert "CREATE TABLE IF NOT EXISTS outbox" in call_args

    def test_enqueue_job_inserts_record(self, store, mock_conn):
        """Test enqueue_job inserts a job record."""
        mock_conn, mock_cursor = mock_conn

        job = Job(
            id="job_123",
            task="test task",
            runtime="direct",
            status=JobStatus.READY,
            workspace="/tmp",
            created_at=time.time(),
            updated_at=time.time(),
            model="test-model",
            budget_usd=1.0,
            cost_usd=0.0,
            metadata={"key": "value"},
        )

        result = store.enqueue_job(job)

        assert result is job
        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        assert "INSERT INTO jobs" in call_args[0][0]
        # Verify parameters
        params = call_args[0][1]
        assert params[0] == "job_123"
        assert params[1] == "test task"
        assert params[4] == "/tmp"  # workspace is 5th parameter (index 4)

    def test_get_job_returns_job(self, store, mock_conn):
        """Test get_job retrieves a job."""
        mock_conn, mock_cursor = mock_conn

        now = time.time()
        mock_cursor.fetchone.return_value = (
            "job_123",
            "test task",
            "direct",
            "READY",
            "/tmp",
            now,
            now,
            "test-model",
            1.0,
            0.0,
            '{"key": "value"}',
        )

        job = store.get_job("job_123")

        assert job is not None
        assert job.id == "job_123"
        assert job.task == "test task"
        assert job.status == JobStatus.READY
        assert job.metadata == {"key": "value"}
        mock_cursor.execute.assert_called_once_with(
            "SELECT id, task, runtime, status, workspace, created_at, updated_at, "
            "model, budget_usd, cost_usd, metadata FROM jobs WHERE id = %s",
            ("job_123",),
        )

    def test_get_job_returns_none_for_missing(self, store, mock_conn):
        """Test get_job returns None for missing job."""
        mock_conn, mock_cursor = mock_conn
        mock_cursor.fetchone.return_value = None

        job = store.get_job("missing")

        assert job is None

    def test_list_jobs_returns_jobs(self, store, mock_conn):
        """Test list_jobs returns multiple jobs."""
        mock_conn, mock_cursor = mock_conn

        now = time.time()
        mock_cursor.fetchall.return_value = [
            ("job_1", "task 1", "direct", "READY", "/tmp", now, now, "model1", 1.0, 0.0, "{}"),
            ("job_2", "task 2", "direct", "RUNNING", "/tmp", now, now, "model2", 2.0, 0.5, "{}"),
        ]

        jobs = store.list_jobs(limit=10)

        assert len(jobs) == 2
        assert jobs[0].id == "job_1"
        assert jobs[1].id == "job_2"
        assert jobs[0].status == JobStatus.READY
        assert jobs[1].status == JobStatus.RUNNING

    def test_list_jobs_with_status_filter(self, store, mock_conn):
        """Test list_jobs with status filter."""
        mock_conn, mock_cursor = mock_conn
        mock_cursor.fetchall.return_value = []

        store.list_jobs(status_filter="READY", limit=5)

        call_args = mock_cursor.execute.call_args
        assert "WHERE status = %s" in call_args[0][0]
        assert call_args[0][1] == ("READY", 5)

    def test_claim_job_with_fencing_returns_job_and_token(self, store, mock_conn):
        """Test claim_job_with_fencing atomically claims a job."""
        mock_conn, mock_cursor = mock_conn

        now = time.time()
        # First query returns a job
        mock_cursor.fetchone.side_effect = [
            ("job_123", "test task", "direct", "READY", "/tmp", now, now, "model", 1.0, 0.0, 0, "{}"),
            ("job_123",),  # UPDATE RETURNING
        ]

        result = store.claim_job_with_fencing("worker_1", lease_duration=120.0)

        assert result is not None
        job, token = result
        assert job.id == "job_123"
        assert job.status == JobStatus.RUNNING
        assert token == 1  # gen + 1
        assert mock_cursor.execute.call_count == 2

    def test_claim_job_with_fencing_returns_none_when_empty(self, store, mock_conn):
        """Test claim_job_with_fencing returns None when no jobs."""
        mock_conn, mock_cursor = mock_conn
        mock_cursor.fetchone.return_value = None

        result = store.claim_job_with_fencing("worker_1")

        assert result is None

    def test_mutate_with_fencing_returns_true_on_success(self, store, mock_conn):
        """Test mutate_with_fencing returns True when update succeeds."""
        mock_conn, mock_cursor = mock_conn
        mock_cursor.rowcount = 1

        result = store.mutate_with_fencing(
            job_id="job_123",
            worker_id="worker_1",
            fencing_token=1,
            status=JobStatus.SUCCEEDED,
            cost_usd=0.5,
        )

        assert result is True
        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        assert "UPDATE jobs" in call_args[0][0]
        assert "WHERE id = %s AND claimed_by = %s AND claim_generation = %s" in call_args[0][0]

    def test_mutate_with_fencing_returns_false_on_stale_token(self, store, mock_conn):
        """Test mutate_with_fencing returns False for stale token."""
        mock_conn, mock_cursor = mock_conn
        mock_cursor.rowcount = 0

        result = store.mutate_with_fencing(
            job_id="job_123",
            worker_id="worker_1",
            fencing_token=999,  # Stale token
            status=JobStatus.SUCCEEDED,
            cost_usd=0.5,
        )

        assert result is False

    def test_renew_lease_returns_true_on_success(self, store, mock_conn):
        """Test renew_lease extends lease for running job."""
        mock_conn, mock_cursor = mock_conn
        mock_cursor.rowcount = 1

        result = store.renew_lease("job_123", "worker_1", 1, lease_duration=60.0)

        assert result is True
        mock_cursor.execute.assert_called_once()

    def test_reconcile_expired_leases_returns_count(self, store, mock_conn):
        """Test reconcile_expired_leases returns number of reconciled jobs."""
        mock_conn, mock_cursor = mock_conn
        mock_cursor.fetchall.return_value = [("job_1",), ("job_2",)]

        count = store.reconcile_expired_leases()

        assert count == 2
        mock_cursor.execute.assert_called_once()

    def test_enqueue_outbox_returns_message(self, store, mock_conn):
        """Test enqueue_outbox creates outbox message."""
        mock_conn, mock_cursor = mock_conn

        result = store.enqueue_outbox("test_action", {"key": "value"})

        assert "id" in result
        assert result["action"] == "test_action"
        assert result["status"] == "PENDING"
        assert "created_at" in result
        mock_cursor.execute.assert_called_once()

    def test_record_webhook_delivery_atomic_returns_true_for_new(self, store, mock_conn):
        """Test record_webhook_delivery_atomic returns True for new delivery."""
        mock_conn, mock_cursor = mock_conn
        mock_cursor.fetchone.return_value = ("delivery_123",)

        result = store.record_webhook_delivery_atomic("delivery_123", "push")

        assert result is True

    def test_record_webhook_delivery_atomic_returns_false_for_duplicate(self, store, mock_conn):
        """Test record_webhook_delivery_atomic returns False for duplicate."""
        mock_conn, mock_cursor = mock_conn
        mock_cursor.fetchone.return_value = None  # ON CONFLICT DO NOTHING returns no row

        result = store.record_webhook_delivery_atomic("delivery_123", "push")

        assert result is False

    def test_register_installation_upserts(self, store, mock_conn):
        """Test register_installation upserts installation."""
        mock_conn, mock_cursor = mock_conn

        store.register_installation(12345, "test-org", "Organization")

        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        assert "INSERT INTO installations" in call_args[0][0]
        assert "ON CONFLICT (installation_id) DO UPDATE" in call_args[0][0]

    def test_register_repository_upserts(self, store, mock_conn):
        """Test register_repository upserts repository."""
        mock_conn, mock_cursor = mock_conn

        store.register_repository("repo_123", 12345, "owner", "repo")

        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        assert "INSERT INTO repositories" in call_args[0][0]
        assert "ON CONFLICT (id) DO UPDATE" in call_args[0][0]

    def test_register_worker_upserts(self, store, mock_conn):
        """Test register_worker upserts worker."""
        mock_conn, mock_cursor = mock_conn

        store.register_worker("worker_1", "standard", "host1", 1234)

        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        assert "INSERT INTO worker_registry" in call_args[0][0]
        assert "ON CONFLICT (worker_id) DO UPDATE" in call_args[0][0]

    def test_heartbeat_worker_updates_timestamp(self, store, mock_conn):
        """Test heartbeat_worker updates last_heartbeat."""
        mock_conn, mock_cursor = mock_conn

        store.heartbeat_worker("worker_1", active_jobs=2)

        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        assert "UPDATE worker_registry SET last_heartbeat" in call_args[0][0]
        assert call_args[0][1][2] == "worker_1"

    def test_get_active_workers_returns_recent(self, store, mock_conn):
        """Test get_active_workers returns recently active workers."""
        mock_conn, mock_cursor = mock_conn
        now = time.time()
        mock_cursor.fetchall.return_value = [
            ("worker_1", "standard", "host1", 1234, now - 10, 1),
            ("worker_2", "high", "host2", 5678, now - 20, 0),
        ]

        workers = store.get_active_workers(max_idle_seconds=300.0)

        assert len(workers) == 2
        assert workers[0]["worker_id"] == "worker_1"
        assert workers[0]["active_jobs"] == 1
        assert workers[1]["worker_id"] == "worker_2"

    def test_record_deployment_returns_id(self, store, mock_conn):
        """Test record_deployment creates deployment record."""
        mock_conn, mock_cursor = mock_conn

        deploy_id = store.record_deployment(
            version="1.0.0",
            environment="production",
            actor="deployer",
            image_digest="sha256:abc",
            migration_version="v10",
            result="SUCCESS",
            notes="Deploy notes",
        )

        assert deploy_id.startswith("deploy_")
        mock_cursor.execute.assert_called_once()

    def test_record_backup_returns_id(self, store, mock_conn):
        """Test record_backup creates backup record."""
        mock_conn, mock_cursor = mock_conn

        backup_id = store.record_backup(
            backup_type="pg_dump",
            success=True,
            size_bytes=1024,
            destination="/backups/test.dump",
        )

        assert backup_id.startswith("bkp_")
        mock_cursor.execute.assert_called_once()

    def test_record_restore_drill_updates_backup(self, store, mock_conn):
        """Test record_restore_drill updates backup record."""
        mock_conn, mock_cursor = mock_conn

        store.record_restore_drill("bkp_123", success=True)

        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        assert "UPDATE backup_status SET restore_drill_at" in call_args[0][0]
        assert call_args[0][1][2] == "bkp_123"

    def test_get_backup_freshness_returns_info(self, store, mock_conn):
        """Test get_backup_freshness returns backup info."""
        mock_conn, mock_cursor = mock_conn
        now = time.time()
        # First query for last backup
        mock_cursor.fetchone.side_effect = [
            (now - 3600, True),  # last_backup
            (now - 7200, True),  # last_drill
        ]

        freshness = store.get_backup_freshness()

        assert freshness["last_backup_at"] == now - 3600
        assert freshness["last_backup_success"] is True
        assert freshness["last_restore_drill_at"] == now - 7200
        assert freshness["last_restore_drill_success"] is True
        assert mock_cursor.execute.call_count == 2

    def test_get_backup_freshness_handles_missing(self, store, mock_conn):
        """Test get_backup_freshness handles missing backups."""
        mock_conn, mock_cursor = mock_conn
        mock_cursor.fetchone.return_value = None

        freshness = store.get_backup_freshness()

        assert freshness["last_backup_at"] is None
        assert freshness["last_backup_success"] is False
        assert freshness["last_restore_drill_at"] is None
        assert freshness["last_restore_drill_success"] is False

    def test_health_check_returns_true_on_success(self, store, mock_conn):
        """Test health_check returns True on successful connection."""
        mock_conn, mock_cursor = mock_conn
        mock_cursor.fetchone.return_value = (1,)

        result = store.health_check()

        assert result is True
        mock_cursor.execute.assert_called_once_with("SELECT 1")

    def test_health_check_returns_false_on_failure(self, store, mock_conn):
        """Test health_check returns False on connection failure."""
        mock_conn, mock_cursor = mock_conn
        mock_cursor.execute.side_effect = Exception("Connection failed")

        result = store.health_check()

        assert result is False

    def test_get_queue_stats_returns_counts(self, store, mock_conn):
        """Test get_queue_stats returns job counts by status."""
        mock_conn, mock_cursor = mock_conn
        mock_cursor.fetchall.return_value = [
            ("READY", 5),
            ("RUNNING", 2),
            ("SUCCEEDED", 10),
            ("FAILED", 1),
        ]

        stats = store.get_queue_stats()

        assert stats == {"READY": 5, "RUNNING": 2, "SUCCEEDED": 10, "FAILED": 1}
        mock_cursor.execute.assert_called_once_with("SELECT status, COUNT(*) FROM jobs GROUP BY status")

    def test_close_closes_pool(self, store, mock_pool):
        """Test close closes the connection pool."""
        store.close()

        mock_pool.closeall.assert_called_once()

    def test_close_handles_none_pool(self, store, mock_pool):
        """Test close handles None pool gracefully."""
        store._pool = None
        store.close()  # Should not raise

    def test_init_pool_psycopg3_fallback(self):
        """Test init_pool falls back to psycopg3 when psycopg2 not available."""
        with patch("zcoder.infrastructure.stores.postgres._PSYCOPG2_AVAILABLE", False):
            with patch("zcoder.infrastructure.stores.postgres._PG_AVAILABLE", True):
                # Mock the psycopg module import
                import sys

                mock_psycopg = MagicMock()
                mock_pool = MagicMock()
                mock_psycopg.pool.ConnectionPool.return_value = mock_pool
                sys.modules["psycopg"] = mock_psycopg
                sys.modules["psycopg.pool"] = mock_psycopg.pool

                try:
                    with patch.dict("os.environ", {"DATABASE_URL": "postgresql://test@localhost/test"}):
                        store = PostgresControlPlaneStore(dsn="postgresql://test@localhost/test")
                        # Reset call count since __init__ calls _init_pool
                        mock_psycopg.pool.ConnectionPool.reset_mock()
                        store._pool = None  # Force re-init
                        store._init_pool()

                    assert store._pool is mock_pool
                    mock_psycopg.pool.ConnectionPool.assert_called_once()
                finally:
                    # Clean up
                    if "psycopg" in sys.modules:
                        del sys.modules["psycopg"]
                    if "psycopg.pool" in sys.modules:
                        del sys.modules["psycopg.pool"]
