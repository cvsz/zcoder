"""swarm.py — Agent Swarm Coordination for ZCoder.

Implements distributed multi-agent swarm patterns for collaborative task
execution across multiple agent instances. Provides:

  • SwarmAgent — an individual agent within a swarm with inbox/outbox
  • SwarmCoordinator — manages a swarm of agents, distributes work,
    aggregates results, and handles failure recovery
  • SwarmTask — a distributable task with dependencies and requirements
  • SwarmResult — aggregated results from swarm execution
  • SwarmTopology — defines how agents are connected (star, mesh, ring)

Follows the "Model-Visible ⟺ Logged" pattern and integrates with the
existing SessionProjection and session event infrastructure.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, cast


class SwarmRole(StrEnum):
    """Role of an agent within a swarm."""

    COORDINATOR = "coordinator"
    WORKER = "worker"
    SCOUT = "scout"
    AGGREGATOR = "aggregator"


class SwarmStatus(StrEnum):
    """Status of a swarm."""

    FORMING = "forming"
    ACTIVE = "active"
    IDLE = "idle"
    DISPERSED = "dispersed"
    ERROR = "error"


class SwarmTaskStatus(StrEnum):
    """Status of a swarm task."""

    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass(frozen=True)
class SwarmTopology:
    """Defines how agents are connected within a swarm."""

    name: str  # "star", "mesh", "ring", "hierarchy"
    max_neighbors: int = 3
    broadcast_enabled: bool = True


@dataclass
class SwarmTask:
    """A distributable task within a swarm."""

    id: str
    description: str
    required_capability: str | None = None
    depends_on: list[str] = field(default_factory=list)
    status: SwarmTaskStatus = SwarmTaskStatus.PENDING
    assigned_agent: str | None = None
    result: Any = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None


@dataclass
class SwarmResult:
    """Aggregated results from swarm execution."""

    swarm_id: str
    task_id: str
    status: SwarmTaskStatus
    agent_results: dict[str, Any] = field(default_factory=dict)
    aggregated_output: Any = None
    error: str | None = None
    duration_seconds: float = 0.0


@dataclass
class SwarmAgent:
    """An individual agent within a swarm."""

    id: str
    role: SwarmRole = SwarmRole.WORKER
    capabilities: list[str] = field(default_factory=list)
    status: SwarmStatus = SwarmStatus.IDLE
    current_task: str | None = None
    inbox: list[dict[str, Any]] = field(default_factory=list)
    outbox: list[dict[str, Any]] = field(default_factory=list)
    completed_tasks: list[str] = field(default_factory=list)
    failed_tasks: list[str] = field(default_factory=list)
    last_heartbeat: float = field(default_factory=time.time)

    def send(self, message: dict[str, Any]) -> None:
        """Send a message to the swarm outbox."""
        self.outbox.append(message)

    def receive(self, message: dict[str, Any]) -> None:
        """Receive a message into the swarm inbox."""
        self.inbox.append(message)

    def claim_task(self, task_id: str) -> None:
        """Mark a task as claimed by this agent."""
        self.current_task = task_id
        self.status = SwarmStatus.ACTIVE

    def complete_task(self, task_id: str, result: Any) -> None:
        """Mark a task as completed."""
        self.current_task = None
        self.status = SwarmStatus.IDLE
        self.completed_tasks.append(task_id)

    def fail_task(self, task_id: str, error: str) -> None:
        """Mark a task as failed."""
        self.current_task = None
        self.status = SwarmStatus.IDLE
        self.failed_tasks.append(task_id)

    def heartbeat(self) -> None:
        """Update the agent's heartbeat timestamp."""
        self.last_heartbeat = time.time()

    def is_alive(self, timeout: float = 30.0) -> bool:
        """Check if the agent is alive based on heartbeat."""
        return time.time() - self.last_heartbeat < timeout


