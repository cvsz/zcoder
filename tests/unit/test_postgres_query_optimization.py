"""tests/unit/test_postgres_query_optimization.py — Performance tests for PostgreSQL query optimization."""

from __future__ import annotations

import os

import pytest

from zcoder.domain.models.legacy_job import Job, JobStatus
from zcoder.infrastructure.stores.postgres import PostgresControlPlaneStore

TEST_DSN = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


@pytest.fixture(scope="function")
def pg_store():
    """Create a store with test DSN."""
    if not TEST_DSN:
        pytest.skip("TEST_DATABASE_URL not set")
    store = PostgresControlPlaneStore(dsn=TEST_DSN, min_conn=2, max_conn=10)
    store.init_schema()
    # Clean up any existing jobs
    with store._get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM jobs")
    yield store
    store.close()


class TestPreparedStatements:
    """Tests for prepared statement caching."""

    def test_prepare_and_execute(self, pg_store):
        """Test that prepare() creates and caches prepared statements."""
        # First prepare
        stmt_name = pg_store.prepare("test_select", "SELECT 1 as val")
        assert stmt_name == "test_select"

        # Execute prepared statement
        with pg_store._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("EXECUTE test_select")
                row = cur.fetchone()
                assert row[0] == 1

    def test_prepared_statement_cached(self, pg_store):
        """Test that same query uses cached prepared statement."""
        pg_store.prepare("cached_query", "SELECT 42 as answer")

        # Check internal cache
        assert "cached_query" in pg_store._prepared_statements
        assert pg_store._prepared_statements["cached_query"] == "SELECT 42 as answer"

    def test_prepare_idempotent(self, pg_store):
        """Test that preparing same statement twice is idempotent."""
        name1 = pg_store.prepare("idempotent", "SELECT 'test'")
        name2 = pg_store.prepare("idempotent", "SELECT 'test'")
        assert name1 == name2 == "idempotent"

    def test_execute_prepared_with_params(self, pg_store):
        """Test executing prepared statement with parameters."""
        pg_store.prepare("param_query", "SELECT %s as val")

        rows = pg_store.execute_prepared("param_query", ("hello",))
        assert len(rows) == 1
        assert rows[0][0] == "hello"


class TestQueryPlanAnalysis:
    """Tests for EXPLAIN ANALYZE functionality."""

    def test_explain_analyze_simple(self, pg_store):
        """Test explain_analyze returns query plan."""
        # Insert some test data first
        for i in range(10):
            job = Job(
                id=f"explain_job_{i}",
                task=f"Task {i}",
                runtime="direct",
                status=JobStatus.READY,
            )
            pg_store.enqueue_job(job)

        plan = pg_store.explain_analyze("SELECT * FROM jobs WHERE status = 'READY' LIMIT 5")
        assert isinstance(plan, str)
        assert len(plan) > 0
        # Should contain query plan output
        assert "Seq Scan" in plan or "Index Scan" in plan or "Limit" in plan

    def test_explain_analyze_with_params(self, pg_store):
        """Test explain_analyze with parameterized query."""
        plan = pg_store.explain_analyze("SELECT * FROM jobs WHERE status = %s", ("READY",))
        assert isinstance(plan, str)
        assert len(plan) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
