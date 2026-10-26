"""tests/test_webapp_server.py — webapp/backend/server.py

Uses FastAPI's TestClient (httpx-based, no real network/socket). The
Coder.generate() / local llama-server HTTP calls are monkeypatched so no
real API or model calls happen anywhere in this file.
"""

import json
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


def test_models_endpoint_lists_only_configured_local_model(client, monkeypatch):
    monkeypatch.setenv("ZCODER_MODEL", "qwen-local.gguf")

    response = client.get("/api/models")

    assert response.status_code == 200
    assert response.json() == [{"id": "qwen-local.gguf", "display_name": "qwen-local.gguf", "tier": "local"}]


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
    received = {}

    def fake_generate(self, *args, **kwargs):
        received.update(api_key=self.api_key if hasattr(self, "api_key") else None)
        return "mock reply"

    monkeypatch.setattr(server.Coder, "generate", fake_generate)
    resp = client.post("/api/chat", json={"prompt": "hello", "api_key": "sk-ant-test"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["response"] == "mock reply"
    assert "session_id" in data
    assert received["api_key"] is None


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


@pytest.mark.parametrize("with_api_key", [False, True])
def test_chat_stream_uses_loopback_local_model_without_credentials(client, monkeypatch, with_api_key):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-be-used")

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def __iter__(self):
            events = [
                {"choices": [{"delta": {"content": "Hel"}}]},
                {"choices": [{"delta": {"content": "lo!"}}]},
            ]
            return iter([f"data: {json.dumps(event)}\n".encode() for event in events] + [b"data: [DONE]\n"])

    calls = []

    def fake_open(self, request, timeout=0):
        calls.append((request.full_url, request.method, json.loads(request.data)))
        assert request.get_header("Authorization") is None
        return FakeResponse()

    monkeypatch.setattr(server.urllib.request.OpenerDirector, "open", fake_open)

    payload = {
        "prompt": "hi",
        "model": "local-qwen",
        "session_id": "local-session",
        "system": "Be concise",
    }
    if with_api_key:
        payload["api_key"] = "ignored-compatibility-key"
    response = client.post("/api/chat/stream", json=payload)

    assert response.status_code == 200
    body = response.text
    assert '"text": "Hel"' in body
    assert '"text": "lo!"' in body
    assert '"type": "done"' in body
    assert client.get("/api/sessions/local-session").json()["history"][-1]["content"] == "Hello!"
    assert len(calls) == 1
    url, method, request_payload = calls[0]
    assert url == "http://127.0.0.1:8080/v1/chat/completions"
    assert method == "POST"
    assert request_payload["stream"] is True
    assert request_payload["model"] == "local-qwen"
    assert request_payload["messages"] == [
        {"role": "system", "content": "Be concise"},
        {"role": "user", "content": "hi"},
    ]


@pytest.mark.parametrize("base_url", ["https://model.example/v1", "http://user:pass@127.0.0.1:8080"])
def test_chat_stream_rejects_non_loopback_model_url(client, monkeypatch, base_url):
    monkeypatch.setenv("ZCODER_BASE_URL", base_url)
    response = client.post("/api/chat/stream", json={"prompt": "hi"})

    assert response.status_code == 200
    assert '"type": "error"' in response.text
    assert "loopback" in response.text
