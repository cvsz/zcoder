"""engineering_store_interface.py — Abstract Interface for Durable Engineering Storage."""

from __future__ import annotations

from abc import ABC, abstractmethod

from engineering_models import Attempt, Checkpoint, EngineeringTask


class EngineeringStore(ABC):
    """Abstract base class for all Engineering Task storage backends."""

    @abstractmethod
    def save_task(self, task: EngineeringTask) -> None:
        """Persist EngineeringTask."""
        pass

    @abstractmethod
    def get_task(self, task_id: str) -> EngineeringTask | None:
        """Retrieve EngineeringTask by ID."""
        pass

    @abstractmethod
    def create_attempt(self, attempt: Attempt) -> None:
        """Create a new execution attempt."""
        pass

    @abstractmethod
    def save_checkpoint(self, checkpoint: Checkpoint) -> None:
        """Persist checkpoint for an attempt."""
        pass

    @abstractmethod
    def get_latest_checkpoint(self, attempt_id: str) -> Checkpoint | None:
        """Retrieve the latest checkpoint for an attempt."""
        pass

    @abstractmethod
    def list_tasks(self, status: str | None = None) -> list[EngineeringTask]:
        """List tasks, optionally filtered by status."""
        pass
