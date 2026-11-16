"""Tests for zcoder.agent.orchestration.swarm - Agent swarm coordination."""

from __future__ import annotations

import pytest

from zcoder.agent.orchestration.swarm import (
    Swarm,
    SwarmAgent,
    SwarmRole,
    SwarmStatus,
    SwarmTask,
    SwarmTaskStatus,
    SwarmTopology,
    create_swarm,
)


class TestSwarmTopology:
    """Tests for SwarmTopology dataclass."""

    def test_creation(self):
        topology = SwarmTopology(name="mesh", max_neighbors=5)
        assert topology.name == "mesh"
        assert topology.max_neighbors == 5
        assert topology.broadcast_enabled is True


class TestSwarmTask:
    """Tests for SwarmTask dataclass."""

    def test_creation(self):
        task = SwarmTask(
            id="task_1",
            description="Process data",
        )
        assert task.id == "task_1"
        assert task.description == "Process data"
        assert task.required_capability is None
        assert task.depends_on == []
        assert task.status == SwarmTaskStatus.PENDING
        assert task.assigned_agent is None
        assert task.result is None
        assert task.error is None
        assert task.created_at > 0


class TestSwarmAgent:
    """Tests for SwarmAgent dataclass."""

    def test_creation(self):
        agent = SwarmAgent(
            id="agent_1",
            role="worker",
        )
        assert agent.id == "agent_1"
        assert agent.role == "worker"
        assert agent.capabilities == []
        assert agent.status == "idle"
        assert agent.current_task is None
        assert agent.inbox == []
        assert agent.outbox == []
        assert agent.completed_tasks == []
        assert agent.failed_tasks == []

    def test_send_receive(self):
        agent = SwarmAgent(id="agent_1")
        agent.send({"message": "hello"})
        assert len(agent.outbox) == 1
        assert agent.outbox[0] == {"message": "hello"}

        agent.receive({"message": "hi"})
        assert len(agent.inbox) == 1
        assert agent.inbox[0] == {"message": "hi"}

    def test_claim_complete_task(self):
        agent = SwarmAgent(id="agent_1")
        agent.claim_task("task_1")
        assert agent.current_task == "task_1"
        assert agent.status == "active"

        agent.complete_task("task_1", {"result": "done"})
        assert agent.current_task is None
        assert agent.status == "idle"
        assert "task_1" in agent.completed_tasks

    def test_fail_task(self):
        agent = SwarmAgent(id="agent_1")
        agent.claim_task("task_1")
        agent.fail_task("task_1", "Something went wrong")
        assert agent.current_task is None
        assert agent.status == "idle"
        assert "task_1" in agent.failed_tasks

    def test_heartbeat(self):
        agent = SwarmAgent(id="agent_1")
        before = agent.last_heartbeat
        agent.heartbeat()
        assert agent.last_heartbeat > before
        assert agent.is_alive() is True

    def test_is_alive_timeout(self):
        agent = SwarmAgent(id="agent_1")
        agent.last_heartbeat = 0  # Very old heartbeat
        assert agent.is_alive(timeout=30.0) is False


class TestSwarm:
    """Tests for Swarm dataclass."""

    def test_creation(self):
        swarm = Swarm(id="swarm_1", name="test-swarm")
        assert swarm.id == "swarm_1"
        assert swarm.name == "test-swarm"
        assert swarm.topology.name == "star"
        assert swarm.agents == {}
        assert swarm.tasks == {}
        assert swarm.results == {}
        assert swarm.status == "forming"
        assert swarm.created_at > 0

    def test_add_remove_agent(self):
        swarm = Swarm(id="swarm_1", name="test-swarm")
        agent = SwarmAgent(id="agent_1")
        swarm.add_agent(agent)
        assert len(swarm.agents) == 1
        assert swarm.get_agent("agent_1") is agent

        swarm.remove_agent("agent_1")
        assert len(swarm.agents) == 0
        assert swarm.get_agent("agent_1") is None

    def test_get_available_agents(self):
        swarm = Swarm(id="swarm_1", name="test-swarm")
        agent1 = SwarmAgent(id="agent_1", capabilities=["python"])
        agent2 = SwarmAgent(id="agent_2", capabilities=["javascript"])
        swarm.add_agent(agent1)
        swarm.add_agent(agent2)

        all_available = swarm.get_available_agents()
        assert len(all_available) == 2

        python_available = swarm.get_available_agents(capability="python")
        assert len(python_available) == 1
        assert python_available[0].id == "agent_1"

    def test_add_get_task(self):
        swarm = Swarm(id="swarm_1", name="test-swarm")
        task = SwarmTask(id="task_1", description="Do something")
        swarm.add_task(task)
        assert swarm.get_task("task_1") is task
        assert swarm.get_task("nonexistent") is None

    def test_get_pending_tasks(self):
        swarm = Swarm(id="swarm_1", name="test-swarm")
        task1 = SwarmTask(id="task_1", description="Task 1")
        task2 = SwarmTask(id="task_2", description="Task 2")
        task3 = SwarmTask(id="task_3", description="Task 3")
        task3.status = SwarmTaskStatus.COMPLETED
        swarm.add_task(task1)
        swarm.add_task(task2)
        swarm.add_task(task3)

        pending = swarm.get_pending_tasks()
        assert len(pending) == 2


