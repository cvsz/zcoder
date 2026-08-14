"""tests/test_deployment_engine.py — Tests for Deployment Health, Backup/Restore Drills & Worker Recovery"""

import tempfile
from pathlib import Path

import pytest

from control_plane import ControlPlaneStore, GitHubInstallation
from deployment_engine import DeploymentEngine


@pytest.fixture
def deploy_setup():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)
    store = ControlPlaneStore(db_path=db_path)
    engine = DeploymentEngine(store=store)
    yield store, engine
    if db_path.exists():
        db_path.unlink()


def test_service_liveness_and_readiness_health(deploy_setup):
    store, engine = deploy_setup
    health = engine.evaluate_health()
    assert health.status == "HEALTHY"
    assert health.liveness is True
    assert health.readiness is True
    assert health.db_connected is True


def test_logical_backup_and_restoration_drill(deploy_setup):
    store, engine = deploy_setup

    # Insert baseline data
    inst = GitHubInstallation(installation_id=99001, account_login="drill-org")
    store.register_installation(inst)
    store.enqueue_outbox("test.action", {"payload": 123})

    # Produce backup
    backup = engine.create_logical_backup()
    assert backup.record_counts["installations"] >= 1
    assert backup.record_counts["outbox"] >= 1

    # Restore into fresh DB
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_target:
        target_path = Path(tmp_target.name)
    target_store = ControlPlaneStore(db_path=target_path)

    restored = engine.restore_backup(backup, target_store)
    assert restored is True

    # Verify target has restored records
    with tempfile.NamedTemporaryFile(suffix=".db") as _:
        import sqlite3

        with sqlite3.connect(target_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT account_login FROM installations WHERE installation_id = 99001")
            row = cur.fetchone()
            assert row is not None
            assert row[0] == "drill-org"

    if target_path.exists():
        target_path.unlink()


def test_worker_crash_lease_expiry_drill(deploy_setup):
    store, engine = deploy_setup

    # Seed running job claimed by Worker A
    import sqlite3

    with sqlite3.connect(store.db_path) as conn:
        conn.execute("""
            INSERT INTO jobs (id, task, runtime, status, workspace, created_at, updated_at, model, budget_usd, cost_usd, claimed_by, claim_generation, lease_expires_at, metadata)
            VALUES ('job_crash_1', 'Crash recovery task', 'direct', 'RUNNING', '.', 100.0, 100.0, 'claude-sonnet-5', 5.0, 0.0, 'worker_A', 1, 9999999999.0, '{}')
        """)

    reclaimed, details = engine.simulate_worker_crash_and_reclaim("worker_A", "job_crash_1")
    assert reclaimed is True
    assert "fencing token 2" in details
