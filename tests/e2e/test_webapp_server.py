"""tests/test_webapp_server.py — webapp/backend/server.py

Uses FastAPI's TestClient (httpx-based, no real network/socket). The
Coder.generate() / anthropic streaming calls are monkeypatched so no real
API calls happen anywhere in this file, same convention as
tests/test_coder.py.
"""

import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="optional dependency for webapp, see webapp/requirements-web.txt")
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import webapp.backend.server as server  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_state():
    """Each test gets an empty session store and a fresh rate-limit
    bucket, so tests can't leak state into each other via the
    process-local dicts server.py uses."""
    server._sessions.clear()
    server._rate_buckets.clear()
    yield
    server._sessions.clear()
    server._rate_buckets.clear()


@pytest.fixture
def client():
    return TestClient(server.app, base_url="http://localhost")


def test_version_endpoint(client):
    resp = client.get("/api/version")
    assert resp.status_code == 200
    assert "version" in resp.json()


def test_chat_rejects_empty_prompt(client):
    resp = client.post("/api/chat", json={"prompt": "   "})
    assert resp.status_code == 400


def test_chat_rejects_out_of_range_temperature(client):
    resp = client.post("/api/chat", json={"prompt": "hi", "temperature": 5.0})
    assert resp.status_code == 422  # pydantic validation error


def test_chat_rejects_out_of_range_max_tokens(client):
    resp = client.post("/api/chat", json={"prompt": "hi", "max_tokens": 0})
    assert resp.status_code == 422


def test_chat_happy_path(client, monkeypatch):
    monkeypatch.setattr(server.Coder, "generate", lambda self, *a, **k: "mock reply")
    resp = client.post("/api/chat", json={"prompt": "hello", "api_key": "sk-ant-test"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["response"] == "mock reply"
    assert "session_id" in data


def test_chat_rate_limit_returns_429(client, monkeypatch):
    monkeypatch.setattr(server.Coder, "generate", lambda self, *a, **k: "ok")
    monkeypatch.setattr(server, "_RATE_LIMIT", 2)
    for _ in range(2):
        resp = client.post("/api/chat", json={"prompt": "hi", "api_key": "sk-ant-test"})
        assert resp.status_code == 200
    resp = client.post("/api/chat", json={"prompt": "hi", "api_key": "sk-ant-test"})
    assert resp.status_code == 429


def test_sessions_list_empty_by_default(client):
    resp = client.get("/api/sessions")
    assert resp.status_code == 200
    assert resp.json() == []


def test_sessions_list_reflects_chat_history(client, monkeypatch):
    monkeypatch.setattr(server.Coder, "generate", lambda self, *a, **k: "reply text")
    chat_resp = client.post("/api/chat", json={"prompt": "what is python", "api_key": "sk-ant-test"})
    sid = chat_resp.json()["session_id"]

    listing = client.get("/api/sessions").json()
    assert len(listing) == 1
    assert listing[0]["session_id"] == sid
    assert listing[0]["turns"] == 1
    assert "what is python" in listing[0]["preview"]


def test_sessions_get_and_delete(client, monkeypatch):
    monkeypatch.setattr(server.Coder, "generate", lambda self, *a, **k: "reply")
    sid = client.post("/api/chat", json={"prompt": "hi", "api_key": "sk-ant-test"}).json()["session_id"]

    got = client.get(f"/api/sessions/{sid}")
    assert got.status_code == 200
    assert len(got.json()["history"]) == 2

    deleted = client.delete(f"/api/sessions/{sid}")
    assert deleted.status_code == 200
    assert client.get(f"/api/sessions/{sid}").status_code == 404


def test_chat_stream_uses_local_coder_without_api_key(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(server.Coder, "generate", lambda self, *args, **kwargs: "local reply")
    resp = client.post("/api/chat/stream", json={"prompt": "hi"})
    assert resp.status_code == 200
    assert '"type": "token", "text": "local reply"' in resp.text
    assert '"type": "done"' in resp.text


def test_chat_stream_uses_supplied_prompt_and_system(client, monkeypatch):
    calls = []

    def generate(self, prompt, system=None, history=None):
        calls.append((prompt, system, history, self.personality_style))
        return "local answer"

    monkeypatch.setattr(server.Coder, "generate", generate)
    resp = client.post("/api/chat/stream", json={"prompt": "hello", "personality": "teaching"})
    assert resp.status_code == 200
    assert '"type": "token", "text": "local answer"' in resp.text
    assert calls and calls[0][0] == "hello"
    assert calls[0][3] == "teaching"
