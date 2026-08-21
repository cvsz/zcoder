"""tests/test_github_orchestrator.py — Tests for GitHub PR Automation, CI Loop, Merge Policy & Webhooks"""

import json
import tempfile
import time
import urllib.error
from pathlib import Path

import pytest

from zcoder.core.exceptions import SecurityError
from zcoder.domain.models.legacy_job import Job, JobStatus, JobStore
from zcoder.services.github_orchestrator import (
    CheckConclusion,
    CheckRun,
    DistributedScheduler,
    FakeGitHubProvider,
    GitHubOrchestrator,
    GitHubProvider,
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
    gh_provider.set_checks(
        pr.head_sha,
        [CheckRun("chk1", "ci/tests", "completed", CheckConclusion.SUCCESS, "url", time.time(), time.time())],
    )
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
    gh_provider.set_checks(
        pr.head_sha,
        [
            CheckRun(
                "chk1", "test-suite", "completed", CheckConclusion.FAILURE, "url", time.time(), time.time()
            )
        ],
    )

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


# ---------------------------------------------------------------------------
# Slice F.1 — Provider-backed GitHub REST adapter regressions
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._body = json.dumps(payload).encode("utf-8") if payload is not None else b""
        self.status = status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.fixture
def captured_request(monkeypatch):
    """Patch safe_urlopen in the module namespace; capture the Request."""
    captured = {}

    def _fake_urlopen(req, timeout):
        captured["req"] = req
        captured["timeout"] = timeout
        return captured.get("response", _FakeResponse({}))

    monkeypatch.setattr("zcoder.services.github_orchestrator.safe_urlopen", _fake_urlopen)
    return captured


def test_provider_rejects_non_http_base_url():
    with pytest.raises(SecurityError):
        GitHubProvider(token="t", base_url="file:///etc/passwd")
    with pytest.raises(SecurityError):
        GitHubProvider(token="t", base_url="ftp://api.example.com")


def _header(req, name):
    for key, value in req.headers.items():
        if key.lower() == name.lower():
            return value
    return None


def test_provider_request_uses_configured_base_url_and_headers(captured_request):
    provider = GitHubProvider(token="secret-token", base_url="https://github.example.com/api/")
    provider.list_reviews("owner/repo", 7)
    req = captured_request["req"]
    assert req.full_url == "https://github.example.com/api/repos/owner/repo/pulls/7/reviews"
    assert _header(req, "Authorization") == "Bearer secret-token"
    assert _header(req, "X-GitHub-Api-Version") == "2022-11-28"
    assert captured_request["timeout"] == 30


def test_provider_create_branch_posts_ref_and_returns_base_sha(captured_request):
    provider = GitHubProvider(token="t")
    sha = provider.create_branch("owner/repo", "zcoder/job-1", "abc123")
    assert sha == "abc123"
    req = captured_request["req"]
    assert req.full_url == "https://api.github.com/repos/owner/repo/git/refs"
    assert req.get_method() == "POST"
    assert json.loads(req.data.decode("utf-8")) == {
        "ref": "refs/heads/zcoder/job-1",
        "sha": "abc123",
    }


def test_provider_json_body_sets_content_type(captured_request):
    provider = GitHubProvider(token="t")
    provider.create_branch("owner/repo", "b", "sha")
    assert _header(captured_request["req"], "Content-Type") == "application/json"
    provider.list_reviews("owner/repo", 3)
    assert _header(captured_request["req"], "Content-Type") is None


def test_provider_get_pr_propagates_schema_errors(monkeypatch):
    def _empty(req, timeout):
        return _FakeResponse({})

    monkeypatch.setattr("zcoder.services.github_orchestrator.safe_urlopen", _empty)
    provider = GitHubProvider(token="t")
    with pytest.raises(KeyError):
        provider.get_pr("owner/repo", 1)


def test_provider_create_pr_maps_response(captured_request):
    captured_request["response"] = _FakeResponse(
        {
            "number": 42,
            "title": "T",
            "body": "B",
            "head": {"ref": "h", "sha": "deadbeef"},
            "base": {"ref": "main"},
            "html_url": "https://github.com/owner/repo/pull/42",
            "draft": True,
        }
    )
    provider = GitHubProvider(token="t")
    pr = provider.create_pr("owner/repo", "T", "B", "h", "main")
    assert pr.number == 42
    assert pr.head_branch == "h"
    assert pr.head_sha == "deadbeef"
    assert pr.base_branch == "main"
    assert pr.draft is True
    assert pr.merged is False


def test_provider_get_pr_none_on_http_error(monkeypatch):
    def _raise(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr("zcoder.services.github_orchestrator.safe_urlopen", _raise)
    provider = GitHubProvider(token="t")
    assert provider.get_pr("owner/repo", 999) is None
    assert provider.list_checks("owner/repo", "ref") == []
    assert provider.list_reviews("owner/repo", 999) == []
    assert provider.merge_pr("owner/repo", 999) is False


def test_provider_error_message_does_not_leak_token(monkeypatch):
    def _raise(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 401, "Bad credentials", {}, None)

    monkeypatch.setattr("zcoder.services.github_orchestrator.safe_urlopen", _raise)
    provider = GitHubProvider(token="leaky-token-value")
    with pytest.raises(RuntimeError) as excinfo:
        provider.create_pr("owner/repo", "T", "B", "h", "main")
    assert "leaky-token-value" not in str(excinfo.value)


def test_provider_list_checks_maps_lowercase_conclusions_and_timestamps(captured_request):
    captured_request["response"] = _FakeResponse(
        {
            "check_runs": [
                {
                    "id": 111,
                    "name": "ci/tests",
                    "status": "completed",
                    "conclusion": "success",
                    "html_url": "u1",
                    "started_at": "2026-08-20T10:00:00Z",
                    "completed_at": "2026-08-20T10:05:00Z",
                },
                {
                    "id": 222,
                    "name": "ci/lint",
                    "status": "in_progress",
                    "conclusion": None,
                    "html_url": "u2",
                },
                {
                    "id": 333,
                    "name": "ci/weird",
                    "status": "completed",
                    "conclusion": "some_new_conclusion",
                    "html_url": "u3",
                    "started_at": "not-a-date",
                },
            ]
        }
    )
    provider = GitHubProvider(token="t")
    checks = provider.list_checks("owner/repo", "HEAD")
    by_name = {c.name: c for c in checks}
    assert len(checks) == 3
    assert by_name["ci/tests"].conclusion is CheckConclusion.SUCCESS
    assert by_name["ci/tests"].started_at > 1_000_000_000
    assert by_name["ci/tests"].completed_at is not None
    assert by_name["ci/lint"].conclusion is None
    assert by_name["ci/weird"].conclusion is None  # unknown conclusion does not crash
    assert by_name["ci/weird"].started_at > 0  # unparseable timestamp -> now fallback


def test_provider_merge_pr_success(captured_request):
    captured_request["response"] = _FakeResponse({"merged": True, "sha": "abc"})
    provider = GitHubProvider(token="t")
    assert provider.merge_pr("owner/repo", 5, strategy="merge") is True
    req = captured_request["req"]
    assert req.get_method() == "PUT"
    assert json.loads(req.data.decode("utf-8")) == {"merge_method": "merge"}


def test_provider_empty_response_body_tolerated(captured_request):
    captured_request["response"] = _FakeResponse(None)
    provider = GitHubProvider(token="t")
    assert provider.merge_pr("owner/repo", 5) is True
