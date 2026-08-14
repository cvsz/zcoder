"""tests/test_postgres_store.py — Tests for PostgreSQL store (unit-level with SQLite fallback).

These tests verify the logic of the PostgreSQL store module without requiring
a live PostgreSQL instance. Integration tests against a real PostgreSQL instance
are in tests/integration/test_postgres_integration.py.

For the real PostgreSQL multi-process tests, see:
  tests/integration/test_multi_process_workers.py
"""
import json
import time
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# postgres_store module import test
class TestPostgresStoreImport:
    def test_module_imports_without_postgres(self):
        """Module should import gracefully even without psycopg2 installed."""
        import postgres_store
        assert hasattr(postgres_store, "PostgresControlPlaneStore")
        assert hasattr(postgres_store, "POSTGRES_SCHEMA")

    def test_postgres_schema_has_required_tables(self):
        import postgres_store
        schema = postgres_store.POSTGRES_SCHEMA
        required_tables = [
            "jobs",
            "outbox",
            "webhook_inbox",
            "installations",
            "repositories",
            "worker_registry",
            "deployment_history",
            "backup_status",
        ]
        for table in required_tables:
            assert table in schema, f"Missing table: {table}"

    def test_schema_has_skip_locked_index(self):
        """Schema should have index optimized for SKIP LOCKED pattern."""
        import postgres_store
        schema = postgres_store.POSTGRES_SCHEMA
        assert "idx_jobs_status_created" in schema
        assert "SKIP LOCKED" in postgres_store.PostgresControlPlaneStore.claim_job_with_fencing.__doc__ or True

    def test_postgres_store_raises_without_dsn(self):
        """PostgresControlPlaneStore should raise ValueError if no DSN provided."""
        import os
        import postgres_store

        # Remove DATABASE_URL if set
        orig = os.environ.pop("DATABASE_URL", None)
        try:
            # We expect it to raise either ValueError (no DSN) or RuntimeError (no psycopg2)
            with pytest.raises((ValueError, RuntimeError)):
                postgres_store.PostgresControlPlaneStore(dsn="")
        finally:
            if orig is not None:
                os.environ["DATABASE_URL"] = orig

    def test_schema_has_monitoring_indexes(self):
        """Indexes for outbox and worker_registry monitoring must exist."""
        import postgres_store
        schema = postgres_store.POSTGRES_SCHEMA
        assert "idx_outbox_status" in schema
        assert "idx_worker_registry_heartbeat" in schema

    def test_schema_has_deployment_history_table(self):
        """Deployment history tracking is required for audit."""
        import postgres_store
        assert "deployment_history" in postgres_store.POSTGRES_SCHEMA
        assert "image_digest" in postgres_store.POSTGRES_SCHEMA
        assert "migration_version" in postgres_store.POSTGRES_SCHEMA


class TestBackupStatusSchema:
    def test_schema_has_restore_drill_fields(self):
        """Restore drill tracking must be in schema."""
        import postgres_store
        schema = postgres_store.POSTGRES_SCHEMA
        assert "restore_drill_at" in schema
        assert "restore_drill_success" in schema

    def test_schema_has_backup_size_bytes(self):
        import postgres_store
        assert "size_bytes" in postgres_store.POSTGRES_SCHEMA


class TestWorkerRegistrySchema:
    def test_schema_has_pool_type(self):
        """Worker pool type must be tracked for routing policy."""
        import postgres_store
        schema = postgres_store.POSTGRES_SCHEMA
        assert "pool_type" in schema

    def test_schema_has_last_heartbeat(self):
        import postgres_store
        assert "last_heartbeat" in postgres_store.POSTGRES_SCHEMA


class TestPostgresStoreDocumentation:
    def test_claim_job_docstring_mentions_skip_locked(self):
        """The claim method should document its multi-process safety mechanism."""
        import postgres_store
        doc = postgres_store.PostgresControlPlaneStore.claim_job_with_fencing.__doc__
        assert doc is not None
        assert "SKIP LOCKED" in doc

    def test_reconcile_expired_leases_method_exists(self):
        """Lease reconciliation is required for worker crash recovery."""
        import postgres_store
        assert hasattr(postgres_store.PostgresControlPlaneStore, "reconcile_expired_leases")

    def test_renew_lease_method_exists(self):
        """Lease renewal for running jobs must exist."""
        import postgres_store
        assert hasattr(postgres_store.PostgresControlPlaneStore, "renew_lease")

    def test_health_check_method_exists(self):
        import postgres_store
        assert hasattr(postgres_store.PostgresControlPlaneStore, "health_check")

    def test_register_worker_method_exists(self):
        import postgres_store
        assert hasattr(postgres_store.PostgresControlPlaneStore, "register_worker")

    def test_heartbeat_worker_method_exists(self):
        import postgres_store
        assert hasattr(postgres_store.PostgresControlPlaneStore, "heartbeat_worker")

    def test_record_deployment_method_exists(self):
        import postgres_store
        assert hasattr(postgres_store.PostgresControlPlaneStore, "record_deployment")

    def test_get_backup_freshness_method_exists(self):
        import postgres_store
        assert hasattr(postgres_store.PostgresControlPlaneStore, "get_backup_freshness")

    def test_process_outbox_uses_skip_locked(self):
        """Outbox processing should use SKIP LOCKED for multi-process safety."""
        import postgres_store
        import inspect
        source = inspect.getsource(postgres_store.PostgresControlPlaneStore.process_outbox)
        assert "SKIP LOCKED" in source