@dataclass
class Swarm:
    """A swarm of agents with coordinated task execution."""

    id: str
    name: str
    topology: SwarmTopology = field(default_factory=lambda: SwarmTopology(name="star"))
    agents: dict[str, SwarmAgent] = field(default_factory=dict)
    tasks: dict[str, SwarmTask] = field(default_factory=dict)
    results: dict[str, SwarmResult] = field(default_factory=dict)
    status: SwarmStatus = SwarmStatus.FORMING
    created_at: float = field(default_factory=time.time)

    def add_agent(self, agent: SwarmAgent) -> None:
        """Add an agent to the swarm."""
        self.agents[agent.id] = agent

    def remove_agent(self, agent_id: str) -> None:
        """Remove an agent from the swarm."""
        self.agents.pop(agent_id, None)

    def get_agent(self, agent_id: str) -> SwarmAgent | None:
        """Get an agent by ID."""
        return self.agents.get(agent_id)

    def get_available_agents(self, capability: str | None = None) -> list[SwarmAgent]:
        """Get available agents, optionally filtered by capability."""
        return [
            a
            for a in self.agents.values()
            if a.status == SwarmStatus.IDLE and (capability is None or capability in a.capabilities)
        ]

    def add_task(self, task: SwarmTask) -> None:
        """Add a task to the swarm."""
        self.tasks[task.id] = task

    def get_task(self, task_id: str) -> SwarmTask | None:
        """Get a task by ID."""
        return self.tasks.get(task_id)

    def get_pending_tasks(self) -> list[SwarmTask]:
        """Get all pending tasks."""
        return [t for t in self.tasks.values() if t.status == SwarmTaskStatus.PENDING]

    def get_ready_tasks(self) -> list[SwarmTask]:
        """Get tasks whose dependencies are all completed."""
        completed = {t.id for t in self.tasks.values() if t.status == SwarmTaskStatus.COMPLETED}
        return [
            t
            for t in self.tasks.values()
            if t.status == SwarmTaskStatus.PENDING and all(dep in completed for dep in t.depends_on)
        ]


