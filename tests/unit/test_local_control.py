"""Offline control plane regressions; no network or Anthropic dependencies."""

import sqlite3
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from zcoder.api import local_control as local_api
from zcoder.api.auth import RequestAuthenticationError

from zcoder.services.local_control import (
    LocalAgentRunner,
    LocalControlStore,
    LocalLlamaCppClient,
)


def test_bootstrap_roles_and_independent_approval(tmp_path):
    store = LocalControlStore(tmp_path / "control.sqlite")
    store.bootstrap_admin("admin")
    with pytest.raises(PermissionError):
        store.bootstrap_admin("intruder")
    store.grant_role("admin", "worker", "operator")
    store.grant_role("admin", "inspector", "auditor")
    store.create_task("worker", "job-1", "Review local compiler")
    with pytest.raises(PermissionError):
        store.decide_task("worker", "job-1", True)
    store.decide_task("admin", "job-1", True)
    with pytest.raises(ValueError):
        store.decide_task("admin", "job-1", True)
    with pytest.raises(PermissionError):
        store.audit_records("worker")
    assert store.verify_audit_chain("inspector")


def test_owner_cannot_self_approve(tmp_path):
    store = LocalControlStore(tmp_path / "control.sqlite")
    store.bootstrap_admin("admin")
    store.create_task("admin", "job-2", "Sensitive operation")
    with pytest.raises(PermissionError):
        store.decide_task("admin", "job-2", True)


def test_audit_tampering_detected(tmp_path):
    path = tmp_path / "control.sqlite"
    store = LocalControlStore(path)
    store.bootstrap_admin("admin")
    store.grant_role("admin", "auditor", "auditor")
    assert store.verify_audit_chain("auditor")
    with sqlite3.connect(path) as db:
        db.execute("UPDATE audit SET subject='tampered' WHERE seq=1")
    assert not store.verify_audit_chain("auditor")


def test_fail_closed_roles(tmp_path):
    store = LocalControlStore(tmp_path / "control.sqlite")
    store.bootstrap_admin("admin")
    with pytest.raises(ValueError):
        store.grant_role("admin", "other", "root")
    with pytest.raises(PermissionError):
        store.create_task("unknown", "job", "Task")


def test_agent_runner_consumes_only_approved_task_once(tmp_path, monkeypatch):
    store = LocalControlStore(tmp_path / "control.sqlite")
    store.bootstrap_admin("admin")
    store.grant_role("admin", "worker", "operator")
    store.create_task("worker", "job-3", "Review the local patch")

    class FakeClient:
        def __init__(self, _base_url=None, *, model=None):
            assert model is None

        def generate(self, prompt):
            assert prompt == "Review the local patch"
            return "review complete"

    monkeypatch.setattr("zcoder.services.local_control.LocalLlamaCppClient", FakeClient)
    runner = LocalAgentRunner(store)
    with pytest.raises(ValueError, match="unapproved"):
        runner.run("worker", "job-3")

    store.decide_task("admin", "job-3", True)
    assert runner.run("worker", "job-3") == "review complete"
    with pytest.raises(ValueError, match="already consumed"):
        runner.run("worker", "job-3")

    with store._connect() as db:
        state, result = db.execute(
            "SELECT execution_state,result FROM tasks WHERE task_id='job-3'"
        ).fetchone()
    assert state == "COMPLETED"
    assert result == "review complete"


def test_local_model_client_uses_only_loopback(monkeypatch):
    requested = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size):
            return b'{"choices":[{"message":{"content":"local result"}}]}'

    def fake_open(request, timeout):
        requested.append((request.full_url, timeout))
        return Response()

    monkeypatch.setattr("zcoder.services.local_control._safe_local_urlopen", fake_open)
    client = LocalLlamaCppClient()
    assert client.generate("prompt") == "local result"
    assert requested == [("http://127.0.0.1:8080/v1/chat/completions", 120)]


def test_local_model_client_rejects_non_loopback_endpoint():
    with pytest.raises(ValueError, match="loopback"):
        LocalLlamaCppClient("https://api.anthropic.com")


@pytest.mark.skipif(
    __import__("os").name != "posix", reason="POSIX file mode contract"
)
def test_database_permissions_are_owner_only(tmp_path):
    import stat

    path = tmp_path / "private-control.sqlite"
    store = LocalControlStore(path)
    store.bootstrap_admin("admin")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    # Existing database files are tightened on subsequent connections too.
    path.chmod(0o644)
    store.list_principals("admin")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


# API adapter regressions: authentication failures and tenant/RBAC boundaries.

def _local_api_client(
    monkeypatch, tmp_path, *, principal="admin", organization="org-1"
):
    monkeypatch.setenv("ZCODER_LOCAL_ORGANIZATION_ID", "org-1")
    monkeypatch.setenv("ZCODER_LOCAL_BOOTSTRAP_ADMIN_SUBJECT", "admin")
    monkeypatch.setenv(
        "ZCODER_LOCAL_CONTROL_DATABASE", str(tmp_path / "api-control.sqlite")
    )
    monkeypatch.setattr(local_api, "_store_instance", None)
    monkeypatch.setattr(
        local_api,
        "authenticate_request",
        lambda _headers: SimpleNamespace(
            principal_id=principal, organization_id=organization
        ),
    )
    app = FastAPI()
    app.include_router(local_api.router)
    return TestClient(app)


def test_local_api_rejects_authentication_failure(monkeypatch, tmp_path):
    client = _local_api_client(monkeypatch, tmp_path)

    def reject(_headers):
        raise RequestAuthenticationError("A non-empty Bearer token is required")

    monkeypatch.setattr(local_api, "authenticate_request", reject)
    response = client.get("/local/v1/admin/principals")
    assert response.status_code == 401


def test_local_api_rejects_wrong_organization(monkeypatch, tmp_path):
    client = _local_api_client(monkeypatch, tmp_path, organization="org-2")
    response = client.get("/local/v1/admin/principals")
    assert response.status_code == 403


def test_local_api_enforces_local_admin_role(monkeypatch, tmp_path):
    client = _local_api_client(monkeypatch, tmp_path, principal="operator")
    response = client.get("/local/v1/admin/principals")
    assert response.status_code == 403
    assert response.json()["detail"] == "permission denied"


def test_local_api_allows_bootstrapped_admin_in_bound_organization(
    monkeypatch, tmp_path
):
    client = _local_api_client(monkeypatch, tmp_path)
    response = client.get("/local/v1/admin/principals")
    assert response.status_code == 200
    assert response.json() == {
        "principals": [{"principal": "admin", "role": "admin"}]
    }
