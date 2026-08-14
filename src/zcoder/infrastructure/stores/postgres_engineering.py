"""postgres_engineering_store.py — Durable PostgreSQL-backed engineering storage."""

from __future__ import annotations

import json
import time

from engineering_models import Attempt, Checkpoint, EngineeringTask, TaskStatus
from engineering_store_interface import EngineeringStore

# Reusing connection management logic from existing postgres_store.py
from postgres_store import PostgresControlPlaneStore


class PostgresEngineeringStore(PostgresControlPlaneStore, EngineeringStore):
    """PostgreSQL-backed persistent store for engineering tasks."""

    def init_schema(self) -> None:
        """Create schema if not exists and enable RLS."""
        # Add engineering-specific tables
        schema = """
        CREATE TABLE IF NOT EXISTS engineering_tasks (
            id TEXT PRIMARY KEY,
            task_description TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at DOUBLE PRECISION NOT NULL,
            updated_at DOUBLE PRECISION NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{}'
        );
        -- Enable RLS
        ALTER TABLE engineering_tasks ENABLE ROW LEVEL SECURITY;
        
        CREATE TABLE IF NOT EXISTS engineering_attempts (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES engineering_tasks(id),
            generation INTEGER NOT NULL,
            status TEXT NOT NULL,
            started_at DOUBLE PRECISION NOT NULL,
            completed_at DOUBLE PRECISION
        );
        CREATE TABLE IF NOT EXISTS engineering_checkpoints (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES engineering_tasks(id),
            attempt_id TEXT NOT NULL REFERENCES engineering_attempts(id),
            sequence INTEGER NOT NULL,
            phase TEXT NOT NULL,
            state_snapshot JSONB NOT NULL DEFAULT '{}',
            timestamp DOUBLE PRECISION NOT NULL
        );
        -- Portfolio/Campaign Tables
        CREATE TABLE IF NOT EXISTS managed_repositories (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            local_path TEXT NOT NULL,
            status TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS engineering_campaigns (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            status TEXT NOT NULL,
            repositories JSONB NOT NULL DEFAULT '[]'
        );
        """
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(schema)

    def connection_scope(self):
        """Return a transactional connection scope for PostgreSQL infrastructure adapters."""
        return self._get_conn()

    def claim_task(self) -> EngineeringTask | None:
        """Atomically claim a CREATED task for processing."""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM engineering_tasks
                    WHERE status = 'CREATED'
                    ORDER BY created_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                """)
                row = cur.fetchone()
                if not row:
                    return None

                # Mark as RUNNING
                cur.execute(
                    """
                    UPDATE engineering_tasks
                    SET status = 'RUNNING', updated_at = %s
                    WHERE id = %s
                """,
                    (time.time(), row[0]),
                )

                metadata = row[5]
                if isinstance(metadata, str):
                    metadata = json.loads(metadata)

                return EngineeringTask(
                    id=row[0],
                    task_description=row[1],
                    status=TaskStatus.RUNNING,
                    created_at=row[3],
                    updated_at=row[4],
                    metadata=metadata,
                )

    def save_task(self, task: EngineeringTask) -> None:
        task.updated_at = time.time()
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO engineering_tasks (id, task_description, status, created_at, updated_at, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE
                    SET task_description = EXCLUDED.task_description,
                        status = EXCLUDED.status,
                        updated_at = EXCLUDED.updated_at,
                        metadata = EXCLUDED.metadata
                """,
                    (
                        task.id,
                        task.task_description,
                        task.status.value,
                        task.created_at,
                        task.updated_at,
                        json.dumps(task.metadata),
                    ),
                )

    def get_task(self, task_id: str) -> EngineeringTask | None:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM engineering_tasks WHERE id = %s", (task_id,))
                row = cur.fetchone()
                if not row:
                    return None

                metadata = row[5]
                if isinstance(metadata, str):
                    metadata = json.loads(metadata)

                return EngineeringTask(
                    id=row[0],
                    task_description=row[1],
                    status=TaskStatus(row[2]),
                    created_at=row[3],
                    updated_at=row[4],
                    metadata=metadata,
                )

    def create_attempt(self, attempt: Attempt) -> None:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO engineering_attempts (id, task_id, generation, status, started_at, completed_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """,
                    (
                        attempt.id,
                        attempt.task_id,
                        attempt.generation,
                        attempt.status,
                        attempt.started_at,
                        attempt.completed_at,
                    ),
                )

    def save_checkpoint(self, checkpoint: Checkpoint) -> None:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO engineering_checkpoints (id, task_id, attempt_id, sequence, phase, state_snapshot, timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                    (
                        checkpoint.id,
                        checkpoint.task_id,
                        checkpoint.attempt_id,
                        checkpoint.sequence,
                        checkpoint.phase,
                        json.dumps(checkpoint.state_snapshot),
                        checkpoint.timestamp,
                    ),
                )

    def get_latest_checkpoint(self, attempt_id: str) -> Checkpoint | None:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM engineering_checkpoints 
                    WHERE attempt_id = %s 
                    ORDER BY sequence DESC LIMIT 1
                """,
                    (attempt_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return Checkpoint(
                    id=row[0],
                    task_id=row[1],
                    attempt_id=row[2],
                    sequence=row[3],
                    phase=row[4],
                    state_snapshot=row[5],
                    timestamp=row[6],
                )

    def list_tasks(self, status: str | None = None) -> list[EngineeringTask]:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                if status:
                    cur.execute(
                        "SELECT * FROM engineering_tasks WHERE status = %s ORDER BY created_at DESC",
                        (status,),
                    )
                else:
                    cur.execute("SELECT * FROM engineering_tasks ORDER BY created_at DESC")
                rows = cur.fetchall()
            return [
                EngineeringTask(
                    id=row[0],
                    task_description=row[1],
                    status=TaskStatus(row[2]),
                    created_at=row[3],
                    updated_at=row[4],
                    metadata=row[5],
                )
                for row in rows
            ]
