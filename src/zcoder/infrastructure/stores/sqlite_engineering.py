"""sqlite_engineering_store.py — Durable SQLite-backed engineering storage."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from zcoder.domain.interfaces.engineering_store import EngineeringStore
from zcoder.domain.models.engineering import Attempt, Checkpoint, EngineeringTask, TaskStatus


class SQLiteEngineeringStore(EngineeringStore):
    """SQLite-backed persistent store for engineering tasks."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or (Path.home() / ".zcoder" / "engineering.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        # Enable WAL mode for better concurrency and crash-safety
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    task_description TEXT,
                    status TEXT,
                    created_at REAL,
                    updated_at REAL,
                    metadata TEXT,
                    claimed_by TEXT,
                    claim_generation INTEGER NOT NULL DEFAULT 0,
                    lease_expires_at REAL NOT NULL DEFAULT 0
                )
            """
            )
            # Defensive migration for pre-existing database files created before
            # lease-claim columns were introduced.
            for column_def in (
                "claimed_by TEXT",
                "claim_generation INTEGER NOT NULL DEFAULT 0",
                "lease_expires_at REAL NOT NULL DEFAULT 0",
            ):
                try:
                    conn.execute(f"ALTER TABLE tasks ADD COLUMN {column_def}")
                except sqlite3.OperationalError:
                    pass  # Column already exists.
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tasks_status_created
                ON tasks (status, created_at)
            """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS attempts (
                    id TEXT PRIMARY KEY,
                    task_id TEXT,
                    generation INTEGER,
                    status TEXT,
                    started_at REAL,
                    completed_at REAL
                )
            """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoints (
                    id TEXT PRIMARY KEY,
                    task_id TEXT,
                    attempt_id TEXT,
                    sequence INTEGER,
                    phase TEXT,
                    state_snapshot TEXT,
                    timestamp REAL
                )
            """
            )

    def claim_task(
        self,
        task_id: str | None = None,
        claimed_by: str = "default-worker",
        lease_seconds: float = 60.0,
    ) -> EngineeringTask | None:
        """Atomically claim a CREATED task (or reclaim an expired RUNNING lease).

        Uses BEGIN IMMEDIATE plus a compare-and-set on claim_generation so two
        concurrent processes can never claim the same task. The incremented
        generation acts as a fencing token; stale claimers are rejected.
        """
        now = time.time()
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                query = """
                    SELECT id, task_description, status, created_at, updated_at, metadata, claim_generation
                    FROM tasks
                    WHERE status = 'CREATED'
                       OR (status = 'RUNNING' AND lease_expires_at < ?)
                """
                params: list[object] = [now]
                if task_id is not None:
                    query += " AND id = ?"
                    params.append(task_id)
                query += " ORDER BY created_at ASC LIMIT 1"
                row = conn.execute(query, params).fetchone()
                if not row:
                    conn.commit()
                    return None

                task_id_found, description, _, created_at, updated_at, metadata_json, generation = row
                new_generation = int(generation or 0) + 1
                cur = conn.execute(
                    """
                    UPDATE tasks
                    SET status = 'RUNNING', claimed_by = ?, claim_generation = ?,
                        lease_expires_at = ?, updated_at = ?
                    WHERE id = ? AND claim_generation = ?
                """,
                    (
                        claimed_by,
                        new_generation,
                        now + lease_seconds,
                        now,
                        task_id_found,
                        int(generation or 0),
                    ),
                )
                if cur.rowcount != 1:
                    conn.commit()
                    return None  # Lost the claim race.
                conn.commit()
                return EngineeringTask(
                    id=task_id_found,
                    task_description=description,
                    status=TaskStatus.RUNNING,
                    created_at=created_at,
                    updated_at=now,
                    metadata=json.loads(metadata_json) if metadata_json else {},
                )
            except Exception:
                conn.rollback()
                raise

    def save_task(self, task: EngineeringTask) -> None:
        task.updated_at = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO tasks (id, task_description, status, created_at, updated_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
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
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = cur.fetchone()
            if not row:
                return None
            return EngineeringTask(
                id=row[0],
                task_description=row[1],
                status=TaskStatus(row[2]),
                created_at=row[3],
                updated_at=row[4],
                metadata=json.loads(row[5]),
            )

    def create_attempt(self, attempt: Attempt) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO attempts (id, task_id, generation, status, started_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?)
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
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO checkpoints (id, task_id, attempt_id, sequence, phase, state_snapshot, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
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
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT * FROM checkpoints 
                WHERE attempt_id = ? 
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
                state_snapshot=json.loads(row[5]),
                timestamp=row[6],
            )

    def list_tasks(self, status: str | None = None) -> list[EngineeringTask]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            if status:
                cur.execute("SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC", (status,))
            else:
                cur.execute("SELECT * FROM tasks ORDER BY created_at DESC")
            return [
                EngineeringTask(
                    id=row[0],
                    task_description=row[1],
                    status=TaskStatus(row[2]),
                    created_at=row[3],
                    updated_at=row[4],
                    metadata=json.loads(row[5]),
                )
                for row in cur.fetchall()
            ]
