"""tests/test_deployment_engine.py — Tests for Deployment Health, Backup/Restore Drills & Worker Recovery"""

import hashlib
import tempfile
from pathlib import Path

import pytest

from zcoder.domain.services.control_plane import ControlPlaneStore, GitHubInstallation
from zcoder.domain.services.deployment import (
    ArtifactManifest,
    DeploymentEngine,
    DeploymentRecord,
)


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


def test_deployment_history_and_rollback(deploy_setup):
    store, engine = deploy_setup

    # Record two deployments
    engine.record_deployment(
        DeploymentRecord(
            deployment_id="dep_1",
            version="v1.0.0",
            image_digest="sha256:abc123",
            deployed_at=1000.0,
            actor="ci",
            environment="production",
            result="SUCCESS",
        )
    )
    engine.record_deployment(
        DeploymentRecord(
            deployment_id="dep_2",
            version="v1.1.0",
            image_digest="sha256:def456",
            deployed_at=2000.0,
            actor="ci",
            environment="production",
            result="FAILED",
        )
    )

    history = engine.get_deployment_history(limit=5)
    assert len(history) == 2
    assert history[0].version == "v1.1.0"

    success, msg = engine.rollback_to_version("v1.0.0", actor="ops")
    assert success is True
    assert "v1.0.0" in msg

    updated = engine.get_deployment_history(limit=5)
    assert any(d.result == "ROLLBACK" for d in updated)


def test_artifact_revocation_and_verification(deploy_setup):
    store, engine = deploy_setup

    # Create a temp file and compute its hash
    with tempfile.NamedTemporaryFile(delete=False, suffix=".whl") as tmp:
        tmp.write(b"fake-wheel-content")
        tmp_path = Path(tmp.name)

    sha256 = hashlib.sha256()
    with open(tmp_path, "rb") as f:
        sha256.update(f.read())
    digest = sha256.hexdigest()

    manifest = ArtifactManifest(
        artifact_id="art_1",
        artifact_type="wheel",
        version="v1.0.0",
        sha256=digest,
        size_bytes=len(b"fake-wheel-content"),
        provenance="sbom+attestation",
    )

    engine.revoke_artifact(manifest, "Supply chain compromise")
    loaded = engine.get_artifact_manifest("art_1")
    assert loaded is not None
    assert loaded.revoked is True
    assert loaded.revocation_reason == "Supply chain compromise"
    assert engine.verify_artifact_integrity(loaded, str(tmp_path)) is True

    tmp_path.unlink()


def test_deployment_rehearsal(deploy_setup):
    store, engine = deploy_setup

    result = engine.run_deployment_rehearsal("v1.0.0", dry_run=True)
    assert result["target_version"] == "v1.0.0"
    assert result["dry_run"] is True
    assert result["passed"] is True
    assert any(c["name"] == "health" for c in result["checks"])
    assert any(c["name"] == "backup_creation" for c in result["checks"])
    assert "duration_seconds" in result
