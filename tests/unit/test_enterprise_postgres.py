"""Tests for enterprise_postgres.py — Enterprise PostgreSQL Store with RLS."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from zcoder.domain.models.tenant import (
    ApiKey,
    EnterpriseRole,
    Organization,
    OrgStatus,
    Project,
    RequestContext,
)
from zcoder.infrastructure.stores.enterprise_postgres import (
    ENTERPRISE_PG_ROLES,
    ENTERPRISE_PG_SCHEMA,
    ENTERPRISE_RLS_DDL,
    EnterprisePostgresStore,
)


class TestEnterprisePostgresConstants:
    """Tests for SQL constant definitions."""

    def test_enterprise_pg_roles_contains_expected_roles(self) -> None:
        """Test that role definitions contain expected roles."""
        assert "zcoder_admin" in ENTERPRISE_PG_ROLES
        assert "zcoder_app" in ENTERPRISE_PG_ROLES
        assert "zcoder_readonly" in ENTERPRISE_PG_ROLES
        assert "CREATE ROLE" in ENTERPRISE_PG_ROLES

    def test_enterprise_pg_schema_contains_expected_tables(self) -> None:
        """Test that schema contains all expected tables."""
        expected_tables = [
            "organizations",
            "projects",
            "memberships",
            "service_accounts",
            "api_keys",
            "tenant_jobs",
            "tenant_job_idempotency",
            "usage_ledger",
            "tenant_quotas",
            "enterprise_audit",
        ]
        for table in expected_tables:
            assert table in ENTERPRISE_PG_SCHEMA

    def test_enterprise_rls_ddl_contains_expected_policies(self) -> None:
        """Test that RLS DDL contains expected policies."""
        expected_tables = [
            "projects",
            "memberships",
            "service_accounts",
            "api_keys",
            "tenant_jobs",
            "tenant_job_idempotency",
            "usage_ledger",
            "tenant_quotas",
            "enterprise_audit",
        ]
        for table in expected_tables:
            assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in ENTERPRISE_RLS_DDL
            assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in ENTERPRISE_RLS_DDL
            assert f"tenant_isolation_{table}" in ENTERPRISE_RLS_DDL

    def test_organizations_not_rls_scoped(self) -> None:
        """Test that organizations table is NOT RLS-scoped (for cross-org admin)."""
        assert (
            "organizations" not in ENTERPRISE_RLS_DDL
            or "tenant_isolation_organizations" not in ENTERPRISE_RLS_DDL
        )


class TestEnterprisePostgresStore:
    """Tests for EnterprisePostgresStore class."""

    @pytest.fixture
    def mock_pool(self) -> MagicMock:
        """Create a mock connection pool."""
        pool = MagicMock()
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cur
        pool.getconn.return_value = conn
        return pool

    @pytest.fixture
    def store(self, mock_pool: MagicMock) -> EnterprisePostgresStore:
        """Create a store with mocked pool."""
        with patch("psycopg2.pool.ThreadedConnectionPool", return_value=mock_pool):
            store = EnterprisePostgresStore(dsn="postgresql://test:test@localhost/test")
            store.pool = mock_pool
            # Reset mock to clear calls from init_schema
            mock_pool.getconn.return_value.cursor.return_value.__enter__.return_value.reset_mock()
            mock_pool.getconn.return_value.reset_mock()
            return store

    def test_init_sanitizes_dsn(self) -> None:
        """Test that DSN is sanitized on init."""
        with patch("psycopg2.pool.ThreadedConnectionPool"):
            with patch("zcoder.core.utils.sanitize_dsn", return_value="sanitized_dsn") as mock_sanitize:
                store = EnterprisePostgresStore(dsn="postgresql://user:pass@localhost/db")
                mock_sanitize.assert_called_once()
                assert store.dsn == "sanitized_dsn"

    def test_init_schema_executes_ddl(self, store: EnterprisePostgresStore, mock_pool: MagicMock) -> None:
        """Test that init_schema executes both schema and RLS DDL."""
        conn = mock_pool.getconn.return_value
        cur = conn.cursor.return_value.__enter__.return_value

        store.init_schema()

        # Should execute at least twice: once for schema, once for RLS
        # (schema DDL may execute multiple statements)
        assert cur.execute.call_count >= 2
        conn.commit.assert_called_once()

    def test_scoped_conn_sets_tenant_context(
        self, store: EnterprisePostgresStore, mock_pool: MagicMock
    ) -> None:
        """Test that scoped_conn sets app.current_org."""
        conn = mock_pool.getconn.return_value
        cur = conn.cursor.return_value.__enter__.return_value

        ctx = RequestContext(
            principal_id="user1",
            organization_id="org1",
            role=EnterpriseRole.OPERATOR,
        )

        with store.scoped_conn(ctx) as conn:
            pass  # Just test context manager

        # Check BEGIN and SET LOCAL were called
        execute_calls = [call[0][0] for call in cur.execute.call_args_list]
        assert "BEGIN" in execute_calls[0]
        assert "SET LOCAL app.current_org = %s" in execute_calls[1]
        # Check commit and reset
        assert conn.commit.called

    def test_scoped_conn_resets_on_exception(
        self, store: EnterprisePostgresStore, mock_pool: MagicMock
    ) -> None:
        """Test that scoped_conn rolls back and resets on exception."""
        conn = mock_pool.getconn.return_value
        cur = conn.cursor.return_value.__enter__.return_value

        ctx = RequestContext(
            principal_id="user1",
            organization_id="org1",
            role=EnterpriseRole.OPERATOR,
        )

        try:
            with store.scoped_conn(ctx):
                raise ValueError("test error")
        except ValueError:
            pass

        # Should rollback and reset
        conn.rollback.assert_called()
        # RESET should be attempted
        reset_calls = [call for call in cur.execute.call_args_list if "RESET app.current_org" in call[0][0]]
        assert len(reset_calls) > 0

    def test_create_organization(self, store: EnterprisePostgresStore, mock_pool: MagicMock) -> None:
        """Test create_organization."""
        conn = mock_pool.getconn.return_value
        cur = conn.cursor.return_value.__enter__.return_value

        ctx = RequestContext(
            principal_id="admin",
            organization_id="org1",
            role=EnterpriseRole.ORG_ADMIN,
            is_global_admin=True,
        )
        org = Organization(
            id="org1",
            name="Test Org",
            slug="test-org",
            status=OrgStatus.ACTIVE,
        )

        result = store.create_organization(ctx, org)

        assert result == org
        cur.execute.assert_called()
        conn.commit.assert_called()

    def test_create_organization_requires_permission(
        self, store: EnterprisePostgresStore, mock_pool: MagicMock
    ) -> None:
        """Test create_organization requires org.manage permission for non-admin."""

        ctx = RequestContext(
            principal_id="user1",
            organization_id="org1",
            role=EnterpriseRole.OPERATOR,  # No org.manage
        )
        org = Organization(
            id="org2",  # Different org
            name="Test Org",
            slug="test-org",
            status=OrgStatus.ACTIVE,
        )

        with pytest.raises(Exception, match="lacks required permission"):
            store.create_organization(ctx, org)

    def test_get_organization(self, store: EnterprisePostgresStore, mock_pool: MagicMock) -> None:
        """Test get_organization."""
        conn = mock_pool.getconn.return_value
        cur = conn.cursor.return_value.__enter__.return_value
        # metadata is stored as JSON string
        cur.fetchone.return_value = (
            "org1",
            "Test Org",
            "test-org",
            "ACTIVE",
            1234567890.0,
            '{"key": "value"}',
        )

        ctx = RequestContext(
            principal_id="user1",
            organization_id="org1",
            role=EnterpriseRole.OPERATOR,
        )

        result = store.get_organization(ctx, "org1")

        assert result is not None
        assert result.id == "org1"
        assert result.name == "Test Org"
        # metadata is returned as JSON string from DB
        assert result.metadata == '{"key": "value"}'

    def test_get_organization_not_found(self, store: EnterprisePostgresStore, mock_pool: MagicMock) -> None:
        """Test get_organization returns None when not found."""
        conn = mock_pool.getconn.return_value
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchone.return_value = None

        ctx = RequestContext(
            principal_id="user1",
            organization_id="org1",
            role=EnterpriseRole.OPERATOR,
        )

        result = store.get_organization(ctx, "org1")

        assert result is None

    def test_create_project(self, store: EnterprisePostgresStore, mock_pool: MagicMock) -> None:
        """Test create_project."""
        conn = mock_pool.getconn.return_value
        cur = conn.cursor.return_value.__enter__.return_value

        ctx = RequestContext(
            principal_id="user1",
            organization_id="org1",
            project_id="proj1",
            role=EnterpriseRole.PROJECT_ADMIN,  # Has project.manage
        )
        project = Project(
            id="proj1",
            organization_id="org1",
            name="Test Project",
            slug="test-project",
        )

        result = store.create_project(ctx, project)

        assert result == project
        cur.execute.assert_called()
        conn.commit.assert_called()

    def test_enqueue_job(self, store: EnterprisePostgresStore, mock_pool: MagicMock) -> None:
        """Test enqueue_job."""
        conn = mock_pool.getconn.return_value
        cur = conn.cursor.return_value.__enter__.return_value

        ctx = RequestContext(
            principal_id="user1",
            organization_id="org1",
            project_id="proj1",
            role=EnterpriseRole.OPERATOR,
        )

        from zcoder.services.agent_runtime import Job, JobStatus

        job = Job(
            id="job1",
            task="test task",
            runtime="direct",
            status=JobStatus.CREATED,
            workspace=".",
        )

        result = store.enqueue_job(ctx, job)

        assert result == job
        cur.execute.assert_called()
        conn.commit.assert_called()

    def test_enqueue_job_with_idempotency_key(
        self, store: EnterprisePostgresStore, mock_pool: MagicMock
    ) -> None:
        """Test enqueue_job with idempotency key."""
        conn = mock_pool.getconn.return_value
        cur = conn.cursor.return_value.__enter__.return_value
        # fetchone calls:
        # 1. Check existing idempotency -> None (no existing)
        # 2. After INSERT idempotency (ON CONFLICT DO NOTHING RETURNING) -> returns job_id (success)
        cur.fetchone.side_effect = [None, ("job1",)]

        ctx = RequestContext(
            principal_id="user1",
            organization_id="org1",
            project_id="proj1",
            role=EnterpriseRole.OPERATOR,
        )

        from zcoder.services.agent_runtime import Job, JobStatus

        job = Job(
            id="job1",
            task="test task",
            runtime="direct",
            status=JobStatus.CREATED,
            workspace=".",
        )

        result = store.enqueue_job(
            ctx,
            job,
            idempotency_key="idem1",
            request_fingerprint="fp1",
        )

        assert result == job
        # Should check idempotency, then insert job, then insert idempotency
        assert cur.execute.call_count >= 3
        conn.commit.assert_called()

    def test_enqueue_job_idempotency_conflict(
        self, store: EnterprisePostgresStore, mock_pool: MagicMock
    ) -> None:
        """Test enqueue_job raises on idempotency key conflict."""
        conn = mock_pool.getconn.return_value
        cur = conn.cursor.return_value.__enter__.return_value
        # Existing record with different fingerprint
        cur.fetchone.return_value = ("different_fp", "existing_job")

        ctx = RequestContext(
            principal_id="user1",
            organization_id="org1",
            project_id="proj1",
            role=EnterpriseRole.OPERATOR,
        )

        from zcoder.services.agent_runtime import Job, JobStatus

        job = Job(
            id="job1",
            task="test task",
            runtime="direct",
            status=JobStatus.CREATED,
            workspace=".",
        )

        from zcoder.domain.models.tenant import IdempotencyConflictError

        with pytest.raises(IdempotencyConflictError):
            store.enqueue_job(
                ctx,
                job,
                idempotency_key="idem1",
                request_fingerprint="fp1",
            )

    def test_get_job(self, store: EnterprisePostgresStore, mock_pool: MagicMock) -> None:
        """Test get_job."""
        conn = mock_pool.getconn.return_value
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchone.return_value = (
            "job1",
            "proj1",
            "test task",
            "direct",
            "CREATED",
            ".",
            1234567890.0,
            1234567890.0,
            "model1",
            0.0,
            0.0,
            "{}",
        )

        ctx = RequestContext(
            principal_id="user1",
            organization_id="org1",
            project_id="proj1",
            role=EnterpriseRole.OPERATOR,
        )

        result = store.get_job(ctx, "job1")

        assert result is not None
        assert result.id == "job1"
        assert result.task == "test task"

    def test_list_jobs(self, store: EnterprisePostgresStore, mock_pool: MagicMock) -> None:
        """Test list_jobs."""
        conn = mock_pool.getconn.return_value
        cur = conn.cursor.return_value.__enter__.return_value
        # First call: COUNT(*) -> fetchone
        # Second call: SELECT jobs -> fetchall
        cur.fetchone.return_value = (5,)  # count
        cur.fetchall.return_value = [
            ("job1", "proj1", "task1", "direct", "CREATED", ".", 1.0, 1.0, "m1", 0.0, 0.0, "{}"),
            ("job2", "proj1", "task2", "direct", "CREATED", ".", 1.0, 1.0, "m1", 0.0, 0.0, "{}"),
        ]

        ctx = RequestContext(
            principal_id="user1",
            organization_id="org1",
            project_id="proj1",
            role=EnterpriseRole.OPERATOR,
        )

        jobs, total = store.list_jobs(ctx, limit=10, offset=0)

        assert total == 5
        assert len(jobs) == 2

    def test_cancel_job(self, store: EnterprisePostgresStore, mock_pool: MagicMock) -> None:
        """Test cancel_job."""
        conn = mock_pool.getconn.return_value
        cur = conn.cursor.return_value.__enter__.return_value
        # First fetch: job exists and is RUNNING
        cur.fetchone.return_value = (
            "job1",
            "proj1",
            "test task",
            "direct",
            "RUNNING",
            ".",
            1234567890.0,
            1234567890.0,
            "model1",
            0.0,
            0.0,
            "{}",
        )
        # Update returns 1 row affected
        cur.rowcount = 1

        ctx = RequestContext(
            principal_id="user1",
            organization_id="org1",
            project_id="proj1",
            role=EnterpriseRole.OPERATOR,
        )

        result = store.cancel_job(ctx, "job1")

        assert result is not None
        assert result.status.value == "CANCELLED"
        cur.execute.assert_called()
        conn.commit.assert_called()

    def test_cancel_job_not_found(self, store: EnterprisePostgresStore, mock_pool: MagicMock) -> None:
        """Test cancel_job returns None when job not found."""
        conn = mock_pool.getconn.return_value
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchone.return_value = None

        ctx = RequestContext(
            principal_id="user1",
            organization_id="org1",
            project_id="proj1",
            role=EnterpriseRole.OPERATOR,
        )

        result = store.cancel_job(ctx, "nonexistent")

        assert result is None

    def test_claim_job_scoped(self, store: EnterprisePostgresStore, mock_pool: MagicMock) -> None:
        """Test claim_job_scoped."""
        conn = mock_pool.getconn.return_value
        cur = conn.cursor.return_value.__enter__.return_value
        # First fetch: job available
        cur.fetchone.return_value = (
            "job1",
            "proj1",
            "test task",
            "direct",
            "READY",
            ".",
            1234567890.0,
            1234567890.0,
            "model1",
            0.0,
            0.0,
            0,
            "{}",
        )
        # Update returns 1 row affected
        cur.rowcount = 1

        ctx = RequestContext(
            principal_id="user1",
            organization_id="org1",
            project_id="proj1",
            role=EnterpriseRole.OPERATOR,
        )

        result = store.claim_job_scoped(ctx, "worker1", 120.0)

        assert result is not None
        job, gen = result
        assert job.id == "job1"
        assert gen == 1

    def test_claim_job_scoped_none_available(
        self, store: EnterprisePostgresStore, mock_pool: MagicMock
    ) -> None:
        """Test claim_job_scoped returns None when no jobs available."""
        conn = mock_pool.getconn.return_value
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchone.return_value = None

        ctx = RequestContext(
            principal_id="user1",
            organization_id="org1",
            project_id="proj1",
            role=EnterpriseRole.OPERATOR,
        )

        result = store.claim_job_scoped(ctx, "worker1", 120.0)

        assert result is None

    def test_mutate_job_scoped(self, store: EnterprisePostgresStore, mock_pool: MagicMock) -> None:
        """Test mutate_job_scoped."""
        conn = mock_pool.getconn.return_value
        cur = conn.cursor.return_value.__enter__.return_value
        cur.rowcount = 1

        ctx = RequestContext(
            principal_id="user1",
            organization_id="org1",
            project_id="proj1",
            role=EnterpriseRole.OPERATOR,
        )

        from zcoder.services.agent_runtime import JobStatus

        result = store.mutate_job_scoped(ctx, "job1", "worker1", 1, JobStatus.SUCCEEDED, 0.5)

        assert result is True
        cur.execute.assert_called()
        conn.commit.assert_called()

    def test_mutate_job_scoped_fails_on_wrong_generation(
        self, store: EnterprisePostgresStore, mock_pool: MagicMock
    ) -> None:
        """Test mutate_job_scoped fails when fencing token doesn't match."""
        conn = mock_pool.getconn.return_value
        cur = conn.cursor.return_value.__enter__.return_value
        cur.rowcount = 0  # No rows updated

        ctx = RequestContext(
            principal_id="user1",
            organization_id="org1",
            project_id="proj1",
            role=EnterpriseRole.OPERATOR,
        )

        from zcoder.services.agent_runtime import JobStatus

        result = store.mutate_job_scoped(ctx, "job1", "worker1", 1, JobStatus.SUCCEEDED, 0.5)

        assert result is False

    def test_renew_lease(self, store: EnterprisePostgresStore, mock_pool: MagicMock) -> None:
        """Test renew_lease."""
        conn = mock_pool.getconn.return_value
        cur = conn.cursor.return_value.__enter__.return_value
        cur.rowcount = 1

        ctx = RequestContext(
            principal_id="user1",
            organization_id="org1",
            project_id="proj1",
            role=EnterpriseRole.OPERATOR,
        )

        result = store.renew_lease(ctx, "job1", "worker1", 1, 120.0)

        assert result is True
        cur.execute.assert_called()
        conn.commit.assert_called()

    def test_save_api_key(self, store: EnterprisePostgresStore, mock_pool: MagicMock) -> None:
        """Test save_api_key."""
        conn = mock_pool.getconn.return_value
        cur = conn.cursor.return_value.__enter__.return_value

        ctx = RequestContext(
            principal_id="admin",
            organization_id="org1",
            role=EnterpriseRole.ORG_ADMIN,
        )
        key = ApiKey(
            id="key1",
            prefix="zc_test",
            secret_hash="hash123",
            organization_id="org1",
            project_id="proj1",
            principal_id="user1",
            scopes=["read", "write"],
        )

        store.save_api_key(ctx, key)

        cur.execute.assert_called()
        conn.commit.assert_called()

    def test_authenticate_api_key(self, store: EnterprisePostgresStore, mock_pool: MagicMock) -> None:
        """Test authenticate_api_key - success case."""
        conn = mock_pool.getconn.return_value
        cur = conn.cursor.return_value.__enter__.return_value
        # First _raw_conn: find org by prefix -> fetchall returns org
        # Then scoped_conn: find api_key -> fetchone returns key
        # We need to handle multiple cursors, so use side_effect on fetchall/fetchone
        cur.fetchall.return_value = [("org1",)]  # First query: org by prefix
        cur.fetchone.return_value = (
            "key1",
            "org1",
            "proj1",
            "user1",
            '["read"]',
            "ACTIVE",
            None,
        )  # Second query: api key

        ctx = store.authenticate_api_key("zc_test_org1_key123")

        assert ctx is not None
        assert ctx.organization_id == "org1"
        assert ctx.principal_id == "user1"

    def test_authenticate_api_key_not_found(
        self, store: EnterprisePostgresStore, mock_pool: MagicMock
    ) -> None:
        """Test authenticate_api_key returns None when key not found."""
        conn = mock_pool.getconn.return_value
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchone.return_value = None

        ctx = store.authenticate_api_key("zc_test_org1_invalid")

        assert ctx is None

    def test_record_usage_event(self, store: EnterprisePostgresStore, mock_pool: MagicMock) -> None:
        """Test record_usage_event."""
        conn = mock_pool.getconn.return_value
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchone.return_value = ("usage1",)  # Inserted successfully

        from zcoder.domain.models.tenant import UsageEvent

        ctx = RequestContext(
            principal_id="user1",
            organization_id="org1",
            project_id="proj1",
            role=EnterpriseRole.OPERATOR,
        )
        event = UsageEvent(
            id="usage1",
            organization_id="org1",
            project_id="proj1",
            job_id="job1",
            metric="tokens",
            quantity=1000,
            unit="count",
            cost_usd=0.01,
        )

        result = store.record_usage_event(ctx, event)

        assert result is True
        cur.execute.assert_called()
        conn.commit.assert_called()

    def test_check_and_reserve_quota_new_quota(
        self, store: EnterprisePostgresStore, mock_pool: MagicMock
    ) -> None:
        """Test check_and_reserve_quota creates new quota if not exists."""
        conn = mock_pool.getconn.return_value
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchone.return_value = None  # No existing quota

        ctx = RequestContext(
            principal_id="user1",
            organization_id="org1",
            role=EnterpriseRole.OPERATOR,
        )

        result = store.check_and_reserve_quota(ctx, "tokens", 100, 1000.0)

        assert result is True
        # Should insert new quota
        assert cur.execute.call_count >= 2
        conn.commit.assert_called()

    def test_check_and_reserve_quota_existing_within_limit(
        self, store: EnterprisePostgresStore, mock_pool: MagicMock
    ) -> None:
        """Test check_and_reserve_quota reserves when within limit."""
        conn = mock_pool.getconn.return_value
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchone.return_value = (500.0, 1000.0)  # current=500, limit=1000
        cur.rowcount = 1

        ctx = RequestContext(
            principal_id="user1",
            organization_id="org1",
            role=EnterpriseRole.OPERATOR,
        )

        result = store.check_and_reserve_quota(ctx, "tokens", 100, 1000.0)

        assert result is True
        conn.commit.assert_called()

    def test_check_and_reserve_quota_exceeds_limit(
        self, store: EnterprisePostgresStore, mock_pool: MagicMock
    ) -> None:
        """Test check_and_reserve_quota returns False when limit exceeded."""
        conn = mock_pool.getconn.return_value
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchone.return_value = (950.0, 1000.0)  # current=950, limit=1000

        ctx = RequestContext(
            principal_id="user1",
            organization_id="org1",
            role=EnterpriseRole.OPERATOR,
        )

        result = store.check_and_reserve_quota(ctx, "tokens", 100, 1000.0)

        assert result is False

    def test_record_audit_event(self, store: EnterprisePostgresStore, mock_pool: MagicMock) -> None:
        """Test record_audit_event."""
        conn = mock_pool.getconn.return_value
        cur = conn.cursor.return_value.__enter__.return_value

        from zcoder.domain.models.tenant import EnterpriseAuditEvent

        event = EnterpriseAuditEvent(
            event_id="audit1",
            organization_id="org1",
            actor="user1",
            actor_type="USER",
            action="job.create",
            resource="job1",
            result="SUCCESS",
            timestamp=1234567890.0,
        )

        store.record_audit_event(event)

        cur.execute.assert_called()
        conn.commit.assert_called()

    def test_export_audit_log(self, store: EnterprisePostgresStore, mock_pool: MagicMock) -> None:
        """Test export_audit_log."""
        conn = mock_pool.getconn.return_value
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchall.return_value = [
            ("audit1", "org1", "user1", "USER", "job.create", "job1", "SUCCESS", 1234567890.0, "{}", "1.0"),
        ]

        ctx = RequestContext(
            principal_id="admin",
            organization_id="org1",
            role=EnterpriseRole.ORG_ADMIN,
        )

        result = store.export_audit_log(ctx, limit=10)

        assert len(result) == 1
        assert result[0]["event_id"] == "audit1"
        assert result[0]["actor"] == "user1"

    def test_verify_rls_policies(self, store: EnterprisePostgresStore, mock_pool: MagicMock) -> None:
        """Test verify_rls_policies."""
        conn = mock_pool.getconn.return_value
        cur = conn.cursor.return_value.__enter__.return_value
        # First query: pg_class
        cur.fetchall.side_effect = [
            [("projects", True, True), ("memberships", True, True)],
            [
                (
                    "projects",
                    "tenant_isolation_projects",
                    "ALL",
                    "organization_id = current_setting('app.current_org', true)",
                ),
                (
                    "memberships",
                    "tenant_isolation_memberships",
                    "ALL",
                    "organization_id = current_setting('app.current_org', true)",
                ),
            ],
        ]

        result = store.verify_rls_policies()

        assert "projects" in result
        assert result["projects"]["rls_enabled"] is True
        assert result["projects"]["force_rls"] is True
        assert len(result["projects"]["policies"]) == 1

    def test_verify_app_role_cannot_bypass_rls(
        self, store: EnterprisePostgresStore, mock_pool: MagicMock
    ) -> None:
        """Test verify_app_role_cannot_bypass_rls."""
        conn = mock_pool.getconn.return_value
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchone.return_value = (False, True, False)  # not superuser, inherit, not bypassrls

        result = store.verify_app_role_cannot_bypass_rls()

        assert result["exists"] is True
        assert result["superuser"] is False
        assert result["bypassrls"] is False

    def test_verify_app_role_not_exists(self, store: EnterprisePostgresStore, mock_pool: MagicMock) -> None:
        """Test verify_app_role_cannot_bypass_rls when role doesn't exist."""
        conn = mock_pool.getconn.return_value
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchone.return_value = None

        result = store.verify_app_role_cannot_bypass_rls()

        assert result["exists"] is False

    def test_verify_table_rls_enabled(self, store: EnterprisePostgresStore, mock_pool: MagicMock) -> None:
        """Test verify_table_rls_enabled."""
        conn = mock_pool.getconn.return_value
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchone.return_value = (True, True)

        rls_enabled, force_rls = store.verify_table_rls_enabled("projects")

        assert rls_enabled is True
        assert force_rls is True

    def test_verify_policy_count(self, store: EnterprisePostgresStore, mock_pool: MagicMock) -> None:
        """Test verify_policy_count."""
        conn = mock_pool.getconn.return_value
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchone.return_value = (1,)

        count = store.verify_policy_count("projects")

        assert count == 1

    def test_close(self, store: EnterprisePostgresStore, mock_pool: MagicMock) -> None:
        """Test close."""
        store.close()
        mock_pool.closeall.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
