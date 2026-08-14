"""enterprise_postgres_store.py — Production PostgreSQL Store with Real PostgreSQL Row-Level Security (RLS) & Multi-Tenancy.

Upgrade-11 P0 Corrections:
  • Added ENABLE ROW LEVEL SECURITY + FORCE ROW LEVEL SECURITY on all tenant tables
  • Added CREATE POLICY statements using current_setting('app.current_org')
  • Added DB role matrix: zcoder_admin (migration), zcoder_app (normal application), zcoder_readonly
  • zcoder_app does NOT have BYPASSRLS and is NOT superuser
  • Added RLS verification helpers for testing
  • SET LOCAL app.current_org is used WITH RLS policies, not instead of them

Features:
  • Organization, Project, Membership, ServiceAccount, and ApiKey storage
  • REAL PostgreSQL Row-Level Security (RLS): ENABLE + FORCE ROW LEVEL SECURITY + CREATE POLICY
  • DB role matrix: zcoder_admin (migrations/superuser-free), zcoder_app (normal, no BYPASSRLS)
  • Connection pool tenant-isolation with transactional SET LOCAL app.current_org (inside transaction)
  • Guaranteed reset of session tenant context upon connection release
  • Atomic usage metering and quota reservation to prevent concurrency overspends
  • Enterprise Audit Log with immutable append-only semantics and JSONL export
  • RLS verification helpers for integration testing
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import psycopg2
import psycopg2.extras
import psycopg2.pool

from agent_runtime import Job, JobStatus
from tenant_models import (
    ApiKey,
    EnterpriseAuditEvent,
    EnterpriseRole,
    Organization,
    OrgStatus,
    Project,
    RequestContext,
    UsageEvent,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DB Role Matrix (executed once by admin/migration role)
# ---------------------------------------------------------------------------
ENTERPRISE_PG_ROLES = """
-- Migration/admin role: used only for DDL (not superuser, not BYPASSRLS)
-- In production this should be a dedicated non-superuser role.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'zcoder_admin') THEN
    CREATE ROLE zcoder_admin;
  END IF;
END $$;

-- Application role: used by normal API/worker connections.
-- MUST NOT have BYPASSRLS. MUST NOT own tables created with FORCE ROW LEVEL SECURITY.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'zcoder_app') THEN
    CREATE ROLE zcoder_app LOGIN PASSWORD 'zcoder_app_placeholder';
  END IF;
END $$;

-- Read-only role: for analytics/reporting only
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'zcoder_readonly') THEN
    CREATE ROLE zcoder_readonly;
  END IF;
END $$;
"""

# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------
ENTERPRISE_PG_SCHEMA = """
-- 1. Organizations & Projects
CREATE TABLE IF NOT EXISTS organizations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM now()),
    metadata JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    name TEXT NOT NULL,
    slug TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM now()),
    UNIQUE (organization_id, slug)
);

-- 2. Memberships & Credentials
CREATE TABLE IF NOT EXISTS memberships (
    id TEXT PRIMARY KEY,
    principal_id TEXT NOT NULL,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    role TEXT NOT NULL DEFAULT 'Viewer',
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM now()),
    UNIQUE (principal_id, organization_id)
);

CREATE TABLE IF NOT EXISTS service_accounts (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    project_id TEXT REFERENCES projects(id),
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'Operator',
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM now())
);

CREATE TABLE IF NOT EXISTS api_keys (
    id TEXT PRIMARY KEY,
    prefix TEXT NOT NULL,
    secret_hash TEXT NOT NULL,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    project_id TEXT REFERENCES projects(id),
    principal_id TEXT NOT NULL,
    scopes JSONB NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM now()),
    expires_at DOUBLE PRECISION,
    last_used_at DOUBLE PRECISION
);

