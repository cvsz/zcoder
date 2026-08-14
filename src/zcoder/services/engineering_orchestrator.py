"""engineering_orchestrator.py — Orchestrates durable engineering tasks."""
from __future__ import annotations

from typing import Optional

from engineering_models import Attempt, EngineeringTask, TaskStatus
from engineering_store_interface import EngineeringStore


class EngineeringOrchestrator:
    def __init__(self, store: EngineeringStore):
        self.store = store

    def create_task(self, description: str) -> EngineeringTask:
        task = EngineeringTask(task_description=description)
        self.store.save_task(task)
        return task

    def start_task(self, task_id: str) -> Optional[Attempt]:
        task = self.store.get_task(task_id)
        if not task:
            return None
        
        task.status = TaskStatus.RUNNING
        self.store.save_task(task)
        
        attempt = Attempt(task_id=task_id)
        self.store.create_attempt(attempt)
        return attempt

    def update_task_status(self, task_id: str, status: TaskStatus) -> None:
        task = self.store.get_task(task_id)
        if task:
            task.status = status
            self.store.save_task(task)
