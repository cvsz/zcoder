"""Regression tests for local desktop inference and code-signing defaults."""

from __future__ import annotations

import socket
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from zcoder.interfaces.desktop.security import open_local_request, validate_local_base_url


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8080/v1",
        "https://[::1]:8443/v1",
    ],
)
def test_validate_local_base_url_accepts_loopback_ip_literals(url: str) -> None:
    assert validate_local_base_url(url) == url


def test_validate_local_base_url_accepts_localhost_when_all_addresses_are_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_getaddrinfo(host: str, port: int, *, type: int):
        assert host == "localhost"
        assert type == socket.SOCK_STREAM
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port)),
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", port, 0, 0)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    assert validate_local_base_url("http://localhost:8080/v1") == "http://localhost:8080/v1"


def test_validate_local_base_url_rejects_localhost_with_non_loopback_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_getaddrinfo(host: str, port: int, *, type: int):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.20", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(ValueError, match="exclusively to loopback"):
        validate_local_base_url("http://localhost:8080/v1")


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/v1",
        "http://192.168.1.20:8080/v1",
        "file:///etc/passwd",
        "http://user:secret@127.0.0.1:8080/v1",
        "http://127.0.0.1:8080/v1?token=secret",
        "http://127.0.0.1:8080/v1#fragment",
        "http://127.0.0.1:99999/v1",
    ],
)
def test_validate_local_base_url_rejects_non_loopback_or_unsafe_urls(url: str) -> None:
    with pytest.raises(ValueError):
        validate_local_base_url(url)


def test_local_request_does_not_follow_redirects() -> None:
    class RedirectHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.send_response(302)
            self.send_header("Location", "http://example.com/should-not-be-followed")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), RedirectHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = Request(
            f"http://127.0.0.1:{server.server_port}/v1/chat/completions",
            data=b"{}",
            method="POST",
        )
        with pytest.raises(HTTPError) as error:
            open_local_request(request, timeout=2)
        assert error.value.code == 302
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_signing_password_has_no_repository_default() -> None:
    root = Path(__file__).resolve().parents[2]
    makefile = (root / "Makefile").read_text(encoding="utf-8")
    make_cert = (root / "scripts" / "make_cert.ps1").read_text(encoding="utf-8")

    assert "ZCoderDesktop2026!" not in makefile + make_cert
    assert "PFX_PASSWORD ?=" not in makefile
    assert "-Password $(PFX_PASSWORD)" not in makefile
    assert "ZCODER_PFX_PASSWORD" in make_cert
    assert "No default password is used" in make_cert
