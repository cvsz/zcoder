"""legacy_job_models.py — Legacy Job infrastructure for backward compatibility."""

from __future__ import annotations

import enum
import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


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
            conn.execute(
                """
                INSERT OR REPLACE INTO jobs 
                (id, task, runtime, status, workspace, created_at, updated_at, model, budget_usd, cost_usd, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    job.id,
                    job.task,
                    job.runtime,
                    job.status,
                    job.workspace,
                    job.created_at,
                    job.updated_at,
                    job.model,
                    job.budget_usd,
                    job.cost_usd,
                    json.dumps(job.metadata),
                ),
            )

    def get_job(self, job_id: str) -> Optional[Job]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, task, runtime, status, workspace, created_at, updated_at, model, budget_usd, cost_usd, metadata FROM jobs WHERE id = ?",
                (job_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return Job(
                id=row[0],
                task=row[1],
                runtime=row[2],
                status=row[3],
                workspace=row[4],
                created_at=row[5],
                updated_at=row[6],
                model=row[7],
                budget_usd=row[8],
                cost_usd=row[9],
                metadata=json.loads(row[10]),
            )

    def list_jobs(self) -> List[Job]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, task, runtime, status, workspace, created_at, updated_at, model, budget_usd, cost_usd, metadata FROM jobs ORDER BY created_at DESC"
            )
            return [
                Job(
                    id=row[0],
                    task=row[1],
                    runtime=row[2],
                    status=row[3],
                    workspace=row[4],
                    created_at=row[5],
                    updated_at=row[6],
                    model=row[7],
                    budget_usd=row[8],
                    cost_usd=row[9],
                    metadata=json.loads(row[10]),
                )
                for row in cur.fetchall()
            ]

    def add_event(self, job_id: str, event_type: str, payload: Dict[str, Any]) -> JobEvent:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT COALESCE(MAX(sequence), 0) + 1 FROM events WHERE job_id = ?", (job_id,))
            seq = cur.fetchone()[0]
            evt = JobEvent(
                id=f"evt_{uuid.uuid4().hex[:8]}",
                job_id=job_id,
                sequence=seq,
                event_type=event_type,
                timestamp=time.time(),
                payload=payload,
            )
            conn.execute(
                """
                INSERT INTO events (id, job_id, sequence, event_type, timestamp, payload)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (evt.id, evt.job_id, evt.sequence, evt.event_type, evt.timestamp, json.dumps(evt.payload)),
            )
            return evt

    def list_events(self, job_id: str) -> List[JobEvent]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, job_id, sequence, event_type, timestamp, payload FROM events WHERE job_id = ? ORDER BY sequence ASC",
                (job_id,),
            )
            return [
                JobEvent(
                    id=r[0],
                    job_id=r[1],
                    sequence=r[2],
                    event_type=r[3],
                    timestamp=r[4],
                    payload=json.loads(r[5]),
                )
                for r in cur.fetchall()
            ]

    def create_approval(
        self, job_id: str, tool_name: str, action: str, risk: str = "medium"
    ) -> ApprovalRequest:
        req = ApprovalRequest(
            id=f"apr_{uuid.uuid4().hex[:8]}",
            job_id=job_id,
            tool_name=tool_name,
            action_description=action,
            risk_level=risk,
        )
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO approvals (id, job_id, tool_name, action_description, risk_level, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    req.id,
                    req.job_id,
                    req.tool_name,
                    req.action_description,
                    req.risk_level,
                    req.status,
                    req.created_at,
                ),
            )
        return req

    def update_approval(self, approval_id: str, status: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE approvals SET status = ? WHERE id = ?", (status, approval_id))


class ToolPolicy(str, enum.Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


class PolicyEngine:
    DANGEROUS_COMMANDS = ["rm -rf", "git push -f", "git reset --hard", "drop table", "mkfs", "dd if="]

    def evaluate_command(self, cmd: str) -> ToolPolicy:
        for danger in self.DANGEROUS_COMMANDS:
            if danger in cmd:
                return ToolPolicy.REQUIRE_APPROVAL
        return ToolPolicy.ALLOW


class FakeRuntime:
    def __init__(self, should_succeed: bool = True, cost: float = 0.05):
        self.should_succeed = should_succeed
        self.cost = cost

    def execute_task(self, job: Job, store: JobStore, validator: Optional[Callable[[], bool]] = None) -> bool:
        job.status = JobStatus.RUNNING.value
        store.save_job(job)
        store.add_event(job.id, "job.started", {"runtime": "fake"})

        store.add_event(job.id, "agent.plan", {"steps": ["Analyze", "Patch", "Validate"]})
        store.add_event(job.id, "agent.tool_executed", {"tool": "file_patch", "file": "test_auth.py"})

        job.cost_usd += self.cost
        if job.budget_usd and job.cost_usd > job.budget_usd:
            job.status = JobStatus.BUDGET_REACHED.value
            store.save_job(job)
            store.add_event(job.id, "budget.reached", {"budget": job.budget_usd, "spent": job.cost_usd})
            return False

        if validator and not validator():
            job.status = JobStatus.FAILED.value
            store.save_job(job)
            store.add_event(job.id, "job.failed", {"reason": "validation_failed"})
            return False

        if self.should_succeed:
            job.status = JobStatus.SUCCEEDED.value
            store.save_job(job)
            store.add_event(job.id, "job.succeeded", {"cost_usd": job.cost_usd})
            return True
        else:
            job.status = JobStatus.FAILED.value
            store.save_job(job)
            store.add_event(job.id, "job.failed", {"reason": "runtime_error"})
            return False


class JobOrchestrator:
    def __init__(self, store: Optional[JobStore] = None):
        self.store = store or JobStore()
        self.policy = PolicyEngine()

    def submit_job(
        self, task: str, runtime: str = "direct", model: str = "claude-sonnet-5", budget_usd: float = 0.0
    ) -> Job:
        job_id = f"job_{uuid.uuid4().hex[:8]}"
        job = Job(id=job_id, task=task, runtime=runtime, model=model, budget_usd=budget_usd)
        self.store.save_job(job)
        return job

    def run_job(
        self, job_id: str, runtime_adapter: Any, validator: Optional[Callable[[], bool]] = None
    ) -> bool:
        job = self.store.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        return runtime_adapter.execute_task(job, self.store, validator=validator)
