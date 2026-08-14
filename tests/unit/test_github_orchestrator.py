"""tests/test_github_orchestrator.py — Tests for GitHub PR Automation, CI Loop, Merge Policy & Webhooks"""
import tempfile
import time
from pathlib import Path
import pytest

from legacy_job_models import Job, JobStatus, JobStore
from github_orchestrator import (
    CheckConclusion,
    CheckRun,
    DistributedScheduler,
    FakeGitHubProvider,
    GitHubOrchestrator,
    PullRequest,
    ReviewState,
)


@pytest.fixture
def test_setup():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)
    store = JobStore(db_path=db_path)
    gh_provider = FakeGitHubProvider()
    orch = GitHubOrchestrator(github_provider=gh_provider, store=store)
    yield store, gh_provider, orch
    if db_path.exists():
        db_path.unlink()


def test_pr_creation_and_idempotency(test_setup):
    store, gh_provider, orch = test_setup
    job = Job(id="job_gh_01", task="Fix auth check")
    store.save_job(job)

    pr1 = orch.create_pull_request_for_job("job_gh_01", "owner/repo", "Fix auth", "Summary", "zcoder/job-01")
    assert pr1.number == 1
    assert pr1.head_branch == "zcoder/job-01"

    # Second call creates no duplicate PR
    pr2 = orch.create_pull_request_for_job("job_gh_01", "owner/repo", "Fix auth", "Summary", "zcoder/job-01")
    assert pr2.number == 1


def test_merge_readiness_evaluation(test_setup):
    store, gh_provider, orch = test_setup
    job = Job(id="job_gh_02", task="Feature PR")
    store.save_job(job)
    pr = orch.create_pull_request_for_job("job_gh_02", "owner/repo", "Feature", "Body", "zcoder/job-02")

    # 1. Initially unready (missing checks & review)
    ready, reason = orch.evaluate_merge_readiness("owner/repo", pr.number, required_checks=["ci/tests"])
    assert ready is False

    # 2. Add passing check
    gh_provider.set_checks(pr.head_sha, [
        CheckRun("chk1", "ci/tests", "completed", CheckConclusion.SUCCESS, "url", time.time(), time.time())
    ])
    ready, reason = orch.evaluate_merge_readiness("owner/repo", pr.number, required_checks=["ci/tests"])
    assert ready is False
    assert "Pending human review" in reason

    # 3. Add approved review
    gh_provider.add_review(pr.number, ReviewState.APPROVED, author="senior_dev")
    ready, reason = orch.evaluate_merge_readiness("owner/repo", pr.number, required_checks=["ci/tests"])
    assert ready is True
    assert reason == "READY_FOR_MERGE"


def test_ci_repair_loop(test_setup):
    store, gh_provider, orch = test_setup
    job = Job(id="job_gh_03", task="CI Fix")
    store.save_job(job)
    pr = orch.create_pull_request_for_job("job_gh_03", "owner/repo", "CI Fix", "Body", "zcoder/job-03")

    # Initial check is failing
    gh_provider.set_checks(pr.head_sha, [
        CheckRun("chk1", "test-suite", "completed", CheckConclusion.FAILURE, "url", time.time(), time.time())
    ])

    repaired = orch.execute_ci_repair_loop(job.id, "owner/repo", pr.number, max_repairs=3)
    assert repaired is True

    # Events should show repair attempts
    events = store.list_events(job.id)
    repair_events = [e for e in events if e.event_type == "ci.repair_attempt"]
    assert len(repair_events) >= 1


def test_webhook_verification_and_deduplication(test_setup):
    _, _, orch = test_setup
    secret = "test_webhook_secret_key"
    payload = b'{"action": "completed", "workflow_run": {"id": 123}}'

    # Compute valid signature
    import hashlib
    import hmac
    sig = "sha256=" + hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()

    assert orch.verify_webhook(payload, sig, secret) is True
    assert orch.verify_webhook(payload, "sha256=invalid_sig", secret) is False

    # Delivery deduplication
    assert orch.handle_webhook_delivery("del_001", "check_run", {}) is True
    assert orch.handle_webhook_delivery("del_001", "check_run", {}) is False  # Second delivery ignored


def test_distributed_scheduler_atomic_claim(test_setup):
    store, _, _ = test_setup
    job = Job(id="job_ready_1", task="Queued task", status=JobStatus.READY)
    store.save_job(job)

    scheduler = DistributedScheduler(store=store)
    claimed = scheduler.claim_next_job("worker_node_1")
    assert claimed is not None
    assert claimed.id == "job_ready_1"
    assert claimed.status == JobStatus.RUNNING
    assert claimed.metadata["claimed_by"] == "worker_node_1"

    # Second worker cannot claim the same job
    second_claim = scheduler.claim_next_job("worker_node_2")
    assert second_claim is None
