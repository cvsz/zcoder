"""Tests for zcoder.agent.orchestration.workflow - Workflow engine."""

from __future__ import annotations

import asyncio

import pytest

from zcoder.agent.orchestration.workflow import AsyncWorkflowStep, Workflow, WorkflowEngine, WorkflowStep


class TestWorkflowStep:
    """Tests for WorkflowStep dataclass."""

    def test_creation(self):
        step = WorkflowStep(
            step_id="step1",
            instruction="Do something",
        )
        assert step.step_id == "step1"
        assert step.instruction == "Do something"
        assert step.depends_on == []
        assert step.model is None
        assert step.max_tokens == 2048

    def test_creation_full(self):
        step = WorkflowStep(
            step_id="step2",
            instruction="Do something else",
            depends_on=["step1"],
            model="zcoder-pro",
            max_tokens=4096,
        )
        assert step.step_id == "step2"
        assert step.instruction == "Do something else"
        assert step.depends_on == ["step1"]
        assert step.model == "zcoder-pro"
        assert step.max_tokens == 4096


class TestAsyncWorkflowStep:
    """Tests for AsyncWorkflowStep dataclass."""

    def test_creation(self):
        async def my_fn():
            return "result"

        step = AsyncWorkflowStep(
            id="step1",
            fn=my_fn,
        )
        assert step.id == "step1"
        assert step.depends_on == []

    def test_creation_with_deps(self):
        async def my_fn():
            return "result"

        step = AsyncWorkflowStep(
            id="step2",
            fn=my_fn,
            depends_on=["step1"],
        )
        assert step.id == "step2"
        assert step.depends_on == ["step1"]


class TestWorkflow:
    """Tests for Workflow dataclass."""

    def test_creation(self):
        workflow = Workflow(
            name="test-workflow",
            steps=[],
        )
        assert workflow.name == "test-workflow"
        assert workflow.steps == []
        assert workflow.model == "zcoder-pro"

    def test_creation_with_steps(self):
        step = WorkflowStep(
            step_id="step1",
            instruction="Do something",
        )
        workflow = Workflow(
            name="test-workflow",
            steps=[step],
            model="zcoder-promax",
        )
        assert workflow.name == "test-workflow"
        assert len(workflow.steps) == 1
        assert workflow.model == "zcoder-promax"


class TestWorkflowEngine:
    """Tests for WorkflowEngine."""

    def test_creation_default(self):
        engine = WorkflowEngine()
        assert engine.max_concurrent == 10
        assert engine._semaphore is None

    def test_creation_custom(self):
        engine = WorkflowEngine(max_concurrent=5)
        assert engine.max_concurrent == 5

    def test_creation_invalid(self):
        with pytest.raises(ValueError, match="max_concurrent must be > 0"):
            WorkflowEngine(max_concurrent=0)

        with pytest.raises(ValueError, match="max_concurrent must be > 0"):
            WorkflowEngine(max_concurrent=-1)

    @pytest.mark.asyncio
    async def test_execute_single_step(self):
        engine = WorkflowEngine()

        async def step_fn():
            return "result1"

        steps = [
            AsyncWorkflowStep(id="step1", fn=step_fn),
        ]
        results = await engine.execute(steps)
        assert len(results) == 1
        assert results[0] == "result1"

    @pytest.mark.asyncio
    async def test_execute_multiple_steps_sequential(self):
        engine = WorkflowEngine(max_concurrent=1)

        call_order = []

        async def step1_fn():
            call_order.append("step1")
            return "result1"

        async def step2_fn():
            call_order.append("step2")
            return "result2"

        steps = [
            AsyncWorkflowStep(id="step1", fn=step1_fn),
            AsyncWorkflowStep(id="step2", fn=step2_fn),
        ]
        results = await engine.execute(steps)
        assert len(results) == 2
        assert results[0] == "result1"
        assert results[1] == "result2"

    @pytest.mark.asyncio
    async def test_execute_with_dependencies(self):
        engine = WorkflowEngine(max_concurrent=2)

        execution_order = []

        async def step_a():
            execution_order.append("a")
            await asyncio.sleep(0.01)
            return "result_a"

        async def step_b():
            execution_order.append("b")
            await asyncio.sleep(0.01)
            return "result_b"

        async def step_c():
            execution_order.append("c")
            # Depends on both a and b
            return "result_c"

        steps = [
            AsyncWorkflowStep(id="a", fn=step_a),
            AsyncWorkflowStep(id="b", fn=step_b),
            AsyncWorkflowStep(id="c", fn=step_c, depends_on=["a", "b"]),
        ]
        results = await engine.execute(steps)
        assert len(results) == 3
        # a and b should run first (in some order), then c
        assert execution_order[2] == "c"  # c runs last

    @pytest.mark.asyncio
    async def test_execute_dependency_not_found(self):
        engine = WorkflowEngine()

        async def step_fn():
            return "result"

        steps = [
            AsyncWorkflowStep(id="step1", fn=step_fn, depends_on=["nonexistent"]),
        ]
        # Should not raise, just execute without waiting for missing dep
        results = await engine.execute(steps)
        assert len(results) == 1
        assert results[0] == "result"

    @pytest.mark.asyncio
    async def test_execute_empty_steps(self):
        engine = WorkflowEngine()
        results = await engine.execute([])
        assert results == []

    @pytest.mark.asyncio
    async def test_execute_step_exception(self):
        engine = WorkflowEngine()

        async def failing_fn():
            raise ValueError("Step failed")

        steps = [
            AsyncWorkflowStep(id="step1", fn=failing_fn),
        ]
        results = await engine.execute(steps)
        assert len(results) == 1
        assert isinstance(results[0], dict)
        assert "error" in results[0]
        assert results[0]["step_id"] == "step1"
        assert "Step failed" in results[0]["error"]

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrency(self):
        engine = WorkflowEngine(max_concurrent=1)

        max_concurrent = 0
        current_concurrent = 0

        async def slow_fn():
            nonlocal current_concurrent, max_concurrent
            current_concurrent += 1
            max_concurrent = max(max_concurrent, current_concurrent)
            await asyncio.sleep(0.05)
            current_concurrent -= 1
            return "done"

        steps = [AsyncWorkflowStep(id=f"step{i}", fn=slow_fn) for i in range(5)]
        results = await engine.execute(steps)
        assert len(results) == 5
        assert max_concurrent == 1  # Should never exceed 1 with max_concurrent=1
