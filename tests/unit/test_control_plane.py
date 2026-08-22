"""tests/test_control_plane.py — Tests for PostgreSQL/Storage Control Plane, Fencing Tokens, Outbox & Fleet Registry"""

import tempfile
from pathlib import Path

import pytest

from zcoder.domain.services.control_plane import (
    ControlPlaneStore,
    FleetRepository,
    GitHubInstallation,
)
from zcoder.services.agent_runtime import JobStatus


@pytest.fixture
def cp_store():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)
    store = ControlPlaneStore(db_path=db_path)
    yield store
    if db_path.exists():
        db_path.unlink()


def test_atomic_claim_with_monotonic_fencing_token(cp_store):
    with sqlite3_conn(cp_store.db_path) as conn:
        conn.execute(
            """
            INSERT INTO jobs (id, task, runtime, status, workspace, created_at, updated_at, model, budget_usd, cost_usd, claim_generation, lease_expires_at, metadata)
            VALUES ('job_fence_1', 'Task 1', 'direct', 'READY', '.', 100.0, 100.0, 'claude-sonnet-5', 5.0, 0.0, 0, 0, '{}')
        """
        )

    # Worker A claims job -> generation token = 1
    res = cp_store.claim_job_with_fencing("worker_A", lease_duration=60.0)
    assert res is not None
    job, gen_token = res
    assert job.id == "job_fence_1"
    assert gen_token == 1

    # Worker A updates job using valid generation token
    mutated = cp_store.mutate_with_fencing(
        job.id, "worker_A", fencing_token=1, status=JobStatus.RUNNING, cost_usd=0.05
    )
    assert mutated is True

    # Stale Worker attempts update with old token 0 -> REJECTED
    stale_mutated = cp_store.mutate_with_fencing(
        job.id, "worker_A", fencing_token=0, status=JobStatus.SUCCEEDED, cost_usd=0.10
    )
    assert stale_mutated is False


def test_durable_outbox_transaction_and_processing(cp_store):
    out_msg = cp_store.enqueue_outbox("github.create_pr", {"repo": "owner/repo", "title": "Fix"})
    assert out_msg.status == "PENDING"

    delivered = []

    def dummy_handler(action, payload):
        delivered.append((action, payload))

    processed_count = cp_store.process_outbox(dummy_handler)
    assert processed_count == 1
    assert len(delivered) == 1
    assert delivered[0][0] == "github.create_pr"


def test_outbox_processing_respects_finite_batch_budget(cp_store):
    for index in range(3):
        cp_store.enqueue_outbox("maintenance.campaign.summary", {"index": index})

    delivered = []

    def dummy_handler(action, payload):
        delivered.append((action, payload))

    assert cp_store.process_outbox(dummy_handler, max_messages=2) == 2
    assert [payload["index"] for _, payload in delivered] == [0, 1]

    assert cp_store.process_outbox(dummy_handler, max_messages=2) == 1
    assert [payload["index"] for _, payload in delivered] == [0, 1, 2]


def test_outbox_processing_rejects_non_positive_batch_budget(cp_store):
    with pytest.raises(ValueError, match="max_messages must be >= 1"):
        cp_store.process_outbox(lambda _action, _payload: None, max_messages=0)


def test_outbox_processing_persists_dead_state_after_finite_failure_budget(cp_store):
    msg = cp_store.enqueue_outbox("maintenance.campaign.summary", {"campaign_id": "cmp_1"})
    calls = 0

    def failing_handler(_action, _payload):
        nonlocal calls
        calls += 1
        raise RuntimeError("downstream unavailable")

    assert cp_store.process_outbox(failing_handler, max_messages=1, max_attempts=2) == 0
    with sqlite3_conn(cp_store.db_path) as conn:
        row = conn.execute("SELECT status, attempts FROM outbox WHERE id = ?", (msg.id,)).fetchone()
    assert row == ("PENDING", 1)

    assert cp_store.process_outbox(failing_handler, max_messages=1, max_attempts=2) == 0
    with sqlite3_conn(cp_store.db_path) as conn:
        row = conn.execute("SELECT status, attempts FROM outbox WHERE id = ?", (msg.id,)).fetchone()
    assert row == ("DEAD", 2)
    assert calls == 2

    # DEAD messages are terminal and cannot expand later invocations.
    assert cp_store.process_outbox(failing_handler, max_messages=1, max_attempts=2) == 0
    assert calls == 2


def test_outbox_processing_preserves_legacy_failure_behavior_without_attempt_budget(cp_store):
    msg = cp_store.enqueue_outbox("maintenance.campaign.summary", {"campaign_id": "cmp_legacy"})

    def failing_handler(_action, _payload):
        raise RuntimeError("downstream unavailable")

    assert cp_store.process_outbox(failing_handler, max_messages=1) == 0
    with sqlite3_conn(cp_store.db_path) as conn:
        row = conn.execute("SELECT status, attempts FROM outbox WHERE id = ?", (msg.id,)).fetchone()
    assert row == ("PENDING", 1)


def test_outbox_processing_rejects_non_positive_attempt_budget(cp_store):
    with pytest.raises(ValueError, match="max_attempts must be >= 1"):
        cp_store.process_outbox(lambda _action, _payload: None, max_attempts=0)


def test_db_enforced_webhook_deduplication(cp_store):
    assert cp_store.record_webhook_delivery_atomic("del_unique_100", "push") is True
    # Duplicate delivery rejected at database constraint level
    assert cp_store.record_webhook_delivery_atomic("del_unique_100", "push") is False


def test_fleet_installation_and_repo_registry(cp_store):
    inst = GitHubInstallation(installation_id=12345, account_login="my-org")
    cp_store.register_installation(inst)

    repo = FleetRepository(
        id="repo_1",
        installation_id=12345,
        owner="my-org",
        name="backend",
        automation_enabled=True,
        trust_level="TRUSTED",
    )
    cp_store.register_repository(repo)

    with sqlite3_conn(cp_store.db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT owner, name, trust_level, automation_enabled FROM repositories WHERE id = 'repo_1'"
        )
        row = cur.fetchone()
        assert row == ("my-org", "backend", "TRUSTED", 1)


def sqlite3_conn(path):
    import sqlite3

    return sqlite3.connect(path)
