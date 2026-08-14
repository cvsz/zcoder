"""engineering_models.py — Durable Engineering Runtime Entities."""
from __future__ import annotations

import enum
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


class TaskStatus(str, enum.Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PAUSED = "PAUSED"


@dataclass
class EngineeringTask:
    id: str = field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    task_description: str = ""
    status: TaskStatus = TaskStatus.CREATED
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Attempt:
    id: str = field(default_factory=lambda: f"att_{uuid.uuid4().hex[:8]}")
    task_id: str = ""
    generation: int = 1
    status: str = "PENDING"
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None


@dataclass
class Checkpoint:
    id: str = field(default_factory=lambda: f"chk_{uuid.uuid4().hex[:8]}")
    task_id: str = ""
    attempt_id: str = ""
    sequence: int = 0
    phase: str = ""
    state_snapshot: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
