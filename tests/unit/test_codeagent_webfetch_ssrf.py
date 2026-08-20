"""Regression guards for SEC-005 CodeAgent WebFetch SSRF containment.

The CodeAgent WebFetch sink must route model-controlled URLs through the
centralized external-URL boundary (rejecting loopback/private/link-local/
metadata destinations, userinfo confusion, and redirect hops into private
space) instead of the scheme-only ``safe_urlopen`` path.
"""

from __future__ import annotations

import http.server
import socket
import threading
import urllib.error
import urllib.request

import pytest

import zcoder.core.outbound_security as outbound_security
from zcoder.claude.capabilities.code import CodeAgent, CodeSession


def _agent() -> CodeAgent:
    return CodeAgent(api_key="test-key", model="test-model")


def _session() -> CodeSession:
    return CodeSession(cwd="/tmp", model="test-model")


def _assert_blocked(result: str) -> None:
    assert result.startswith("[WebFetch error]")
    assert "non-public" in result


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8080/internal",
        "http://127.1.2.3/private",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/internal",
        "http://192.168.1.9/private",
        "http://[::1]/internal",
        "http://[::ffff:127.0.0.1]/internal",
        "http://0.0.0.0/internal",
    ],
)
def test_webfetch_blocks_non_public_ip_literals(url: str) -> None:
    result = _agent()._run_tool("WebFetch", {"url": url}, _session())
    _assert_blocked(result)


def test_webfetch_blocks_userinfo_hostname_confusion() -> None:
    result = _agent()._run_tool(
        "WebFetch",
        {"url": "https://public.example@127.0.0.1/internal"},
        _session(),
    )
    assert result.startswith("[WebFetch error]")
    assert "userinfo" in result


def test_webfetch_blocks_private_dns_resolution(monkeypatch) -> None:
    def fake_getaddrinfo(host, port, *, type):
        assert host == "internal.example"
        assert type == socket.SOCK_STREAM
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.23.4.5", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    result = _agent()._run_tool(
        "WebFetch",
        {"url": "https://internal.example/data"},
        _session(),
    )
    _assert_blocked(result)


def test_webfetch_blocks_mixed_public_and_private_dns(monkeypatch) -> None:
    def fake_getaddrinfo(host, port, *, type):
        assert type == socket.SOCK_STREAM
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.9", port)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    result = _agent()._run_tool(
        "WebFetch",
        {"url": "https://mixed.example/data"},
        _session(),
    )
    _assert_blocked(result)


class _RedirectHandler(http.server.BaseHTTPRequestHandler):
    redirect_to: str = ""

    def do_GET(self):  # noqa: N802
        self.send_response(302)
        self.send_header("Location", self.redirect_to)
        self.end_headers()

    def log_message(self, *args):  # noqa: D102
        pass


def test_redirect_targets_are_revalidated(monkeypatch) -> None:
    calls: list[str] = []

    def fake_validate(url: str) -> None:
        calls.append(url)
        if "/private" in url:
            raise ValueError("Outbound URL host '127.0.0.1' resolves to a non-public address")

    monkeypatch.setattr(outbound_security, "validate_external_http_url", fake_validate)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _RedirectHandler)
    port = server.server_address[1]
    _RedirectHandler.redirect_to = f"http://127.0.0.1:{port}/private"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/start")
        with pytest.raises(ValueError, match="non-public"):
            outbound_security.safe_external_urlopen(req, timeout=5)
    finally:
        server.shutdown()
        thread.join(timeout=5)

    assert any(url.endswith("/start") for url in calls)
    assert any(url.endswith("/private") for url in calls)


def test_webfetch_still_fetches_public_urls(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, amount: int = -1) -> bytes:
            assert amount == 4096
            return b"public-page-content"

    def fake_getaddrinfo(host, port, *, type):
        assert host == "public.example"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(
        "zcoder.claude.capabilities.code.safe_external_urlopen",
        lambda req, timeout: FakeResponse(),
    )

    result = _agent()._run_tool(
        "WebFetch",
        {"url": "https://public.example/page"},
        _session(),
    )

    assert result == "public-page-content"
