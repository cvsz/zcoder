"""Unit tests for zcoder.api.server observability and health/readiness routes."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="fastapi is an optional API dependency")

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from fastapi.testclient import TestClient  # noqa: E402

import zcoder.api.server as server  # noqa: E402


@pytest.fixture()
def client():
    return TestClient(server.app)


class _FakeStore:
    def __init__(self, healthy: bool = True):
        self.healthy = healthy

    def health_check(self) -> bool:
        if not self.healthy:
            raise RuntimeError("connection refused")
        return True


def test_metrics_route_returns_prometheus_text(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert "version=0.0.4" in resp.headers["content-type"]
    body = resp.text
    assert body.endswith("\n")
    assert "# TYPE zcoder_jobs_queued gauge" in body
    assert "zcoder_api_requests_total" in body


def test_liveness_always_200(client):
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "alive"}


def test_readiness_200_when_probe_ok(client, monkeypatch):
    monkeypatch.setattr(server, "_get_db_store", lambda: _FakeStore(healthy=True))
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready"}


def test_readiness_503_when_probe_raises(client, monkeypatch):
    monkeypatch.setattr(server, "_get_db_store", lambda: _FakeStore(healthy=False))
    resp = client.get("/health/ready")
    assert resp.status_code == 503
    assert resp.json() == {"status": "unavailable"}


def test_readiness_503_fail_closed_on_import_or_construction_error(client, monkeypatch):
    def _boom():
        raise ImportError("psycopg2 missing")

    monkeypatch.setattr(server, "_get_db_store", _boom)
    resp = client.get("/health/ready")
    assert resp.status_code == 503
    assert resp.json() == {"status": "unavailable"}
