"""postgres_store.py — Real PostgreSQL Control Plane Storage Backend.

This module provides a production-grade PostgreSQL storage backend for ZCoder.
It implements the same interface as the SQLite ControlPlaneStore but uses
real PostgreSQL features:

  • SELECT ... FOR UPDATE SKIP LOCKED (atomic multi-process claim)
  • Row-level locking (not just CAS)
  • Unique constraints for deduplication
  • Proper connection pooling with psycopg2/psycopg (configurable)
  • LISTEN/NOTIFY for lease events (optional)

This module requires psycopg2-binary or psycopg >= 3.x to be installed.
It is intentionally separate from control_plane.py so that the SQLite path
has no dependency on PostgreSQL packages.

Usage:
    from zcoder.infrastructure.stores.postgres import PostgresControlPlaneStore
    store = PostgresControlPlaneStore(dsn="postgresql://user:pass@host/db")
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from zcoder.core.utils import sanitize_dsn
from zcoder.domain.models.legacy_job import Job, JobStatus
from zcoder.infrastructure.stores.postgres_outbox_store import process_postgres_store_outbox

logger = logging.getLogger(__name__)

# ─── psycopg import guard ────────────────────────────────────────────────────

try:
    import psycopg2
    import psycopg2.extras
    import psycopg2.pool

    _PSYCOPG2_AVAILABLE = True
    _PG_AVAILABLE = True
except ImportError:
    _PSYCOPG2_AVAILABLE = False

if not _PSYCOPG2_AVAILABLE:
    try:
        import psycopg  # type: ignore[import]

        _PSYCOPG3_AVAILABLE = True
        _PG_AVAILABLE = True
    except ImportError:
        _PSYCOPG3_AVAILABLE = False
        _PG_AVAILABLE = False


# ─── Schema DDL ──────────────────────────────────────────────────────────────

POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
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

CREATE TABLE IF NOT EXISTS outbox (
    id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM now()),
    delivered_at DOUBLE PRECISION,
    error TEXT
);

CREATE TABLE IF NOT EXISTS webhook_inbox (
    delivery_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    received_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM now())
);

CREATE TABLE IF NOT EXISTS installations (
    installation_id BIGINT PRIMARY KEY,
    account_login TEXT NOT NULL,
    account_type TEXT NOT NULL DEFAULT 'Organization',
    suspended BOOLEAN NOT NULL DEFAULT FALSE,
    created_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM now())
);

CREATE TABLE IF NOT EXISTS repositories (
    id TEXT PRIMARY KEY,
    installation_id BIGINT NOT NULL REFERENCES installations(installation_id),
    owner TEXT NOT NULL,
    name TEXT NOT NULL,
    default_branch TEXT NOT NULL DEFAULT 'main',
    automation_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    trust_level TEXT NOT NULL DEFAULT 'STANDARD'
);

CREATE TABLE IF NOT EXISTS worker_registry (
    worker_id TEXT PRIMARY KEY,
    pool_type TEXT NOT NULL DEFAULT 'standard',
    hostname TEXT,
    pid INTEGER,
    registered_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM now()),
    last_heartbeat DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM now()),
    active_jobs INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS deployment_history (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    version TEXT NOT NULL,
    image_digest TEXT,
    deployed_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM now()),
    actor TEXT,
    environment TEXT NOT NULL DEFAULT 'unknown',
    migration_version TEXT,
    result TEXT NOT NULL DEFAULT 'UNKNOWN',
    notes TEXT
);

CREATE TABLE IF NOT EXISTS backup_status (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    backup_type TEXT NOT NULL DEFAULT 'pg_dump',
    started_at DOUBLE PRECISION NOT NULL,
    completed_at DOUBLE PRECISION,
    success BOOLEAN NOT NULL DEFAULT FALSE,
    size_bytes BIGINT,
    destination TEXT,
    error TEXT,
    restore_drill_at DOUBLE PRECISION,
    restore_drill_success BOOLEAN
);

-- Indexes for common access patterns
CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON jobs (status, created_at) WHERE status IN ('READY', 'RUNNING');
CREATE INDEX IF NOT EXISTS idx_jobs_lease ON jobs (lease_expires_at) WHERE status = 'RUNNING';
CREATE INDEX IF NOT EXISTS idx_outbox_status ON outbox (status, created_at) WHERE status = 'PENDING';
CREATE INDEX IF NOT EXISTS idx_repos_installation ON repositories (installation_id);
CREATE INDEX IF NOT EXISTS idx_worker_registry_heartbeat ON worker_registry (last_heartbeat);
CREATE INDEX IF NOT EXISTS idx_backup_status_success ON backup_status (success, completed_at);
CREATE INDEX IF NOT EXISTS idx_backup_status_restore_drill ON backup_status (restore_drill_at);
"""


