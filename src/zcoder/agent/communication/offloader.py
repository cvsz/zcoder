"""
Distributed task offloader for Phase 17.

Enables distributed task offloading between agents. Supports:
- Task proposal and offloading to remote agents
- Consensus protocols for multi-agent agreement
- Task status tracking and cancellation
- Session sharing and state synchronization
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from zcoder.agent.communication.protocol import (
    Operation,
)
from zcoder.agent.communication.registry import AgentRegistry


# Task state enumeration
class TaskState(Enum):
    """States of a distributed task."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


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
    completed_at: float | None = None
    result: Any = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class TaskOffloader:
    """Manages distributed task offloading between agents."""

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self._tasks: dict[str, OffloadedTask] = {}
        self._local_registry = AgentRegistry()

    def offload_task(
        self,
        target_agent_id: str,
        operation: Operation,
        params: dict[str, Any],
        timeout: float | None = None,
    ) -> str:
        """Offload a task to another agent.

        Args:
            target_agent_id: ID of the target agent
            operation: Type of operation to perform
            params: Parameters for the operation
            timeout: Optional timeout in seconds

        Returns:
            The task ID for tracking
        """
        task_id = str(uuid.uuid4())
        task = OffloadedTask(
            task_id=task_id,
            source_agent=self.agent_id,
            target_agent=target_agent_id,
            operation=operation,
            params=params,
        )
        self._tasks[task_id] = task

        # Save task state to disk
        self._persist_task(task)

        return task_id

    def get_task_status(self, task_id: str) -> dict[str, Any]:
        """Get the status of a task."""
        if task_id not in self._tasks:
            return {"error": f"Task {task_id} not found"}

        task = self._tasks[task_id]
        return {
            "task_id": task.task_id,
            "state": task.state.value,
            "source_agent": task.source_agent,
            "target_agent": task.target_agent,
            "operation": task.operation.value,
            "created_at": task.created_at,
            "completed_at": task.completed_at,
            "result": task.result,
            "error": task.error,
            "metadata": task.metadata,
        }

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a task."""
        if task_id not in self._tasks:
            return False

        task = self._tasks[task_id]
        task.state = TaskState.CANCELLED
        task.completed_at = time.time()

        # Remove from active tasks
        del self._tasks[task_id]

        # Persist the cancelled state
        self._persist_task(task)

        return True

    def _persist_task(self, task: OffloadedTask) -> None:
        """Persist task state to disk."""
        try:
            tasks_file = Path.home() / ".zcoder" / "offloaded_tasks.json"
            tasks_data: dict[str, dict[str, Any]] = {}

            if tasks_file.exists():
                with open(tasks_file) as f:
                    tasks_data = json.load(f)

            tasks_data[task.task_id] = {
                "state": task.state.value,
                "source_agent": task.source_agent,
                "target_agent": task.target_agent,
                "operation": task.operation.value,
                "params": task.params,
                "created_at": task.created_at,
                "completed_at": task.completed_at,
                "result": task.result,
                "error": task.error,
                "metadata": task.metadata,
            }

            with open(tasks_file, "w") as f:
                json.dump(tasks_data, f, indent=8)
        except (OSError, json.JSONDecodeError):
            pass  # Best-effort persistence

    def complete_task(
        self,
        task_id: str,
        result: Any,
        error: str | None = None,
    ) -> None:
        """Mark a task as completed."""
        if task_id not in self._tasks:
            return

        task = self._tasks[task_id]
        task.state = TaskState.COMPLETED
        task.completed_at = time.time()
        task.result = result
        task.error = error

        # Persist the completed state
        self._persist_task(task)

    def list_tasks(self) -> list[dict[str, Any]]:
        """List all tasks managed by this offloader."""
        return [
            {
                "task_id": task.task_id,
                "state": task.state.value,
                "source_agent": task.source_agent,
                "target_agent": task.target_agent,
                "operation": task.operation.value,
                "created_at": task.created_at,
                "completed_at": task.completed_at,
            }
            for task in self._tasks.values()
        ]