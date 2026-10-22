"""Authenticated API integration for local control operations."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from zcoder.api import local_control


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ZCODER_LOCAL_CONTROL_DATABASE", str(tmp_path / "control.sqlite"))
    monkeypatch.setenv("ZCODER_LOCAL_ORGANIZATION_ID", "org-1")
    monkeypatch.setenv("ZCODER_LOCAL_BOOTSTRAP_ADMIN_SUBJECT", "admin")
    monkeypatch.setattr(local_control, "_store_instance", None)
    actor = {"principal_id": "admin", "organization_id": "org-1"}
    monkeypatch.setattr(
        local_control,
        "authenticate_request",
        lambda _headers: SimpleNamespace(**actor),
    )
    app = FastAPI()
    app.include_router(local_control.router)
    return TestClient(app), actor


def test_local_admin_compliance_and_approved_agent_flow(client, monkeypatch):
    http, identity = client
    response = http.put("/local/v1/admin/principals/operator", json={"role": "operator"})
    assert response.status_code == 200

    response = http.get("/local/v1/admin/principals")
    assert response.status_code == 200
    assert {item["principal"] for item in response.json()["principals"]} == {"admin", "operator"}

    identity["principal_id"] = "operator"
    response = http.post(
        "/local/v1/tasks",
        json={"task_id": "task-1", "description": "Review a patch"},
    )
    assert response.status_code == 201

    class FakeCoder:
        def __init__(self, **kwargs):
            assert kwargs["provider"] == "llama_cpp"

        def generate(self, prompt):
            assert prompt == "Review a patch"
            return "review complete"

    monkeypatch.setattr("zcoder.services.coder.Coder", FakeCoder)
    identity["principal_id"] = "admin"
    response = http.post("/local/v1/tasks/task-1/decision", json={"approve": True})
    assert response.status_code == 200

    identity["principal_id"] = "operator"
    response = http.post("/local/v1/tasks/task-1/run")
    assert response.status_code == 200
    assert response.json()["result"] == "review complete"

    identity["principal_id"] = "admin"
    response = http.get("/local/v1/compliance/audit")
    assert response.status_code == 200
    assert response.json()["verified"] is True
    assert any(row["action"] == "task.completed" for row in response.json()["records"])


def test_local_control_rejects_other_organization(client):
    http, identity = client
    identity["organization_id"] = "org-2"
    response = http.get("/local/v1/admin/principals")
    assert response.status_code == 403