@dataclass
class SwarmCoordinator:
    """Coordinates a swarm of agents for distributed task execution."""

    swarm: Swarm
    assignment_strategy: str = "capability_based"  # "round_robin", "capability_based", "least_loaded"
    task_timeout: float = 60.0
    heartbeat_timeout: float = 30.0

    def assign_task(self, task: SwarmTask) -> SwarmAgent | None:
        """Assign a task to an available agent based on strategy."""
        available = self.swarm.get_available_agents(task.required_capability)
        if not available:
            task.status = SwarmTaskStatus.FAILED
            task.error = "No available agent"
            return None

        if self.assignment_strategy == "round_robin":
            agent = available[0]
        elif self.assignment_strategy == "least_loaded":
            agent = min(available, key=lambda a: len(a.completed_tasks) + len(a.failed_tasks))
        else:  # capability_based
            # Prefer agents with matching capability
            matching = [a for a in available if task.required_capability in a.capabilities]
            agent = matching[0] if matching else available[0]

        agent.claim_task(task.id)
        task.assigned_agent = agent.id
        task.status = SwarmTaskStatus.ASSIGNED
        task.started_at = time.time()
        return agent

    async def execute_task(self, task: SwarmTask) -> SwarmResult:
        """Execute a single task through the swarm."""
        start_time = time.time()
        agent = self.assign_task(task)
        if agent is None:
            task.status = SwarmTaskStatus.FAILED
            task.error = "No available agent"
            return SwarmResult(
                swarm_id=self.swarm.id,
                task_id=task.id,
                status=task.status,
                error=task.error,
                duration_seconds=time.time() - start_time,
            )

        try:
            # Simulate task execution by processing the task through the agent
            result = await self._execute_on_agent(agent, task)
            agent.complete_task(task.id, result)
            task.completed_at = time.time()
            task.status = SwarmTaskStatus.COMPLETED
            task.result = result
            return SwarmResult(
                swarm_id=self.swarm.id,
                task_id=task.id,
                status=task.status,
                agent_results={agent.id: result},
                aggregated_output=result,
                duration_seconds=time.time() - start_time,
            )
        except Exception as exc:
            agent.fail_task(task.id, str(exc))
            task.status = SwarmTaskStatus.FAILED
            task.error = str(exc)
            return SwarmResult(
                swarm_id=self.swarm.id,
                task_id=task.id,
                status=task.status,
                agent_results={agent.id: None},
                error=str(exc),
                duration_seconds=time.time() - start_time,
            )

    async def _execute_on_agent(self, agent: SwarmAgent, task: SwarmTask) -> Any:
        """Execute a task on a specific agent (simulated)."""
        # Simulate async work
        await asyncio.sleep(0.01)
        return {
            "agent_id": agent.id,
            "task_id": task.id,
            "result": f"Processed '{task.description}' on {agent.role}",
            "capability_used": task.required_capability,
        }

    async def execute_swarm(self) -> list[SwarmResult]:
        """Execute all ready tasks in the swarm respecting dependencies."""
        results: list[SwarmResult] = []

        while True:
            ready_tasks = self.swarm.get_ready_tasks()
            if not ready_tasks:
                break

            # Execute all ready tasks concurrently
            task_results = await asyncio.gather(
                *[self.execute_task(t) for t in ready_tasks],
                return_exceptions=True,
            )

            for result in task_results:
                if isinstance(result, Exception):
                    results.append(
                        SwarmResult(
                            swarm_id=self.swarm.id,
                            task_id="unknown",
                            status=SwarmTaskStatus.FAILED,
                            error=str(result),
                        )
                    )
                else:
                    results.append(cast(SwarmResult, result))

        self.swarm.status = SwarmStatus.IDLE
        return results

    def check_agent_health(self) -> list[str]:
        """Check agent health and return list of dead agent IDs."""
        dead_agents: list[str] = []
        for agent_id, agent in self.swarm.agents.items():
            if not agent.is_alive(self.heartbeat_timeout):
                dead_agents.append(agent_id)
        return dead_agents

    def recover_dead_agents(self) -> list[str]:
        """Reassign tasks from dead agents and mark them as dispersed."""
        dead_ids = self.check_agent_health()
        recovered: list[str] = []

        for dead_id in dead_ids:
            dead_agent = self.swarm.get_agent(dead_id)
            if dead_agent is None:
                continue

            # Reassign current task if any
            if dead_agent.current_task:
                task = self.swarm.get_task(dead_agent.current_task)
                if task and task.status == SwarmTaskStatus.IN_PROGRESS:
                    task.status = SwarmTaskStatus.PENDING
                    task.assigned_agent = None
                    task.started_at = None
                    # Re-assign
                    new_agent = self.assign_task(task)
                    if new_agent:
                        recovered.append(new_agent.id)

            dead_agent.status = SwarmStatus.DISPERSED
            recovered.append(dead_id)

        return recovered

    def get_swarm_metrics(self) -> dict[str, Any]:
        """Get swarm-wide metrics."""
        total_agents = len(self.swarm.agents)
        active_agents = sum(1 for a in self.swarm.agents.values() if a.status == SwarmStatus.ACTIVE)
        idle_agents = sum(1 for a in self.swarm.agents.values() if a.status == SwarmStatus.IDLE)
        total_tasks = len(self.swarm.tasks)
        completed_tasks = sum(1 for t in self.swarm.tasks.values() if t.status == SwarmTaskStatus.COMPLETED)
        failed_tasks = sum(1 for t in self.swarm.tasks.values() if t.status == SwarmTaskStatus.FAILED)

        return {
            "swarm_id": self.swarm.id,
            "swarm_name": self.swarm.name,
            "topology": self.swarm.topology.name,
            "total_agents": total_agents,
            "active_agents": active_agents,
            "idle_agents": idle_agents,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "failed_tasks": failed_tasks,
            "completion_rate": completed_tasks / total_tasks if total_tasks > 0 else 0.0,
            "status": self.swarm.status.value,
        }


def create_swarm(
    name: str,
    topology_name: str = "star",
    num_agents: int = 5,
    coordinator_strategy: str = "capability_based",
) -> SwarmCoordinator:
    """Create a swarm with the specified number of agents."""
    topology = SwarmTopology(name=topology_name)
    swarm = Swarm(id=f"swarm_{int(time.time())}", name=name, topology=topology)

    roles = [SwarmRole.COORDINATOR, SwarmRole.WORKER, SwarmRole.SCOUT, SwarmRole.AGGREGATOR]
    for i in range(num_agents):
        role = roles[i % len(roles)]
        agent = SwarmAgent(
            id=f"agent_{i}",
            role=role,
            capabilities=["general", role.value],
        )
        swarm.add_agent(agent)

    return SwarmCoordinator(swarm=swarm, assignment_strategy=coordinator_strategy)


__all__ = [
    "SwarmRole",
    "SwarmStatus",
    "SwarmTaskStatus",
    "SwarmTopology",
    "SwarmTask",
    "SwarmResult",
    "SwarmAgent",
    "Swarm",
    "SwarmCoordinator",
    "create_swarm",
]
