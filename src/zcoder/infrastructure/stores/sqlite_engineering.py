"""sqlite_engineering_store.py — Durable SQLite-backed engineering storage."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import List, Optional

from engineering_models import Attempt, Checkpoint, EngineeringTask, TaskStatus
from engineering_store_interface import EngineeringStore


class SQLiteEngineeringStore(EngineeringStore):
    """SQLite-backed persistent store for engineering tasks."""

    def __init__(self, db_path: Optional[Path] = None):
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
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    task_description TEXT,
                    status TEXT,
                    created_at REAL,
                    updated_at REAL,
                    metadata TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS attempts (
                    id TEXT PRIMARY KEY,
                    task_id TEXT,
                    generation INTEGER,
                    status TEXT,
                    started_at REAL,
                    completed_at REAL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS checkpoints (
                    id TEXT PRIMARY KEY,
                    task_id TEXT,
                    attempt_id TEXT,
                    sequence INTEGER,
                    phase TEXT,
                    state_snapshot TEXT,
                    timestamp REAL
                )
            """)

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

    def get_task(self, task_id: str) -> Optional[EngineeringTask]:
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

    def get_latest_checkpoint(self, attempt_id: str) -> Optional[Checkpoint]:
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

    def list_tasks(self, status: Optional[str] = None) -> List[EngineeringTask]:
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
