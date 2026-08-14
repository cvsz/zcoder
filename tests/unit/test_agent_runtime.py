"""tests/test_agent_runtime.py — Comprehensive tests for ZCoder Autonomous Agent Runtime"""

import os
import tempfile
from pathlib import Path

import pytest

from agent_runtime import (
    FakeRuntime,
    JobOrchestrator,
    PolicyEngine,
    ToolPolicy,
)
from legacy_job_models import (
    Job,
    JobStatus,
    JobStore,
)


@pytest.fixture
def temp_store():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)
    store = JobStore(db_path=db_path)
    yield store
    if db_path.exists():
        os.unlink(db_path)


def test_job_store_lifecycle_and_restart(temp_store):
    job = Job(id="job_test123", task="Fix bugs in test_auth.py", budget_usd=5.0)
    temp_store.save_job(job)

    # Reopen DB to simulate restart
    new_store = JobStore(db_path=temp_store.db_path)
    retrieved = new_store.get_job("job_test123")
    assert retrieved is not None
    assert retrieved.id == "job_test123"
    assert retrieved.task == "Fix bugs in test_auth.py"
    assert retrieved.status == JobStatus.CREATED
    assert retrieved.budget_usd == 5.0


def test_event_store_deterministic_sequence(temp_store):
    e1 = temp_store.add_event("job_1", "job.created", {"task": "test"})
    e2 = temp_store.add_event("job_1", "agent.started", {"model": "claude-sonnet-5"})
    assert e1.sequence == 1
    assert e2.sequence == 2

    events = temp_store.list_events("job_1")
    assert len(events) == 2
    assert events[0].event_type == "job.created"
    assert events[1].event_type == "agent.started"


def test_policy_engine_dangerous_command():
    policy = PolicyEngine()
    assert policy.evaluate_command("pytest -q") == ToolPolicy.ALLOW
    assert policy.evaluate_command("git status") == ToolPolicy.ALLOW
    assert policy.evaluate_command("rm -rf /tmp/test") == ToolPolicy.REQUIRE_APPROVAL
    assert policy.evaluate_command("git push -f origin main") == ToolPolicy.REQUIRE_APPROVAL


def test_orchestrator_successful_execution(temp_store):
    orch = JobOrchestrator(store=temp_store)
    job = orch.submit_job("Run tests and patch", runtime="fake")
    runtime = FakeRuntime(should_succeed=True, cost=0.10)
    success = orch.run_job(job.id, runtime, validator=lambda: True)

    assert success is True
    updated = temp_store.get_job(job.id)
    assert updated.status == JobStatus.SUCCEEDED
    assert updated.cost_usd == pytest.approx(0.10)


def test_orchestrator_budget_reached(temp_store):
    orch = JobOrchestrator(store=temp_store)
    job = orch.submit_job("Run tests and patch", runtime="fake", budget_usd=0.04)
    runtime = FakeRuntime(should_succeed=True, cost=0.05)
    success = orch.run_job(job.id, runtime)

    assert success is False
    updated = temp_store.get_job(job.id)
    assert updated.status == JobStatus.BUDGET_REACHED


def test_orchestrator_validation_failure(temp_store):
    orch = JobOrchestrator(store=temp_store)
    job = orch.submit_job("Run tests and patch", runtime="fake")
    runtime = FakeRuntime(should_succeed=True)
    success = orch.run_job(job.id, runtime, validator=lambda: False)

    assert success is False
    updated = temp_store.get_job(job.id)
    assert updated.status == JobStatus.FAILED