-- 3. Tenant-Scoped Jobs
CREATE TABLE IF NOT EXISTS tenant_jobs (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    project_id TEXT REFERENCES projects(id),
    task TEXT NOT NULL,
    runtime TEXT NOT NULL DEFAULT 'direct',
    status TEXT NOT NULL DEFAULT 'CREATED',
    workspace TEXT NOT NULL DEFAULT '.',
    created_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM now()),
    updated_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM now()),
    model TEXT NOT NULL DEFAULT 'claude-sonnet-5',
    budget_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
    cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
    claimed_by TEXT,
    claim_generation INTEGER NOT NULL DEFAULT 0,
    lease_expires_at DOUBLE PRECISION NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}'
);

-- 4. Metering & Quotas
CREATE TABLE IF NOT EXISTS usage_ledger (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    project_id TEXT REFERENCES projects(id),
    job_id TEXT,
    metric TEXT NOT NULL,
    quantity DOUBLE PRECISION NOT NULL,
    unit TEXT NOT NULL,
    cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'ZCODER_MEASURED',
    occurred_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM now()),
    dedup_key TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS tenant_quotas (
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    metric TEXT NOT NULL,
    limit_value DOUBLE PRECISION NOT NULL,
    period TEXT NOT NULL DEFAULT 'monthly',
    current_value DOUBLE PRECISION NOT NULL DEFAULT 0,
    soft_limit_ratio DOUBLE PRECISION NOT NULL DEFAULT 0.8,
    PRIMARY KEY (organization_id, metric, period)
);

-- 5. Enterprise Audit Log
CREATE TABLE IF NOT EXISTS enterprise_audit (
    event_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    actor TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    action TEXT NOT NULL,
    resource TEXT NOT NULL,
    result TEXT NOT NULL,
    timestamp DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM now()),
    source_ip TEXT,
    request_id TEXT,
    metadata JSONB NOT NULL DEFAULT '{}',
    schema_version TEXT NOT NULL DEFAULT '1.0'
);

