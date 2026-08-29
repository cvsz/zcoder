"""Public API tests for truthful jobs and resolver-backed webhook safety."""

import socket

import pytest

import zcoder.api.public.v1 as public_api
from zcoder.domain.models.tenant import EnterpriseRole, RequestContext


def admin_context():
    return RequestContext(
        principal_id="operator-1",
        organization_id="org-1",
        project_id="project-1",
        role=EnterpriseRole.ORG_ADMIN,
    )


def route(router, method, path, payload):
    return router.handle_request(method, path, admin_context(), payload=payload, request_id="req-test")


def test_job_creation_does_not_fabricate_a_successful_job():
    status, body = route(
        public_api.PublicAPIV1Router(),
        "POST",
        "/api/v1/jobs",
        {"task": "run tests"},
    )

    assert status == 501
    assert body["error"]["code"] == "JOB_QUEUE_UNAVAILABLE"
    assert "id" not in body


def install_dns_result(monkeypatch, address):
    def fake_getaddrinfo(host, port, *, type):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8080/callback",
        "http://169.254.169.254/latest/meta-data",
        "https://public.example@internal.example/callback",
    ],
)
def test_webhook_rejects_local_metadata_and_userinfo_targets(monkeypatch, url):
    install_dns_result(monkeypatch, "10.0.0.5")

    status, body = route(
        public_api.PublicAPIV1Router(),
        "POST",
        "/api/v1/webhooks",
        {"url": url},
    )

    assert status == 400
    assert body["error"]["code"] == "SSRF_BLOCKED"


def test_webhook_rejects_non_http_scheme():
    status, body = route(
        public_api.PublicAPIV1Router(),
        "POST",
        "/api/v1/webhooks",
        {"url": "file:///etc/passwd"},
    )

    assert status == 400
    assert body["error"]["code"] == "SSRF_BLOCKED"


def test_webhook_accepts_resolved_public_target(monkeypatch):
    install_dns_result(monkeypatch, "93.184.216.34")

    status, body = route(
        public_api.PublicAPIV1Router(),
        "POST",
        "/api/v1/webhooks",
        {"url": "https://hooks.example.com/zcoder"},
    )

    assert status == 201
    assert body["url"] == "https://hooks.example.com/zcoder"
