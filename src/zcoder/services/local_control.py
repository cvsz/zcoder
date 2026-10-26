"""Offline local administration, compliance evidence, and task approvals.

No Anthropic SDK, network requests, or model inference. SQLite is suitable
for a single trusted host; external access requires a separate authenticated API.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from zcoder.core.resilience import safe_urlopen

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
        # The database contains principal roles, task prompts/results, and audit
        # evidence. On POSIX, create/open it without following symlinks and
        # enforce owner-only access before SQLite opens the path.
        if os.name == "posix" and self.database != ":memory:":
            flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
            try:
                fd = os.open(self.database, flags, 0o600)
                try:
                    os.fchmod(fd, 0o600)
                finally:
                    os.close(fd)
            except OSError as exc:
                raise RuntimeError("unable to secure local control database permissions") from exc
        db = sqlite3.connect(self.database, timeout=10)
        db.execute("PRAGMA busy_timeout=10000")
        if os.name == "posix" and self.database != ":memory:":
            try:
                os.chmod(self.database, 0o600, follow_symlinks=False)
            except OSError:
                db.close()
                raise RuntimeError("unable to enforce local control database permissions")
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


class LocalLlamaCppClient:
    """Fail-closed OpenAI-compatible client restricted to loopback llama.cpp."""

    def __init__(self, base_url: str | None = None, *, model: str | None = None):
        self.base_url = (base_url or os.getenv("ZCODER_BASE_URL", "http://127.0.0.1:8080")).rstrip("/")
        self.model = model or os.getenv("ZCODER_MODEL", "local")
        parsed = urlsplit(self.base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username
            or parsed.password
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("local inference endpoint must be an HTTP loopback origin")

    def generate(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 4096,
            "temperature": 0.2,
            "stream": False,
        }
        request = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with safe_urlopen(request, timeout=120) as response:
            raw = response.read(8 * 1024 * 1024 + 1)
        if len(raw) > 8 * 1024 * 1024:
            raise ValueError("local model response exceeded the size limit")
        data = json.loads(raw)
        content = data["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError("local model returned an empty or invalid response")
        return content


class LocalAgentRunner:
    """Run approved prompts once through the loopback llama.cpp provider."""

    def __init__(
        self,
        store: LocalControlStore,
        *,
        model: str | None = None,
        base_url: str | None = None,
        inference_client: LocalLlamaCppClient | None = None,
    ):
        self.store = store
        self.inference_client = inference_client or LocalLlamaCppClient(base_url, model=model)

    def run(self, actor: str, task_id: str) -> str:
        description = self.store.consume_approved_task(actor, task_id)
        try:
            response = self.inference_client.generate(description)
        except Exception as exc:
            error = f"local inference failed: {type(exc).__name__}"
            self.store.complete_task(actor, task_id, error=error)
            raise RuntimeError(error) from exc
        self.store.complete_task(actor, task_id, result=response)
        return response
