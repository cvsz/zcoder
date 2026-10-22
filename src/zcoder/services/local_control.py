"""Offline local administration, compliance evidence, and task approvals.

No Anthropic SDK, network requests, or model inference. SQLite is suitable
for a single trusted host; external access requires a separate authenticated API.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROLES = frozenset({"admin", "operator", "auditor"})
TASK_STATES = frozenset({"PENDING", "APPROVED", "REJECTED"})


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LocalControlStore:
    """Explicit local-only administrative state with append-only audit records."""

    def __init__(self, database: str | Path):
        self.database = str(database)
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS principals (
                    principal TEXT PRIMARY KEY,
                    role TEXT NOT NULL CHECK (role IN ('admin','operator','auditor'))
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    description TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (state IN ('PENDING','APPROVED','REJECTED')),
                    reviewer TEXT,
                    execution_state TEXT NOT NULL DEFAULT 'READY'
                        CHECK (execution_state IN ('READY','RUNNING','COMPLETED','FAILED')),
                    consumed_at TEXT,
                    result TEXT,
                    error TEXT
                );
                CREATE TABLE IF NOT EXISTS audit (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    entry_hash TEXT NOT NULL
                );
                """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(tasks)")}
            migrations = {
                "execution_state": "ALTER TABLE tasks ADD COLUMN execution_state TEXT NOT NULL DEFAULT 'READY'",
                "consumed_at": "ALTER TABLE tasks ADD COLUMN consumed_at TEXT",
                "result": "ALTER TABLE tasks ADD COLUMN result TEXT",
                "error": "ALTER TABLE tasks ADD COLUMN error TEXT",
            }
            for name, statement in migrations.items():
                if name not in columns:
                    db.execute(statement)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database, timeout=10)
        db.execute("PRAGMA busy_timeout=10000")
        return db

    def _audit(self, db: sqlite3.Connection, actor: str, action: str, subject: str) -> None:
        row = db.execute("SELECT entry_hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        previous = row[0] if row else "0" * 64
        timestamp = utc_now()
        packed = json.dumps([timestamp, actor, action, subject, previous], separators=(",", ":"))
        digest = hashlib.sha256(packed.encode("utf-8")).hexdigest()
        db.execute(
            "INSERT INTO audit (timestamp,actor,action,subject,previous_hash,entry_hash) "
            "VALUES (?,?,?,?,?,?)",
            (timestamp, actor, action, subject, previous, digest),
        )

    def bootstrap_admin(self, principal: str) -> None:
        """Create only the first administrator using offline trusted setup."""
        if not principal.strip():
            raise ValueError("principal is required")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM principals LIMIT 1").fetchone():
                raise PermissionError("bootstrap disabled after the first principal")
            db.execute("INSERT INTO principals VALUES (?, 'admin')", (principal,))
            self._audit(db, principal, "admin.bootstrap", principal)

    def _require(self, db: sqlite3.Connection, actor: str, roles: set[str]) -> None:
        row = db.execute("SELECT role FROM principals WHERE principal=?", (actor,)).fetchone()
        if row is None or row[0] not in roles:
            raise PermissionError("permission denied")

    def grant_role(self, actor: str, principal: str, role: str) -> None:
        if role not in ROLES or not principal.strip():
            raise ValueError("invalid role or principal")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._require(db, actor, {"admin"})
            db.execute(
                "INSERT INTO principals(principal,role) VALUES (?,?) "
                "ON CONFLICT(principal) DO UPDATE SET role=excluded.role",
                (principal, role),
            )
            self._audit(db, actor, "admin.grant_role", f"{principal}:{role}")

    def list_principals(self, actor: str) -> list[tuple[str, str]]:
        with self._connect() as db:
            self._require(db, actor, {"admin"})
            return db.execute("SELECT principal,role FROM principals ORDER BY principal").fetchall()

    def get_task(self, actor: str, task_id: str) -> dict[str, str | None]:
        with self._connect() as db:
            row = db.execute(
                "SELECT task_id,description,owner,state,reviewer,execution_state,result,error "
                "FROM tasks WHERE task_id=?",
                (task_id,),
            ).fetchone()
            if row is None:
                raise ValueError("task not found")
            role = db.execute("SELECT role FROM principals WHERE principal=?", (actor,)).fetchone()
            if row[2] != actor and (role is None or role[0] not in {"admin", "operator"}):
                raise PermissionError("permission denied")
            keys = (
                "task_id",
                "description",
                "owner",
                "state",
                "reviewer",
                "execution_state",
                "result",
                "error",
            )
            return dict(zip(keys, row, strict=False))

    def create_task(self, actor: str, task_id: str, description: str) -> None:
        if not task_id.strip() or not description.strip():
            raise ValueError("task_id and description required")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._require(db, actor, {"admin", "operator"})
            db.execute(
                "INSERT INTO tasks(task_id,description,owner,state,reviewer) "
                "VALUES (?,?,?,'PENDING',NULL)",
                (task_id, description, actor),
            )
            self._audit(db, actor, "task.create", task_id)

    def decide_task(self, actor: str, task_id: str, approve: bool) -> None:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._require(db, actor, {"admin"})
            row = db.execute("SELECT owner,state FROM tasks WHERE task_id=?", (task_id,)).fetchone()
            if row is None or row[1] != "PENDING":
                raise ValueError("task missing or already decided")
            if row[0] == actor:
                raise PermissionError("task owner cannot approve their own task")
            state = "APPROVED" if approve else "REJECTED"
            db.execute("UPDATE tasks SET state=?,reviewer=? WHERE task_id=?", (state, actor, task_id))
            self._audit(db, actor, "task." + state.lower(), task_id)

    def audit_records(self, actor: str) -> list[tuple]:
        with self._connect() as db:
            self._require(db, actor, {"admin", "auditor"})
            return db.execute(
                "SELECT seq,timestamp,actor,action,subject,previous_hash,entry_hash "
                "FROM audit ORDER BY seq"
            ).fetchall()

    def verify_audit_chain(self, actor: str) -> bool:
        prev = "0" * 64
        for _seq, timestamp, owner, action, subject, stored_prev, digest in self.audit_records(actor):
            packed = json.dumps([timestamp, owner, action, subject, prev], separators=(",", ":"))
            expected = hashlib.sha256(packed.encode("utf-8")).hexdigest()
            if stored_prev != prev or digest != expected:
                return False
            prev = digest
        return True

    def consume_approved_task(self, actor: str, task_id: str) -> str:
        """Claim one approved task exactly once for a local model worker."""
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._require(db, actor, {"admin", "operator"})
            row = db.execute(
                "SELECT description,state,execution_state FROM tasks WHERE task_id=?",
                (task_id,),
            ).fetchone()
            if row is None or row[1] != "APPROVED" or row[2] != "READY":
                raise ValueError("task is missing, unapproved, or already consumed")
            db.execute(
                "UPDATE tasks SET execution_state='RUNNING',consumed_at=? "
                "WHERE task_id=? AND execution_state='READY'",
                (utc_now(), task_id),
            )
            self._audit(db, actor, "task.consume", task_id)
            return row[0]

    def complete_task(self, actor: str, task_id: str, *, result: str = "", error: str = "") -> None:
        """Persist the terminal outcome of a previously consumed task."""
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._require(db, actor, {"admin", "operator"})
            row = db.execute("SELECT execution_state FROM tasks WHERE task_id=?", (task_id,)).fetchone()
            if row is None or row[0] != "RUNNING":
                raise ValueError("task is not running")
            state = "FAILED" if error else "COMPLETED"
            db.execute(
                "UPDATE tasks SET execution_state=?,result=?,error=? WHERE task_id=?",
                (state, result, error, task_id),
            )
            self._audit(db, actor, "task." + state.lower(), task_id)


class LocalAgentRunner:
    """Run approved prompts once through the loopback llama.cpp provider."""

    def __init__(self, store: LocalControlStore, *, model: str | None = None):
        self.store = store
        self.model = model

    def run(self, actor: str, task_id: str) -> str:
        description = self.store.consume_approved_task(actor, task_id)
        from zcoder.services.coder import Coder

        response = Coder(provider="llama_cpp", model=self.model).generate(description)
        if response.startswith("[ERROR]"):
            self.store.complete_task(actor, task_id, error=response)
            raise RuntimeError(response)
        self.store.complete_task(actor, task_id, result=response)
        return response
