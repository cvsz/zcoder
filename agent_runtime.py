"""agent_runtime.py — Autonomous Agent Runtime Platform for ZCoder

Supports:
  • Durable Engineering Task Model & SQLite/Postgres Engineering Store
  • Multi-mode Execution: Direct, Agent SDK, Managed Agents, and Fake (testing)
  • Operator Approvals & Command/Tool Safety Policy Engine
  • Workspace change tracking & Validation Pipeline
"""
from __future__ import annotations

import enum
import json
import time
from typing import Any, Callable, Dict, List, Optional, Protocol

from engineering_models import Attempt, EngineeringTask, TaskStatus
from engineering_orchestrator import EngineeringOrchestrator
from engineering_store_interface import EngineeringStore
from sqlite_engineering_store import SQLiteEngineeringStore


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


class AgentRuntimeProtocol(Protocol):
    def execute_task(self, task: EngineeringTask, store: EngineeringStore, validator: Optional[Callable[[], bool]] = None) -> bool: ...