class TestSwarmCoordinator:
    """Tests for SwarmCoordinator."""

    @pytest.fixture
    def coordinator(self):
        return create_swarm(name="test-swarm", num_agents=3)

    def test_creation(self):
        coordinator = create_swarm(name="test-swarm", num_agents=5)
        assert coordinator.swarm.name == "test-swarm"
        assert len(coordinator.swarm.agents) == 5
        assert coordinator.assignment_strategy == "capability_based"
        assert coordinator.task_timeout == 60.0
        assert coordinator.heartbeat_timeout == 30.0

    def test_assign_task(self, coordinator):
        task = SwarmTask(id="task_1", description="Process data", required_capability="general")
        agent = coordinator.assign_task(task)
        assert agent is not None
        assert task.assigned_agent == agent.id
        assert task.status == SwarmTaskStatus.ASSIGNED
        assert task.started_at is not None

    def test_assign_task_no_available_agent(self):
        coordinator = create_swarm(name="test-swarm", num_agents=0)
        task = SwarmTask(id="task_1", description="Process data")
        agent = coordinator.assign_task(task)
        assert agent is None
        assert task.status == SwarmTaskStatus.FAILED
        assert task.error == "No available agent"

    @pytest.mark.asyncio
    async def test_execute_task(self, coordinator):
        task = SwarmTask(id="task_1", description="Process data", required_capability="general")
        result = await coordinator.execute_task(task)
        assert result.status == SwarmTaskStatus.COMPLETED
        assert result.error is None
        assert result.duration_seconds > 0
        assert task.status == SwarmTaskStatus.COMPLETED
        assert task.result is not None

    @pytest.mark.asyncio
    async def test_execute_swarm(self, coordinator):
        task1 = SwarmTask(id="task_1", description="Task 1")
        task2 = SwarmTask(id="task_2", description="Task 2")
        coordinator.swarm.add_task(task1)
        coordinator.swarm.add_task(task2)

        results = await coordinator.execute_swarm()
        assert len(results) == 2
        assert all(r.status == SwarmTaskStatus.COMPLETED for r in results)
        assert coordinator.swarm.status == SwarmStatus.IDLE

    @pytest.mark.asyncio
    async def test_execute_swarm_with_dependencies(self, coordinator):
        task1 = SwarmTask(id="task_1", description="Task 1")
        task2 = SwarmTask(id="task_2", description="Task 2", depends_on=["task_1"])
        coordinator.swarm.add_task(task1)
        coordinator.swarm.add_task(task2)

        results = await coordinator.execute_swarm()
        assert len(results) == 2
        assert all(r.status == SwarmTaskStatus.COMPLETED for r in results)

    def test_check_agent_health(self, coordinator):
        # All agents should be alive initially
        dead = coordinator.check_agent_health()
        assert len(dead) == 0

        # Make one agent dead
        agent = coordinator.swarm.get_agent("agent_0")
        agent.last_heartbeat = 0
        dead = coordinator.check_agent_health()
        assert "agent_0" in dead

    def test_recover_dead_agents(self, coordinator):
        agent = coordinator.swarm.get_agent("agent_0")
        agent.last_heartbeat = 0
        recovered = coordinator.recover_dead_agents()
        assert "agent_0" in recovered

    def test_get_swarm_metrics(self, coordinator):
        metrics = coordinator.get_swarm_metrics()
        assert metrics["swarm_id"] == coordinator.swarm.id
        assert metrics["swarm_name"] == "test-swarm"
        assert metrics["topology"] == "star"
        assert metrics["total_agents"] == 3
        assert metrics["status"] == "forming"
        assert 0.0 <= metrics["completion_rate"] <= 1.0


class TestCreateSwarm:
    """Tests for create_swarm factory function."""

    def test_create_default(self):
        swarm = create_swarm(name="test")
        assert swarm.swarm.name == "test"
        assert len(swarm.swarm.agents) == 5
        assert swarm.assignment_strategy == "capability_based"

    def test_create_custom(self):
        swarm = create_swarm(
            name="custom",
            topology_name="mesh",
            num_agents=10,
            coordinator_strategy="least_loaded",
        )
        assert swarm.swarm.name == "custom"
        assert swarm.swarm.topology.name == "mesh"
        assert len(swarm.swarm.agents) == 10
        assert swarm.assignment_strategy == "least_loaded"


class TestRoleEnum:
    """Tests for SwarmRole enum."""

    def test_values(self):
        assert SwarmRole.COORDINATOR == "coordinator"
        assert SwarmRole.WORKER == "worker"
        assert SwarmRole.SCOUT == "scout"
        assert SwarmRole.AGGREGATOR == "aggregator"


class TestSwarmStatusEnum:
    """Tests for SwarmStatus enum."""

    def test_values(self):
        assert SwarmStatus.FORMING == "forming"
        assert SwarmStatus.ACTIVE == "active"
        assert SwarmStatus.IDLE == "idle"
        assert SwarmStatus.DISPERSED == "dispersed"
        assert SwarmStatus.ERROR == "error"


class TestSwarmTaskStatusEnum:
    """Tests for SwarmTaskStatus enum."""

    def test_values(self):
        assert SwarmTaskStatus.PENDING == "pending"
        assert SwarmTaskStatus.ASSIGNED == "assigned"
        assert SwarmTaskStatus.IN_PROGRESS == "in_progress"
        assert SwarmTaskStatus.COMPLETED == "completed"
        assert SwarmTaskStatus.FAILED == "failed"
        assert SwarmTaskStatus.TIMEOUT == "timeout"