# ─── PostgresControlPlaneStore ───────────────────────────────────────────────


class PostgresControlPlaneStore:
    """Production PostgreSQL-backed control plane store.

    Uses SELECT ... FOR UPDATE SKIP LOCKED for multi-process atomic claims.
    Multiple processes connecting to the same PostgreSQL instance will safely
    partition work without duplicate execution.
    """

    def __init__(
        self,
        dsn: str = "",
        min_conn: int = 1,
        max_conn: int = 10,
        connect_timeout: int = 10,
    ) -> None:
        if not _PG_AVAILABLE:
            raise RuntimeError(
                "PostgreSQL support requires psycopg2-binary or psycopg3. "
                "Install with: pip install psycopg2-binary"
            )

        self._dsn = dsn or os.environ.get("DATABASE_URL", "")
        if not self._dsn:
            raise ValueError("DATABASE_URL must be set for PostgreSQL mode")

        self._min_conn = min_conn
        self._max_conn = max_conn
        self._connect_timeout = connect_timeout
        self._pool: Any | None = None
        self._init_pool()

    def _init_pool(self) -> None:
        """Initialize connection pool."""
        dsn = sanitize_dsn(self._dsn)
        if _PSYCOPG2_AVAILABLE:
            self._pool = psycopg2.pool.ThreadedConnectionPool(
                self._min_conn,
                self._max_conn,
                dsn,
                connect_timeout=self._connect_timeout,
            )
            logger.info(
                f"PostgreSQL connection pool initialized (psycopg2, min={self._min_conn}, max={self._max_conn})"
            )
        else:
            # psycopg3 connection pool
            import psycopg.pool  # type: ignore[import]

            self._pool = psycopg.pool.ConnectionPool(  # type: ignore[import]
                dsn,
                min_size=self._min_conn,
                max_size=self._max_conn,
                open=True,
            )
            logger.info(
                f"PostgreSQL connection pool initialized (psycopg3, min={self._min_conn}, max={self._max_conn})"
            )

    @contextmanager
    def _get_conn(self) -> Generator[Any, None, None]:
        """Get a connection from the pool."""
        if _PSYCOPG2_AVAILABLE:
            conn = self._pool.getconn()
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                self._pool.putconn(conn)
        else:
            with self._pool.connection() as conn:
                yield conn

    def init_schema(self) -> None:
        """Create schema if not exists. Safe to run multiple times (idempotent)."""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(POSTGRES_SCHEMA)
        logger.info("PostgreSQL schema initialized")

    def close(self) -> None:
        """Close the connection pool."""
        if self._pool:
            if _PSYCOPG2_AVAILABLE:
                self._pool.closeall()
            else:
                self._pool.close()

    # ── Job operations ────────────────────────────────────────────────────

    def enqueue_job(self, job: Job) -> Job:
        """Insert a new job."""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO jobs (id, task, runtime, status, workspace, created_at, updated_at,
                                     model, budget_usd, cost_usd, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        job.id,
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

    def claim_job_with_fencing(self, worker_id: str, lease_duration: float = 120.0) -> tuple[Job, int] | None:
        """
        Atomically claim the oldest available job using SELECT ... FOR UPDATE SKIP LOCKED.

        This is the key multi-process safety mechanism. Multiple workers can call this
        simultaneously on the same PostgreSQL and each gets a unique job.

        Returns (job, fencing_token) or None if no job available.
        """
        now = time.time()
        expires_at = now + lease_duration

        with self._get_conn() as conn:
            with conn.cursor() as cur:
                # SKIP LOCKED ensures competing workers don't block each other
                cur.execute(
                    """
                    SELECT id, task, runtime, status, workspace, created_at, updated_at,
                           model, budget_usd, cost_usd, claim_generation, metadata
                    FROM jobs
                    WHERE status = 'READY'
                       OR (status = 'RUNNING' AND lease_expires_at < %s)
                    ORDER BY created_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                    """,
                    (now,),
                )
                row = cur.fetchone()
                if not row:
                    return None

                job_id, task, runtime, status, workspace, c_at, u_at, model, budget, cost, gen, meta = row

                new_gen = gen + 1

                cur.execute(
                    """
                    UPDATE jobs
                    SET status = 'RUNNING',
                        claimed_by = %s,
                        claim_generation = %s,
                        lease_expires_at = %s,
                        updated_at = %s
                    WHERE id = %s AND claim_generation = %s
                    RETURNING id
                    """,
                    (worker_id, new_gen, expires_at, now, job_id, gen),
                )

                if cur.fetchone() is None:
                    # Should not happen with FOR UPDATE, but guard anyway
                    return None

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

    def mutate_with_fencing(
        self,
        job_id: str,
        worker_id: str,
        fencing_token: int,
        status: JobStatus,
        cost_usd: float,
    ) -> bool:
        """Reject stale worker writes. Only current token holder can mutate."""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE jobs
                    SET status = %s, cost_usd = %s, updated_at = %s
                    WHERE id = %s AND claimed_by = %s AND claim_generation = %s
                    """,
                    (status.value, cost_usd, time.time(), job_id, worker_id, fencing_token),
                )
                return cur.rowcount > 0

    def renew_lease(
        self,
        job_id: str,
        worker_id: str,
        fencing_token: int,
        lease_duration: float = 120.0,
    ) -> bool:
        """Extend lease for a currently-running job."""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE jobs
                    SET lease_expires_at = %s, updated_at = %s
                    WHERE id = %s AND claimed_by = %s AND claim_generation = %s AND status = 'RUNNING'
                    """,
                    (time.time() + lease_duration, time.time(), job_id, worker_id, fencing_token),
                )
                return cur.rowcount > 0

    def reconcile_expired_leases(self) -> int:
        """Find RUNNING jobs with expired leases and return them to READY."""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE jobs
                    SET status = 'READY', claimed_by = NULL, updated_at = %s
                    WHERE status = 'RUNNING' AND lease_expires_at < %s
                    RETURNING id
                    """,
                    (time.time(), time.time()),
                )
                rows = cur.fetchall()
                count = len(rows)
                if count:
                    logger.info(f"Reconciled {count} expired leases: {[r[0] for r in rows]}")
                return count

    def get_job(self, job_id: str) -> Job | None:
        """Fetch a single job by ID."""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, task, runtime, status, workspace, created_at, updated_at, "
                    "model, budget_usd, cost_usd, metadata FROM jobs WHERE id = %s",
                    (job_id,),
                )
                row = cur.fetchone()
        if not row:
            return None
        job_id, task, runtime, status, workspace, c_at, u_at, model, budget, cost, meta = row
        meta_dict = meta if isinstance(meta, dict) else json.loads(meta or "{}")
        return Job(
            id=job_id,
            task=task,
            runtime=runtime,
            status=JobStatus(status),
            workspace=workspace,
            created_at=c_at,
            updated_at=u_at,
            model=model,
            budget_usd=budget,
            cost_usd=cost,
            metadata=meta_dict,
        )

    def list_jobs(
        self,
        status_filter: str | None = None,
        limit: int = 100,
    ) -> list[Job]:
        """List jobs with optional status filter."""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                if status_filter:
                    cur.execute(
                        "SELECT id, task, runtime, status, workspace, created_at, updated_at, "
                        "model, budget_usd, cost_usd, metadata FROM jobs WHERE status = %s "
                        "ORDER BY created_at DESC LIMIT %s",
                        (status_filter, limit),
                    )
                else:
                    cur.execute(
                        "SELECT id, task, runtime, status, workspace, created_at, updated_at, "
                        "model, budget_usd, cost_usd, metadata FROM jobs "
                        "ORDER BY created_at DESC LIMIT %s",
                        (limit,),
                    )
                rows = cur.fetchall()

        jobs = []
        for row in rows:
            job_id, task, runtime, status, workspace, c_at, u_at, model, budget, cost, meta = row
            meta_dict = meta if isinstance(meta, dict) else json.loads(meta or "{}")
            jobs.append(
                Job(
                    id=job_id,
                    task=task,
                    runtime=runtime,
                    status=JobStatus(status),
                    workspace=workspace,
                    created_at=c_at,
                    updated_at=u_at,
                    model=model,
                    budget_usd=budget,
                    cost_usd=cost,
                    metadata=meta_dict,
                )
            )
        return jobs

    # ── Outbox ────────────────────────────────────────────────────────────

    def enqueue_outbox(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        msg_id = f"out_{uuid.uuid4().hex[:8]}"
        now = time.time()
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO outbox (id, action, payload, status, attempts, created_at)
                    VALUES (%s, %s, %s, 'PENDING', 0, %s)
                    """,
                    (msg_id, action, json.dumps(payload), now),
                )
        return {"id": msg_id, "action": action, "status": "PENDING", "created_at": now}

    def process_outbox(
        self,
        handler: Any,
        max_attempts: int = 5,
        backoff_base: float = 2.0,
    ) -> int:
        """Process one bounded outbox batch through the Upgrade-42 adapter."""
        return process_postgres_store_outbox(
            self,
            handler,
            max_attempts=max_attempts,
            backoff_base=backoff_base,
        )

    # ── Webhook deduplication ─────────────────────────────────────────────

    def record_webhook_delivery_atomic(self, delivery_id: str, event_type: str) -> bool:
        """Atomically record webhook delivery. Returns False if duplicate."""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO webhook_inbox (delivery_id, event_type, received_at)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (delivery_id) DO NOTHING
                        RETURNING delivery_id
                        """,
                        (delivery_id, event_type, time.time()),
                    )
                    row = cur.fetchone()
                    return row is not None
        except Exception as e:
            logger.error(f"Webhook deduplication error: {e}")
            return False

    # ── Fleet registry ────────────────────────────────────────────────────

    def register_installation(
        self, installation_id: int, account_login: str, account_type: str = "Organization"
    ) -> None:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO installations (installation_id, account_login, account_type, created_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (installation_id) DO UPDATE
                    SET account_login = EXCLUDED.account_login,
                        account_type = EXCLUDED.account_type
                    """,
                    (installation_id, account_login, account_type, time.time()),
                )

    def register_repository(
        self,
        repo_id: str,
        installation_id: int,
        owner: str,
        name: str,
        default_branch: str = "main",
        automation_enabled: bool = False,
        trust_level: str = "STANDARD",
    ) -> None:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO repositories (id, installation_id, owner, name, default_branch,
                                              automation_enabled, trust_level)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE
                    SET automation_enabled = EXCLUDED.automation_enabled,
                        trust_level = EXCLUDED.trust_level,
                        default_branch = EXCLUDED.default_branch
                    """,
                    (repo_id, installation_id, owner, name, default_branch, automation_enabled, trust_level),
                )

    # ── Worker registry ────────────────────────────────────────────────────

    def register_worker(
        self, worker_id: str, pool_type: str = "standard", hostname: str = "", pid: int = 0
    ) -> None:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO worker_registry (worker_id, pool_type, hostname, pid, registered_at, last_heartbeat)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (worker_id) DO UPDATE
                    SET last_heartbeat = EXCLUDED.last_heartbeat,
                        pool_type = EXCLUDED.pool_type
                    """,
                    (worker_id, pool_type, hostname, pid, time.time(), time.time()),
                )

    def heartbeat_worker(self, worker_id: str, active_jobs: int = 0) -> None:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE worker_registry SET last_heartbeat = %s, active_jobs = %s WHERE worker_id = %s",
                    (time.time(), active_jobs, worker_id),
                )

    def get_active_workers(self, max_idle_seconds: float = 300.0) -> list[dict[str, Any]]:
        threshold = time.time() - max_idle_seconds
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT worker_id, pool_type, hostname, pid, last_heartbeat, active_jobs "
                    "FROM worker_registry WHERE last_heartbeat > %s ORDER BY last_heartbeat DESC",
                    (threshold,),
                )
                rows = cur.fetchall()
        return [
            {
                "worker_id": r[0],
                "pool_type": r[1],
                "hostname": r[2],
                "pid": r[3],
                "last_heartbeat": r[4],
                "active_jobs": r[5],
            }
            for r in rows
        ]

    # ── Deployment history ────────────────────────────────────────────────

    def record_deployment(
        self,
        version: str,
        environment: str = "unknown",
        actor: str = "",
        image_digest: str = "",
        migration_version: str = "",
        result: str = "SUCCESS",
        notes: str = "",
    ) -> str:
        deploy_id = f"deploy_{uuid.uuid4().hex[:8]}"
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO deployment_history (id, version, image_digest, deployed_at,
                                                    actor, environment, migration_version, result, notes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        deploy_id,
                        version,
                        image_digest,
                        time.time(),
                        actor,
                        environment,
                        migration_version,
                        result,
                        notes,
                    ),
                )
        return deploy_id

    # ── Backup status ─────────────────────────────────────────────────────

    def record_backup(
        self,
        backup_type: str = "pg_dump",
        success: bool = False,
        size_bytes: int = 0,
        destination: str = "",
        error: str = "",
    ) -> str:
        backup_id = f"bkp_{uuid.uuid4().hex[:8]}"
        now = time.time()
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO backup_status (id, backup_type, started_at, completed_at, success,
                                               size_bytes, destination, error)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (backup_id, backup_type, now, now, success, size_bytes, destination, error or None),
                )
        return backup_id

    def record_restore_drill(self, backup_id: str, success: bool = True) -> None:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE backup_status SET restore_drill_at = %s, restore_drill_success = %s WHERE id = %s",
                    (time.time(), success, backup_id),
                )

    def get_backup_freshness(self) -> dict[str, Any]:
        """Return info about backup and restore drill freshness."""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT completed_at, success FROM backup_status WHERE success = TRUE "
                    "ORDER BY completed_at DESC LIMIT 1"
                )
                last_backup = cur.fetchone()
                cur.execute(
                    "SELECT restore_drill_at, restore_drill_success FROM backup_status "
                    "WHERE restore_drill_at IS NOT NULL ORDER BY restore_drill_at DESC LIMIT 1"
                )
                last_drill = cur.fetchone()

        return {
            "last_backup_at": last_backup[0] if last_backup else None,
            "last_backup_success": last_backup[1] if last_backup else False,
            "last_restore_drill_at": last_drill[0] if last_drill else None,
            "last_restore_drill_success": last_drill[1] if last_drill else False,
        }

    # ── Health ────────────────────────────────────────────────────────────

    def health_check(self) -> bool:
        """Simple connectivity check."""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    return cur.fetchone() is not None
        except Exception as e:
            logger.error(f"PostgreSQL health check failed: {e}")
            return False

    # ── Stats ─────────────────────────────────────────────────────────────

    def get_queue_stats(self) -> dict[str, int]:
        """Return queue depth by status."""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status")
                rows = cur.fetchall()
        return {row[0]: row[1] for row in rows}
