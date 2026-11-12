"""Unit tests for PostgresEngineeringStore (mocked database)."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from zcoder.domain.models.engineering import Attempt, Checkpoint, EngineeringTask, TaskStatus
from zcoder.infrastructure.stores.postgres_engineering import PostgresEngineeringStore


class TestPostgresEngineeringStore:
    """Tests for PostgresEngineeringStore with mocked database."""

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
            store = PostgresEngineeringStore(dsn="postgresql://test@localhost/test")
            store._pool = mock_pool
            yield store

    def test_init_schema_creates_tables(self, store, mock_conn):
        """Test that init_schema executes DDL for engineering tables."""
        mock_conn, mock_cursor = mock_conn

        store.init_schema()

        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args[0][0]
        assert "CREATE TABLE IF NOT EXISTS engineering_tasks" in call_args
        assert "CREATE TABLE IF NOT EXISTS engineering_attempts" in call_args
        assert "CREATE TABLE IF NOT EXISTS engineering_checkpoints" in call_args
        assert "CREATE TABLE IF NOT EXISTS managed_repositories" in call_args
        assert "CREATE TABLE IF NOT EXISTS engineering_campaigns" in call_args
        assert "CREATE INDEX IF NOT EXISTS idx_engineering_tasks_status_created" in call_args

    def test_connection_scope_returns_context_manager(self, store, mock_conn):
        """Test connection_scope returns a connection context manager."""
        scope = store.connection_scope()
        assert scope is not None
        # Should be usable as context manager
        assert hasattr(scope, "__enter__")
        assert hasattr(scope, "__exit__")

    def test_claim_task_returns_task_and_marks_running(self, store, mock_conn):
        """Test claim_task atomically claims a CREATED task."""
        mock_conn, mock_cursor = mock_conn

        now = time.time()
        mock_cursor.fetchone.return_value = (
            "task_123",
            "Test task description",
            "CREATED",
            now - 100,
            now - 50,
            '{"key": "value"}',
        )

        task = store.claim_task()

        assert task is not None
        assert task.id == "task_123"
        assert task.task_description == "Test task description"
        assert task.status == TaskStatus.RUNNING
        assert task.metadata == {"key": "value"}
        assert mock_cursor.execute.call_count == 2  # SELECT + UPDATE

    def test_claim_task_returns_none_when_no_tasks(self, store, mock_conn):
        """Test claim_task returns None when no CREATED tasks."""
        mock_conn, mock_cursor = mock_conn
        mock_cursor.fetchone.return_value = None

        task = store.claim_task()

        assert task is None
        mock_cursor.execute.assert_called_once()

    def test_save_task_inserts_or_updates(self, store, mock_conn):
        """Test save_task inserts new or updates existing task."""
        mock_conn, mock_cursor = mock_conn

        now = time.time()
        task = EngineeringTask(
            id="task_123",
            task_description="Test task",
            status=TaskStatus.CREATED,
            created_at=now,
            updated_at=now,
            metadata={"key": "value"},
        )

        store.save_task(task)

        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        assert "INSERT INTO engineering_tasks" in call_args[0][0]
        assert "ON CONFLICT (id) DO UPDATE" in call_args[0][0]
        params = call_args[0][1]
        assert params[0] == "task_123"
        assert params[1] == "Test task"
        assert params[2] == TaskStatus.CREATED

    def test_save_task_updates_timestamp(self, store, mock_conn):
        """Test save_task updates the updated_at timestamp."""
        mock_conn, mock_cursor = mock_conn

        original_time = time.time() - 100
        task = EngineeringTask(
            id="task_123",
            task_description="Test task",
            status=TaskStatus.CREATED,
            created_at=original_time,
            updated_at=original_time,
            metadata={},
        )

        store.save_task(task)

        # updated_at should be updated to current time
        call_args = mock_cursor.execute.call_args
        params = call_args[0][1]
        current_time = params[4]  # updated_at
        assert current_time > original_time

    def test_get_task_returns_task(self, store, mock_conn):
        """Test get_task retrieves a task by ID."""
        mock_conn, mock_cursor = mock_conn

        now = time.time()
        mock_cursor.fetchone.return_value = (
            "task_123",
            "Test task",
            "CREATED",
            now - 100,
            now - 50,
            '{"key": "value"}',
        )

        task = store.get_task("task_123")

        assert task is not None
        assert task.id == "task_123"
        assert task.task_description == "Test task"
        assert task.status == TaskStatus.CREATED
        assert task.metadata == {"key": "value"}
        mock_cursor.execute.assert_called_once_with(
            "SELECT * FROM engineering_tasks WHERE id = %s",
            ("task_123",),
        )

    def test_get_task_returns_none_for_missing(self, store, mock_conn):
        """Test get_task returns None for missing task."""
        mock_conn, mock_cursor = mock_conn
        mock_cursor.fetchone.return_value = None

        task = store.get_task("missing")

        assert task is None

    def test_create_attempt_inserts_record(self, store, mock_conn):
        """Test create_attempt inserts an attempt record."""
        mock_conn, mock_cursor = mock_conn

        attempt = Attempt(
            id="att_123",
            task_id="task_123",
            generation=1,
            status="PENDING",
            started_at=time.time(),
            completed_at=None,
        )

        store.create_attempt(attempt)

        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        assert "INSERT INTO engineering_attempts" in call_args[0][0]
        assert "ON CONFLICT (id) DO NOTHING" in call_args[0][0]
        params = call_args[0][1]
        assert params[0] == "att_123"
        assert params[1] == "task_123"
        assert params[2] == 1

    def test_save_checkpoint_inserts_record(self, store, mock_conn):
        """Test save_checkpoint inserts a checkpoint record."""
        mock_conn, mock_cursor = mock_conn

        checkpoint = Checkpoint(
            id="chk_123",
            task_id="task_123",
            attempt_id="att_123",
            sequence=1,
            phase="analysis",
            state_snapshot={"step": "completed"},
            timestamp=time.time(),
        )

        store.save_checkpoint(checkpoint)

        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        assert "INSERT INTO engineering_checkpoints" in call_args[0][0]
        assert "ON CONFLICT (id) DO NOTHING" in call_args[0][0]
        params = call_args[0][1]
        assert params[0] == "chk_123"
        assert params[1] == "task_123"
        assert params[2] == "att_123"
        assert params[3] == 1
        assert params[4] == "analysis"

    def test_get_latest_checkpoint_returns_checkpoint(self, store, mock_conn):
        """Test get_latest_checkpoint retrieves latest checkpoint for attempt."""
        mock_conn, mock_cursor = mock_conn

        now = time.time()
        mock_cursor.fetchone.return_value = (
            "chk_123",
            "task_123",
            "att_123",
            1,
            "analysis",
            '{"step": "completed"}',
            now,
        )

        checkpoint = store.get_latest_checkpoint("att_123")

        assert checkpoint is not None
        assert checkpoint.id == "chk_123"
        assert checkpoint.task_id == "task_123"
        assert checkpoint.attempt_id == "att_123"
        assert checkpoint.sequence == 1
        assert checkpoint.phase == "analysis"
        assert checkpoint.state_snapshot == {"step": "completed"}
        mock_cursor.execute.assert_called_once()

    def test_get_latest_checkpoint_returns_none_for_missing(self, store, mock_conn):
        """Test get_latest_checkpoint returns None for missing attempt."""
        mock_conn, mock_cursor = mock_conn
        mock_cursor.fetchone.return_value = None

        checkpoint = store.get_latest_checkpoint("missing")

        assert checkpoint is None

    def test_list_tasks_returns_all_tasks(self, store, mock_conn):
        """Test list_tasks returns all tasks when no filter."""
        mock_conn, mock_cursor = mock_conn

        now = time.time()
        mock_cursor.fetchall.return_value = [
            ("task_1", "Task 1", "CREATED", now - 100, now - 50, '{"a": 1}'),
            ("task_2", "Task 2", "RUNNING", now - 200, now - 150, '{"b": 2}'),
        ]

        tasks = store.list_tasks()

        assert len(tasks) == 2
        assert tasks[0].id == "task_1"
        assert tasks[0].status == TaskStatus.CREATED
        assert tasks[1].id == "task_2"
        assert tasks[1].status == TaskStatus.RUNNING

    def test_list_tasks_filters_by_status(self, store, mock_conn):
        """Test list_tasks filters by status."""
        mock_conn, mock_cursor = mock_conn
        mock_cursor.fetchall.return_value = []

        store.list_tasks(status="CREATED")

        call_args = mock_cursor.execute.call_args
        assert "WHERE status = %s" in call_args[0][0]
        assert call_args[0][1] == ("CREATED",)

    def test_list_tasks_handles_metadata_string(self, store, mock_conn):
        """Test list_tasks handles metadata as JSON string."""
        mock_conn, mock_cursor = mock_conn

        now = time.time()
        mock_cursor.fetchall.return_value = [
            ("task_1", "Task 1", "CREATED", now, now, '{"key": "value"}'),
        ]

        tasks = store.list_tasks()

        assert len(tasks) == 1
        assert tasks[0].metadata == {"key": "value"}

    def test_list_tasks_handles_metadata_dict(self, store, mock_conn):
        """Test list_tasks handles metadata as dict (already parsed)."""
        mock_conn, mock_cursor = mock_conn

        now = time.time()
        # Some drivers return JSONB as dict
        mock_cursor.fetchall.return_value = [
            ("task_1", "Task 1", "CREATED", now, now, {"key": "value"}),
        ]

        tasks = store.list_tasks()

        assert len(tasks) == 1
        assert tasks[0].metadata == {"key": "value"}

    def test_inherits_postgres_control_plane_methods(self, store, mock_conn):
        """Test that store inherits methods from PostgresControlPlaneStore."""
        mock_conn, mock_cursor = mock_conn

        # Test health_check inherited method
        mock_cursor.fetchone.return_value = (1,)
        assert store.health_check() is True

        # Test get_queue_stats inherited method
        mock_cursor.fetchall.return_value = [("READY", 5)]
        stats = store.get_queue_stats()
        assert stats == {"READY": 5}

    def test_metadata_parsing_handles_both_formats(self, store, mock_conn):
        """Test that metadata parsing handles both string and dict formats."""
        mock_conn, mock_cursor = mock_conn

        now = time.time()
        # Test with string metadata
        mock_cursor.fetchone.return_value = (
            "task_1",
            "Task 1",
            "CREATED",
            now,
            now,
            '{"string_key": "value"}',
        )

        task1 = store.get_task("task_1")
        assert task1.metadata == {"string_key": "value"}

        # Test with dict metadata (some drivers return parsed JSONB)
        mock_cursor.fetchone.return_value = (
            "task_2",
            "Task 2",
            "CREATED",
            now,
            now,
            {"dict_key": "value"},
        )

        task2 = store.get_task("task_2")
        assert task2.metadata == {"dict_key": "value"}

    def test_claim_task_updates_status_to_running(self, store, mock_conn):
        """Test that claim_task updates task status to RUNNING."""
        mock_conn, mock_cursor = mock_conn

        now = time.time()
        mock_cursor.fetchone.return_value = (
            "task_123",
            "Test task",
            "CREATED",
            now - 100,
            now - 50,
            "{}",
        )

        task = store.claim_task()

        assert task is not None
        assert task.status == TaskStatus.RUNNING

        # Verify UPDATE was called with RUNNING status
        update_call = mock_cursor.execute.call_args_list[1]
        assert "UPDATE engineering_tasks" in update_call[0][0]
        assert "SET status = 'RUNNING'" in update_call[0][0]
        assert update_call[0][1][1] == "task_123"

    def test_init_schema_idempotent(self, store, mock_conn):
        """Test init_schema can be called multiple times."""
        mock_conn, mock_cursor = mock_conn
        store.init_schema()
        store.init_schema()

        # Should execute twice without error
        assert mock_cursor.execute.call_count == 2
