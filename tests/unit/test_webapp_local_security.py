"""Browser and Host boundaries for the unauthenticated local web console."""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient

import webapp.backend.server as server


@pytest.fixture
def client():
    return TestClient(server.app, base_url="http://localhost")


def test_default_web_hosts_are_loopback_names():
    assert server._allowed_web_hosts(None) == ["localhost", "127.0.0.1"]


@pytest.mark.parametrize("raw", ["", "*", "*.example.com", "https://example.com", "localhost:8420"])
def test_web_host_configuration_rejects_ambiguous_values(raw):
    with pytest.raises(ValueError):
        server._allowed_web_hosts(raw)


def test_web_host_configuration_accepts_explicit_unique_names():
    assert server._allowed_web_hosts("localhost, console.example.com,localhost") == [
        "localhost",
        "console.example.com",
    ]


def test_console_rejects_untrusted_host(client):
    response = client.get("/api/version", headers={"Host": "untrusted.example.com"})

    assert response.status_code == 400


def test_console_allows_loopback_host(client):
    assert client.get("/api/version").status_code == 200


def test_cross_origin_json_preflight_is_rejected(client):
    response = client.options(
        "/api/config",
        headers={
            "Origin": "https://untrusted.example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_cross_origin_reads_do_not_receive_cors_permission(client):
    response = client.get("/api/version", headers={"Origin": "https://untrusted.example.com"})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("content_type", [None, "text/plain", "application/x-www-form-urlencoded"])
def test_simple_browser_posts_cannot_update_configuration(client, monkeypatch, content_type):
    writes = []
    monkeypatch.setattr(server.Config, "set", lambda self, key, value: writes.append((key, value)))
    headers = {"Origin": "https://untrusted.example.com"}
    if content_type:
        headers["Content-Type"] = content_type

    response = client.post("/api/config", content='{"model":"untrusted-model"}', headers=headers)

    assert response.status_code == 422
    assert writes == []
