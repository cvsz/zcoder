"""engineering_models.py — Durable Engineering Runtime Entities."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from queue import Queue
from typing import Any

from zcoder.core.enums import StringEnum


class TaskStatus(StringEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PAUSED = "PAUSED"


@dataclass(slots=True)
class EngineeringTask:
    id: str = field(default_factory=lambda: f"task_{uuid.uuid4().hex}")
    task_description: str = ""
    status: str = TaskStatus.CREATED
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Attempt:
    id: str = field(default_factory=lambda: f"att_{uuid.uuid4().hex}")
    task_id: str = ""
    generation: int = 1
    status: str = "PENDING"
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None


@dataclass(slots=True)
class Checkpoint:
    id: str = field(default_factory=lambda: f"chk_{uuid.uuid4().hex}")
    task_id: str = ""
    attempt_id: str = ""
    sequence: int = 0
    phase: str = ""
    state_snapshot: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class CheckpointPool:
    """Object pool for Checkpoint instances to reduce allocation overhead."""

    def __init__(self, initial_size: int = 10):
        self._pool: Queue[Checkpoint] = Queue()
        self._created = 0
        # Pre-populate pool
        for _ in range(initial_size):
            self._pool.put(Checkpoint())
            self._created += 1

    def acquire(self) -> Checkpoint:
        """Get a Checkpoint from the pool, creating new if empty."""
        try:
            return self._pool.get_nowait()
        except Exception:
            self._created += 1
            return Checkpoint()

    def release(self, checkpoint: Checkpoint) -> None:
        """Return a Checkpoint to the pool, resetting it first."""
        # Reset all fields
        checkpoint.id = ""
        checkpoint.task_id = ""
        checkpoint.attempt_id = ""
        checkpoint.sequence = 0
        checkpoint.phase = ""
        checkpoint.state_snapshot.clear()
        checkpoint.timestamp = 0.0
        try:
            self._pool.put_nowait(checkpoint)
        except Exception:  # nosec
            # Pool full, just discard
            pass

    def created_count(self) -> int:
        """Return total number of Checkpoints ever created."""
        return self._created

    def pool_size(self) -> int:
        """Return current pool size."""
        return self._pool.qsize()
