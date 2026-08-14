"""legacy_job_models.py — Legacy Job infrastructure for backward compatibility."""
from __future__ import annotations
import enum
import time
import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

class JobStatus(str, enum.Enum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    PAUSED = "PAUSED"
    RETRYING = "RETRYING"
    BUDGET_REACHED = "BUDGET_REACHED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    SUCCEEDED = "SUCCEEDED"

@dataclass
class Job:
    id: str
    task: str
    runtime: str = "direct"
    status: str = "CREATED"
    workspace: str = "."
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    model: str = "claude-sonnet-5"
    budget_usd: float = 0.0
    cost_usd: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class JobEvent:
    id: str
    job_id: str
    sequence: int
    event_type: str
    timestamp: float
    payload: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ApprovalRequest:
    id: str
    job_id: str
    tool_name: str
    action_description: str
    risk_level: str = "medium"
    status: str = "PENDING"
    created_at: float = field(default_factory=time.time)

class JobStore:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or (Path.home() / ".zcoder" / "jobs.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    task TEXT,
                    runtime TEXT,
                    status TEXT,
                    workspace TEXT,
                    created_at REAL,
                    updated_at REAL,
                    model TEXT,
                    budget_usd REAL,
                    cost_usd REAL,
                    metadata TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    job_id TEXT,
                    sequence INTEGER,
                    event_type TEXT,
                    timestamp REAL,
                    payload TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS approvals (
                    id TEXT PRIMARY KEY,
                    job_id TEXT,
                    tool_name TEXT,
                    action_description TEXT,
                    risk_level TEXT,
                    status TEXT,
                    created_at REAL
                )
            """)

    def save_job(self, job: Job):
        job.updated_at = time.time()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO jobs 
                (id, task, runtime, status, workspace, created_at, updated_at, model, budget_usd, cost_usd, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job.id, job.task, job.runtime, job.status, job.workspace,
                job.created_at, job.updated_at, job.model, job.budget_usd,
                job.cost_usd, json.dumps(job.metadata)
            ))

    def get_job(self, job_id: str) -> Optional[Job]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, task, runtime, status, workspace, created_at, updated_at, model, budget_usd, cost_usd, metadata FROM jobs WHERE id = ?", (job_id,))
            row = cur.fetchone()
            if not row:
                return None
            return Job(
                id=row[0], task=row[1], runtime=row[2], status=row[3],
                workspace=row[4], created_at=row[5], updated_at=row[6],
                model=row[7], budget_usd=row[8], cost_usd=row[9],
                metadata=json.loads(row[10])
            )