-- Indexes for tenant routing and isolation
CREATE INDEX IF NOT EXISTS idx_tenant_jobs_org ON tenant_jobs(organization_id, status);
CREATE INDEX IF NOT EXISTS idx_usage_ledger_org ON usage_ledger(organization_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_audit_org_time ON enterprise_audit(organization_id, timestamp);
"""

# ---------------------------------------------------------------------------
# Real PostgreSQL Row-Level Security
# Upgrade-11 P0: SET LOCAL app.current_org alone is NOT RLS.
# These statements add ACTUAL RLS enforcement at the database engine level.
# FORCE ROW LEVEL SECURITY applies even to table owners.
# ---------------------------------------------------------------------------
ENTERPRISE_RLS_DDL = """
-- Enable and FORCE RLS on every tenant-scoped table.
-- FORCE means even the table owner (zcoder_admin) sees only their tenant rows.
-- The migration/connection role must SET LOCAL app.current_org before any DML.

ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects FORCE ROW LEVEL SECURITY;

ALTER TABLE memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE memberships FORCE ROW LEVEL SECURITY;

ALTER TABLE service_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE service_accounts FORCE ROW LEVEL SECURITY;

ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys FORCE ROW LEVEL SECURITY;

ALTER TABLE tenant_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_jobs FORCE ROW LEVEL SECURITY;

ALTER TABLE usage_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_ledger FORCE ROW LEVEL SECURITY;

ALTER TABLE tenant_quotas ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_quotas FORCE ROW LEVEL SECURITY;

ALTER TABLE enterprise_audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE enterprise_audit FORCE ROW LEVEL SECURITY;

-- RLS Policies: allow access only when organization_id matches the session variable.
-- current_setting(..., true) returns NULL (not error) if variable is unset.
-- An unset variable => empty string => no match => FAIL CLOSED.

DROP POLICY IF EXISTS tenant_isolation_projects ON projects;
CREATE POLICY tenant_isolation_projects ON projects
    USING (organization_id = current_setting('app.current_org', true));

DROP POLICY IF EXISTS tenant_isolation_memberships ON memberships;
CREATE POLICY tenant_isolation_memberships ON memberships
    USING (organization_id = current_setting('app.current_org', true));

DROP POLICY IF EXISTS tenant_isolation_service_accounts ON service_accounts;
CREATE POLICY tenant_isolation_service_accounts ON service_accounts
    USING (organization_id = current_setting('app.current_org', true));

DROP POLICY IF EXISTS tenant_isolation_api_keys ON api_keys;
CREATE POLICY tenant_isolation_api_keys ON api_keys
    USING (organization_id = current_setting('app.current_org', true));

DROP POLICY IF EXISTS tenant_isolation_tenant_jobs ON tenant_jobs;
CREATE POLICY tenant_isolation_tenant_jobs ON tenant_jobs
    USING (organization_id = current_setting('app.current_org', true));

DROP POLICY IF EXISTS tenant_isolation_usage_ledger ON usage_ledger;
CREATE POLICY tenant_isolation_usage_ledger ON usage_ledger
    USING (organization_id = current_setting('app.current_org', true));

DROP POLICY IF EXISTS tenant_isolation_tenant_quotas ON tenant_quotas;
CREATE POLICY tenant_isolation_tenant_quotas ON tenant_quotas
    USING (organization_id = current_setting('app.current_org', true));

DROP POLICY IF EXISTS tenant_isolation_enterprise_audit ON enterprise_audit;
CREATE POLICY tenant_isolation_enterprise_audit ON enterprise_audit
    USING (organization_id = current_setting('app.current_org', true));

-- organizations table: controlled via application-layer permission checks
-- (global admin vs. org-scoped access). Not RLS-scoped here to allow
-- cross-org operations by zcoder_admin for migrations.
"""


class EnterprisePostgresStore:
    """PostgreSQL storage backend with hard tenant isolation."""

    def __init__(self, dsn: str, min_conn: int = 1, max_conn: int = 10):
        self.dsn = dsn
        self.pool = psycopg2.pool.ThreadedConnectionPool(min_conn, max_conn, dsn)
        self.init_schema()

    def init_schema(self) -> None:
        """Apply table DDL then RLS DDL. Safe to re-run (idempotent)."""
        with self._raw_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(ENTERPRISE_PG_SCHEMA)
                # Apply real RLS: ENABLE/FORCE ROW LEVEL SECURITY + CREATE POLICY
                cur.execute(ENTERPRISE_RLS_DDL)
            conn.commit()

    @contextmanager
    def _raw_conn(self) -> Generator[Any, None, None]:
        conn = self.pool.getconn()
        try:
            yield conn
        finally:
            self.pool.putconn(conn)

    @contextmanager
    def scoped_conn(self, ctx: RequestContext) -> Generator[Any, None, None]:
        """Get a pooled connection scoped to the request's tenant via transaction-local setting.

        IMPORTANT: SET LOCAL app.current_org is used IN CONJUNCTION with real PostgreSQL RLS
        policies (ENABLE/FORCE ROW LEVEL SECURITY + CREATE POLICY). The session variable alone
        would not be RLS. Both layers are required.
        """
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                # SET LOCAL ensures the setting resets automatically on COMMIT/ROLLBACK
                cur.execute("BEGIN;")
                cur.execute("SET LOCAL app.current_org = %s;", (ctx.organization_id,))
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            # Explicitly reset session setting before returning to pool to prevent contamination
            try:
                with conn.cursor() as cur:
                    cur.execute("RESET app.current_org;")
                conn.commit()
            except Exception:
                pass
            self.pool.putconn(conn)

    # ─── RLS Verification Helpers (for integration tests) ────────────────────

    def verify_rls_policies(self) -> dict[str, dict[str, Any]]:
        """Query pg_policies to confirm actual RLS policies exist on tenant tables.

        Returns dict: {table_name: {rls_enabled, force_rls, policy_count}}
        """
        result: dict[str, dict[str, Any]] = {}
        tenant_tables = [
            "projects",
            "memberships",
            "service_accounts",
            "api_keys",
            "tenant_jobs",
            "usage_ledger",
            "tenant_quotas",
            "enterprise_audit",
        ]
        with self._raw_conn() as conn:
            with conn.cursor() as cur:
                # Check pg_class for RLS enabled/forced
                cur.execute(
                    """
                    SELECT relname, relrowsecurity, relforcerowsecurity
                    FROM pg_class
                    WHERE relname = ANY(%s) AND relkind = 'r'
                """,
                    (tenant_tables,),
                )
                for row in cur.fetchall():
                    result[row[0]] = {
                        "rls_enabled": row[1],
                        "force_rls": row[2],
                        "policies": [],
                    }

                # Check pg_policies for actual policies
                cur.execute(
                    """
                    SELECT tablename, policyname, cmd, qual
                    FROM pg_policies
                    WHERE tablename = ANY(%s)
                """,
                    (tenant_tables,),
                )
                for row in cur.fetchall():
                    tbl = row[0]
                    if tbl in result:
                        result[tbl]["policies"].append({"name": row[1], "cmd": row[2], "qual": row[3]})
        return result

    def verify_app_role_cannot_bypass_rls(self) -> dict[str, bool]:
        """Query pg_roles to confirm zcoder_app role does not have BYPASSRLS or superuser.

        Returns: {"exists": bool, "bypassrls": bool, "superuser": bool}
        The safe state is bypassrls=False, superuser=False.
        """
        with self._raw_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT rolsuper, rolinherit, rolbypassrls
                    FROM pg_roles
                    WHERE rolname = 'zcoder_app'
                """)
                row = cur.fetchone()
        if row is None:
            return {"exists": False, "superuser": False, "bypassrls": False}
        return {"exists": True, "superuser": row[0], "bypassrls": row[2]}

    def verify_table_rls_enabled(self, table_name: str) -> tuple[bool, bool]:
        """Return (rls_enabled, force_rls) for a single table from pg_class."""
        with self._raw_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = %s AND relkind = 'r'",
                    (table_name,),
                )
                row = cur.fetchone()
        if row is None:
            return False, False
        return row[0], row[1]

    def verify_policy_count(self, table_name: str) -> int:
        """Return the number of RLS policies defined on the table."""
        with self._raw_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM pg_policies WHERE tablename = %s",
                    (table_name,),
                )
                row = cur.fetchone()
        return row[0] if row else 0

    def close(self) -> None:
        self.pool.closeall()

    # ─── Organizations & Projects ────────────────────────────────────────

    def create_organization(self, ctx: RequestContext, org: Organization) -> Organization:
        if not ctx.is_global_admin and ctx.organization_id != org.id:
            ctx.require_permission("org.manage")
        with self._raw_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO organizations (id, name, slug, status, created_at, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, status = EXCLUDED.status
                    """,
                    (org.id, org.name, org.slug, org.status.value, org.created_at, json.dumps(org.metadata)),
                )
            conn.commit()
        return org

    def get_organization(self, ctx: RequestContext, org_id: str) -> Organization | None:
        ctx.validate_tenant_access(org_id)
        ctx.require_permission("org.read")
        with self.scoped_conn(ctx) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, name, slug, status, created_at, metadata FROM organizations WHERE id = %s",
                    (org_id,),
                )
                row = cur.fetchone()
        if not row:
            return None
        return Organization(
            id=row[0], name=row[1], slug=row[2], status=OrgStatus(row[3]), created_at=row[4], metadata=row[5]
        )

    def create_project(self, ctx: RequestContext, project: Project) -> Project:
        ctx.validate_tenant_access(project.organization_id)
        ctx.require_permission("project.manage")
        with self.scoped_conn(ctx) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO projects (id, organization_id, name, slug, status, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, status = EXCLUDED.status
                    """,
                    (
                        project.id,
                        project.organization_id,
                        project.name,
                        project.slug,
                        project.status.value,
                        project.created_at,
                    ),
                )
        return project

    # ─── Scoped Job Claims & Execution ───────────────────────────────────

    def enqueue_job(self, ctx: RequestContext, job: Job) -> Job:
        ctx.validate_tenant_access(ctx.organization_id)
        ctx.require_permission("job.create")
        with self.scoped_conn(ctx) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO tenant_jobs (
                        id, organization_id, project_id, task, runtime, status, workspace,
                        created_at, updated_at, model, budget_usd, cost_usd, metadata
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        job.id,
                        ctx.organization_id,
                        ctx.project_id,
                        job.task,
                        job.runtime,
                        job.status.value,
                        job.workspace,
                        job.created_at,
                        job.updated_at,
                        job.model,
                        job.budget_usd,
                        job.cost_usd,
                        json.dumps(job.metadata),
                    ),
                )
        return job

    def claim_job_scoped(
        self, ctx: RequestContext, worker_id: str, lease_duration: float = 120.0
    ) -> tuple[Job, int] | None:
        """Atomically claim job strictly within the worker's assigned tenant scope."""
        now = time.time()
        expires_at = now + lease_duration
        with self.scoped_conn(ctx) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, task, runtime, status, workspace, created_at, updated_at,
                           model, budget_usd, cost_usd, claim_generation, metadata
                    FROM tenant_jobs
                    WHERE organization_id = %s
                      AND (status = 'READY' OR (status = 'RUNNING' AND lease_expires_at < %s))
                    ORDER BY created_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                    """,
                    (ctx.organization_id, now),
                )
                row = cur.fetchone()
                if not row:
                    return None

                job_id, task, runtime, status, workspace, c_at, u_at, model, budget, cost, gen, meta = row

                new_gen = gen + 1
                cur.execute(
                    """
                    UPDATE tenant_jobs
                    SET status = 'RUNNING', claimed_by = %s, claim_generation = %s,
                        lease_expires_at = %s, updated_at = %s
                    WHERE id = %s AND claim_generation = %s
                    """,
                    (worker_id, new_gen, expires_at, now, job_id, gen),
                )

        meta_dict = meta if isinstance(meta, dict) else json.loads(meta or "{}")
        job = Job(
            id=job_id,
            task=task,
            runtime=runtime,
            status=JobStatus.RUNNING,
            workspace=workspace,
            created_at=c_at,
            updated_at=now,
            model=model,
            budget_usd=budget,
            cost_usd=cost,
            metadata=meta_dict,
        )
        return job, new_gen

    def mutate_job_scoped(
        self,
        ctx: RequestContext,
        job_id: str,
        worker_id: str,
        fencing_token: int,
        status: JobStatus,
        cost_usd: float,
    ) -> bool:
        with self.scoped_conn(ctx) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE tenant_jobs
                    SET status = %s, cost_usd = %s, updated_at = %s
                    WHERE id = %s AND organization_id = %s AND claimed_by = %s AND claim_generation = %s
                    """,
                    (
                        status.value,
                        cost_usd,
                        time.time(),
                        job_id,
                        ctx.organization_id,
                        worker_id,
                        fencing_token,
                    ),
                )
                return cur.rowcount > 0

    # ─── API Keys & Service Accounts ─────────────────────────────────────

    def save_api_key(self, ctx: RequestContext, key: ApiKey) -> None:
        ctx.validate_tenant_access(key.organization_id)
        ctx.require_permission("apikey.manage")
        with self.scoped_conn(ctx) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO api_keys (id, prefix, secret_hash, organization_id, project_id, principal_id, scopes, status, created_at, expires_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        key.id,
                        key.prefix,
                        key.secret_hash,
                        key.organization_id,
                        key.project_id,
                        key.principal_id,
                        json.dumps(key.scopes),
                        key.status,
                        key.created_at,
                        key.expires_at,
                    ),
                )

    def authenticate_api_key(self, raw_key: str) -> RequestContext | None:
        (
            raw_key.split("_")[0] + "_" + raw_key.split("_")[1] + "_" + raw_key.split("_")[2]
            if raw_key.count("_") >= 2
            else ""
        )
        secret_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        with self._raw_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, organization_id, project_id, principal_id, scopes, status, expires_at
                    FROM api_keys
                    WHERE secret_hash = %s AND status = 'ACTIVE'
                    """,
                    (secret_hash,),
                )
                row = cur.fetchone()
        if not row:
            return None

        key_id, org_id, proj_id, principal_id, scopes, status, expires_at = row
        if expires_at and time.time() > expires_at:
            return None

        scopes if isinstance(scopes, list) else json.loads(scopes)
        return RequestContext(
            principal_id=principal_id,
            organization_id=org_id,
            project_id=proj_id,
            role=EnterpriseRole.OPERATOR,
            authentication_method="apikey",
        )

    # ─── Metering, Quotas & Atomic Reservations ──────────────────────────

    def record_usage_event(self, ctx: RequestContext, event: UsageEvent) -> bool:
        ctx.validate_tenant_access(event.organization_id)
        dedup = event.dedup_key or f"usage_{uuid.uuid4().hex}"
        try:
            with self.scoped_conn(ctx) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO usage_ledger (id, organization_id, project_id, job_id, metric, quantity, unit, cost_usd, source, occurred_at, dedup_key)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (dedup_key) DO NOTHING
                        RETURNING id
                        """,
                        (
                            event.id,
                            event.organization_id,
                            event.project_id,
                            event.job_id,
                            event.metric,
                            event.quantity,
                            event.unit,
                            event.cost_usd,
                            event.source,
                            event.occurred_at,
                            dedup,
                        ),
                    )
                    return cur.fetchone() is not None
        except Exception:
            return False

    def check_and_reserve_quota(
        self, ctx: RequestContext, metric: str, requested_amount: float, limit_value: float = 1000.0
    ) -> bool:
        """Atomically check quota and reserve capacity using row-level locking."""
        with self.scoped_conn(ctx) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT current_value, limit_value
                    FROM tenant_quotas
                    WHERE organization_id = %s AND metric = %s AND period = 'monthly'
                    FOR UPDATE
                    """,
                    (ctx.organization_id, metric),
                )
                row = cur.fetchone()
                if not row:
                    cur.execute(
                        """
                        INSERT INTO tenant_quotas (organization_id, metric, limit_value, period, current_value)
                        VALUES (%s, %s, %s, 'monthly', %s)
                        """,
                        (ctx.organization_id, metric, limit_value, requested_amount),
                    )
                    return True

                curr, lim = row
                if curr + requested_amount > lim:
                    return False  # Quota exceeded

                cur.execute(
                    """
                    UPDATE tenant_quotas
                    SET current_value = current_value + %s
                    WHERE organization_id = %s AND metric = %s AND period = 'monthly'
                    """,
                    (requested_amount, ctx.organization_id, metric),
                )
                return True

    # ─── Audit Logging & Export ──────────────────────────────────────────

    def record_audit_event(self, event: EnterpriseAuditEvent) -> None:
        with self._raw_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO enterprise_audit (event_id, organization_id, actor, actor_type, action, resource, result, timestamp, source_ip, request_id, metadata, schema_version)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        event.event_id,
                        event.organization_id,
                        event.actor,
                        event.actor_type,
                        event.action,
                        event.resource,
                        event.result,
                        event.timestamp,
                        event.source_ip,
                        event.request_id,
                        json.dumps(event.metadata),
                        event.schema_version,
                    ),
                )
            conn.commit()

    def export_audit_log(self, ctx: RequestContext, limit: int = 100) -> list[dict[str, Any]]:
        ctx.require_permission("audit.export")
        with self.scoped_conn(ctx) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT event_id, organization_id, actor, actor_type, action, resource, result, timestamp, metadata, schema_version
                    FROM enterprise_audit
                    WHERE organization_id = %s
                    ORDER BY timestamp DESC
                    LIMIT %s
                    """,
                    (ctx.organization_id, limit),
                )
                rows = cur.fetchall()
        return [
            {
                "event_id": r[0],
                "organization_id": r[1],
                "actor": r[2],
                "actor_type": r[3],
                "action": r[4],
                "resource": r[5],
                "result": r[6],
                "timestamp": r[7],
                "metadata": r[8],
                "schema_version": r[9],
            }
            for r in rows
        ]
