"""
Distributed task offloader for Phase 17.

Enables task offloading between agents. Supports:

- Task lifecycle management (pending → in_progress → completed/failed/cancelled)
- Timeout enforcement with automatic expiry
- Persistent task state (atomic on-disk writes, restored on restart)
- Consensus helpers (propose / vote / accept / reject) over the JSON-RPC protocol
- Session sharing and state-sync notifications

Persistence
-----------
Task state is stored at ``~/.zcoder/offloaded_tasks.json`` by default
(overridable via the ``storage_path`` constructor argument). Writes are
atomic (write-to-temp + ``os.replace``) and old terminal tasks are evicted
once the store passes ``max_tasks`` entries so the file cannot grow without
bound.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from zcoder.agent.communication.protocol import (
    MessageType,
    Operation,
    RPCNotification,
    RPCRequest,
    create_notification,
    create_request,
)

TASKS_FILE = Path.home() / ".zcoder" / "offloaded_tasks.json"


class TaskState(Enum):
    """States of a distributed task."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @classmethod
    def terminal_states(cls) -> tuple[TaskState, ...]:
        """States after which a task no longer needs an executor."""
        return (cls.COMPLETED, cls.FAILED, cls.CANCELLED)


@dataclass
class OffloadedTask:
    """Represents a task that has been offloaded to another agent."""

    task_id: str
    source_agent: str
    target_agent: str
    operation: Operation
    params: dict[str, Any]
    state: TaskState = TaskState.PENDING
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    result: Any = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: float | None = None

    @property
    def deadline(self) -> float | None:
        """Absolute timestamp after which the task is considered expired."""
        if self.timeout_seconds is None:
            return None
        return self.created_at + self.timeout_seconds

    def is_expired(self, now: float | None = None) -> bool:
        """Return True if a pending/in-progress task exceeded its timeout."""
        if self.state in TaskState.terminal_states():
            return False
        deadline = self.deadline
        if deadline is None:
            return False
        return (now if now is not None else time.time()) > deadline

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the on-disk representation."""
        return {
            "task_id": self.task_id,
            "source_agent": self.source_agent,
            "target_agent": self.target_agent,
            "operation": self.operation.value,
            "params": self.params,
            "state": self.state.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "error": self.error,
            "metadata": self.metadata,
            "timeout_seconds": self.timeout_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OffloadedTask:
        """Rehydrate an OffloadedTask from its on-disk representation."""
        try:
            operation = Operation(data.get("operation", Operation.OFFLOAD.value))
        except ValueError:
            operation = Operation.OFFLOAD
        try:
            state = TaskState(data.get("state", TaskState.PENDING.value))
        except ValueError:
            state = TaskState.PENDING
        return cls(
            task_id=str(data["task_id"]),
            source_agent=str(data.get("source_agent", "")),
            target_agent=str(data.get("target_agent", "")),
            operation=operation,
            params=dict(data.get("params", {})),
            state=state,
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", data.get("created_at", time.time()))),
            completed_at=data.get("completed_at"),
            result=data.get("result"),
            error=data.get("error"),
            metadata=dict(data.get("metadata", {})),
            timeout_seconds=data.get("timeout_seconds"),
        )


class TaskOffloader:
    """Manages distributed task offloading between agents."""

    def __init__(
        self,
        agent_id: str,
        storage_path: Path | str | None = None,
        max_tasks: int = 1000,
    ) -> None:
        """Initialize the offloader and restore persisted tasks from disk.

        Args:
            agent_id: Identity of the agent owning this offloader.
            storage_path: Optional explicit task-store file. Defaults to
                ``TASKS_FILE`` (``~/.zcoder/offloaded_tasks.json``).
            max_tasks: Maximum number of tracked tasks before terminal tasks
                are evicted oldest-first.
        """
        if not agent_id or not agent_id.strip():
            raise ValueError("agent_id must be a non-empty string")
        self.agent_id = agent_id
        self._path = Path(storage_path) if storage_path is not None else TASKS_FILE
        self._max_tasks = max_tasks
        self._lock = threading.Lock()
        self._tasks: dict[str, OffloadedTask] = self._load()

    @property
    def path(self) -> Path:
        """Return the on-disk file backing this offloader."""
        return self._path

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _load(self) -> dict[str, OffloadedTask]:
        """Load persisted tasks from disk."""
        if not self._path.exists():
            return {}
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            corrupt = self._path.with_suffix(self._path.suffix + ".corrupt")
            try:
                os.replace(self._path, corrupt)
            except OSError:
                pass
            return {}
        tasks: dict[str, OffloadedTask] = {}
        entries = data.values() if isinstance(data, dict) else data
        for entry in entries:
            if not isinstance(entry, dict) or "task_id" not in entry:
                continue
            try:
                task = OffloadedTask.from_dict(entry)
            except (TypeError, ValueError, KeyError):
                continue
            tasks[task.task_id] = task
        self._evict_locked(tasks)
        return tasks

    def _evict_locked(self, tasks: dict[str, OffloadedTask]) -> None:
        """Evict oldest terminal tasks until the store fits ``max_tasks``."""
        if len(tasks) <= self._max_tasks:
            return
        terminal = sorted(
            (t for t in tasks.values() if t.state in TaskState.terminal_states()),
            key=lambda t: (t.completed_at or t.updated_at, t.task_id),
        )
        for task in terminal:
            if len(tasks) <= self._max_tasks:
                break
            del tasks[task.task_id]

    def _save_locked(self) -> None:
        """Persist tasks atomically. Caller must hold ``self._lock``."""
        self._evict_locked(self._tasks)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=self._path.name + ".", suffix=".tmp", dir=self._path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({tid: t.to_dict() for tid, t in self._tasks.items()}, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self._path)
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def reload(self) -> None:
        """Re-read tasks from disk, discarding in-memory state."""
        with self._lock:
            self._tasks = self._load()

    # ------------------------------------------------------------------
    # Task lifecycle
    # ------------------------------------------------------------------
    def offload_task(
        self,
        target_agent_id: str,
        operation: Operation,
        params: dict[str, Any],
        timeout: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Offload a task to another agent.

        Args:
            target_agent_id: ID of the target agent.
            operation: Type of operation to perform.
            params: Parameters for the operation.
            timeout: Optional timeout in seconds. When set, :py:meth:`expire_stale`
                will mark the task as FAILED once the deadline passes.
            metadata: Optional extra metadata tracked with the task.

        Returns:
            The task ID for tracking.
        """
        if not target_agent_id or not target_agent_id.strip():
            raise ValueError("target_agent_id must be a non-empty string")
        if not isinstance(operation, Operation):
            operation = Operation.from_value(str(operation))
        if timeout is not None and timeout <= 0:
            raise ValueError("timeout must be positive when provided")

        task = OffloadedTask(
            task_id=str(uuid.uuid4()),
            source_agent=self.agent_id,
            target_agent=target_agent_id,
            operation=operation,
            params=dict(params),
            metadata=dict(metadata or {}),
            timeout_seconds=timeout,
        )
        with self._lock:
            self._tasks[task.task_id] = task
            self._save_locked()
        return task.task_id

    def get_task_status(self, task_id: str) -> dict[str, Any]:
        """Get the status of a task."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return {"error": f"Task {task_id} not found"}
        return {
            "task_id": task.task_id,
            "state": task.state.value,
            "source_agent": task.source_agent,
            "target_agent": task.target_agent,
            "operation": task.operation.value,
            "params": task.params,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
            "completed_at": task.completed_at,
            "result": task.result,
            "error": task.error,
            "metadata": task.metadata,
            "timeout_seconds": task.timeout_seconds,
        }

    def mark_in_progress(self, task_id: str) -> bool:
        """Mark a pending task as in_progress. Returns False if not possible."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None or task.state is not TaskState.PENDING:
                return False
            task.state = TaskState.IN_PROGRESS
            task.updated_at = time.time()
            self._save_locked()
        return True

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a task. Returns False if the task is unknown or terminal."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None or task.state in TaskState.terminal_states():
                return False
            task.state = TaskState.CANCELLED
            task.completed_at = time.time()
            task.updated_at = task.completed_at
            self._save_locked()
        return True

    def complete_task(self, task_id: str, result: Any = None, error: str | None = None) -> bool:
        """Mark a task as completed. Returns False for unknown/terminal tasks."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None or task.state in TaskState.terminal_states():
                return False
            task.state = TaskState.COMPLETED
            task.completed_at = time.time()
            task.updated_at = task.completed_at
            task.result = result
            task.error = error
            self._save_locked()
        return True

    def fail_task(self, task_id: str, error: str) -> bool:
        """Mark a task as failed with an error message."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None or task.state in TaskState.terminal_states():
                return False
            task.state = TaskState.FAILED
            task.completed_at = time.time()
            task.updated_at = task.completed_at
            task.error = error
            self._save_locked()
        return True

    def expire_stale(self, now: float | None = None) -> list[str]:
        """Fail every non-terminal task whose deadline has passed.

        Returns:
            IDs of the tasks that were expired.
        """
        now = now if now is not None else time.time()
        expired: list[str] = []
        with self._lock:
            for task in self._tasks.values():
                if task.is_expired(now):
                    task.state = TaskState.FAILED
                    task.error = "Task exceeded its timeout"
                    task.completed_at = now
                    task.updated_at = now
                    expired.append(task.task_id)
            if expired:
                self._save_locked()
        return expired

    def list_tasks(self, state: TaskState | None = None) -> list[dict[str, Any]]:
        """List tasks managed by this offloader, optionally filtered by state."""
        with self._lock:
            tasks = list(self._tasks.values())
        if state is not None:
            tasks = [t for t in tasks if t.state is state]
        return [
            {
                "task_id": task.task_id,
                "state": task.state.value,
                "source_agent": task.source_agent,
                "target_agent": task.target_agent,
                "operation": task.operation.value,
                "created_at": task.created_at,
                "updated_at": task.updated_at,
                "completed_at": task.completed_at,
                "timeout_seconds": task.timeout_seconds,
            }
            for task in tasks
        ]

    # ------------------------------------------------------------------
    # Consensus helpers (Phase 17 consensus operations)
    # ------------------------------------------------------------------
    def build_propose_message(self, proposal_id: str, payload: dict[str, Any]) -> RPCRequest:
        """Build a PROPOSE message to send to peer agents."""
        return create_request(Operation.PROPOSE.value, {"proposal_id": proposal_id, **payload})

    def build_vote_message(self, proposal_id: str, vote: bool, voter: str | None = None) -> RPCRequest:
        """Build a VOTE message agreeing (or not) with a proposal."""
        return create_request(
            Operation.VOTE.value,
            {"proposal_id": proposal_id, "vote": vote, "voter": voter or self.agent_id},
        )

    def build_accept_message(self, proposal_id: str) -> RPCNotification:
        """Build an ACCEPT notification broadcast once a quorum approves."""
        return create_notification(
            Operation.ACCEPT.value, {"proposal_id": proposal_id, "accepted_by": self.agent_id}
        )

    def build_reject_message(self, proposal_id: str, reason: str = "") -> RPCNotification:
        """Build a REJECT notification broadcast once a quorum rejects."""
        return create_notification(
            Operation.REJECT.value,
            {"proposal_id": proposal_id, "rejected_by": self.agent_id, "reason": reason},
        )

    def share_session(self, session_id: str, payload: dict[str, Any], target_agent: str) -> str:
        """Alias for offloading a SHARE_SESSION operation."""
        return self.offload_task(target_agent, Operation.SHARE_SESSION, {"session_id": session_id, **payload})

    def sync_state(self, session_id: str, state: dict[str, Any], target_agent: str) -> str:
        """Alias for offloading a SYNC_STATE operation."""
        return self.offload_task(
            target_agent, Operation.SYNC_STATE, {"session_id": session_id, "state": state}
        )

    def await_approval(
        self,
        proposal_id: str,
        votes: dict[str, bool],
        quorum: int | None = None,
    ) -> tuple[bool, str]:
        """Evaluate a consensus round from collected votes.

        Args:
            proposal_id: Identifier of the proposal being evaluated.
            votes: Mapping of voter id to vote (True = accept, False = reject).
            quorum: Number of matching votes required. Defaults to a simple
                majority of the collected votes (at least one).

        Returns:
            ``(approved, reason)`` — approved is True once a quorum of
            agreeing votes has been collected in either direction.
        """
        if not votes:
            return False, "no votes collected"
        if quorum is None:
            quorum = max(1, (len(votes) // 2) + 1)
        approvals = sum(1 for v in votes.values() if v)
        rejections = len(votes) - approvals
        if approvals >= quorum:
            return True, f"accepted: {approvals}/{len(votes)} votes (quorum {quorum})"
        if rejections >= quorum:
            return False, f"rejected: {rejections}/{len(votes)} votes (quorum {quorum})"
        return False, f"inconclusive: {approvals} approvals / {rejections} rejections (quorum {quorum})"


__all__ = [
    "TASKS_FILE",
    "MessageType",
    "OffloadedTask",
    "TaskOffloader",
    "TaskState",
]
