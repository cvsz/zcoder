"""Autonomous agent runtime compatibility surface for ZCoder.

The durable runtime uses :class:`EngineeringTask` and :class:`EngineeringStore`,
while older callers still import the legacy job runtime symbols from
``agent_runtime``.  Keep both surfaces available from this module so the
src-layout migration remains backward compatible.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from zcoder.domain.interfaces.engineering_store import EngineeringStore
from zcoder.domain.models.engineering import EngineeringTask
from zcoder.domain.models.legacy_job import (
    ApprovalRequest,
    FakeRuntime,
    Job,
    JobEvent,
    JobOrchestrator,
    JobStatus,
    JobStore,
    PolicyEngine,
    ToolPolicy,
)


class AgentRuntimeProtocol(Protocol):
    """Contract implemented by durable engineering runtime adapters."""

    def execute_task(
        self,
        task: EngineeringTask,
        store: EngineeringStore,
        validator: Callable[[], bool] | None = None,
    ) -> bool: ...


__all__ = [
    "AgentRuntimeProtocol",
    "ApprovalRequest",
    "FakeRuntime",
    "Job",
    "JobEvent",
    "JobOrchestrator",
    "JobStatus",
    "JobStore",
    "PolicyEngine",
    "ToolPolicy",
]
