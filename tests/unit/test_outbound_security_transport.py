"""Transport-level regression guards for external outbound URL security."""

from __future__ import annotations

import socket
import urllib.request

import zcoder.core.outbound_security as outbound_security


def test_external_urlopen_disables_environment_proxies(monkeypatch) -> None:
    captured_handlers: list[object] = []

    class FakeOpener:
        def open(self, req, timeout):
            assert req.full_url == "https://public.example/data"
            assert timeout == 3
            return object()

    def fake_build_opener(*handlers):
        captured_handlers.extend(handlers)
        return FakeOpener()

    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:8888")
    monkeypatch.setattr(outbound_security, "validate_external_http_url", lambda _url: None)
    monkeypatch.setattr(urllib.request, "build_opener", fake_build_opener)

    req = urllib.request.Request("https://public.example/data")
    outbound_security.safe_external_urlopen(req, timeout=3)

    proxy_handlers = [h for h in captured_handlers if isinstance(h, urllib.request.ProxyHandler)]
    assert len(proxy_handlers) == 1
    assert proxy_handlers[0].proxies == {}


def test_external_redirect_revalidates_destination() -> None:
    handler = outbound_security._ExternalRedirectHandler()
    req = urllib.request.Request("https://public.example/start")

    try:
        handler.redirect_request(
            req,
            fp=None,
            code=302,
            msg="Found",
            headers={},
            newurl="http://127.0.0.1/internal",
        )
    except ValueError as exc:
        assert "non-public" in str(exc)
    else:
        raise AssertionError("private redirect target was not rejected")


def test_external_url_rejects_ipv4_mapped_ipv6_loopback() -> None:
    try:
        outbound_security.validate_external_http_url("http://[::ffff:127.0.0.1]/internal")
    except ValueError as exc:
        assert "non-public" in str(exc)
    else:
        raise AssertionError("IPv4-mapped IPv6 loopback was not rejected")


def test_pinned_http_connection_uses_validated_ip_without_dns_reresolution(monkeypatch) -> None:
    calls: list[tuple[str, int]] = []
    sentinel_socket = object()

    def fake_create_connection(address, timeout=None, source_address=None):
        calls.append(address)
        return sentinel_socket

    def unexpected_getaddrinfo(*_args, **_kwargs):
        raise AssertionError("connection attempted a second DNS lookup")

    monkeypatch.setattr(socket, "create_connection", fake_create_connection)
    monkeypatch.setattr(socket, "getaddrinfo", unexpected_getaddrinfo)

    conn = outbound_security._PinnedHTTPConnection(
        "public.example",
        pinned_address="93.184.216.34",
        port=80,
        timeout=3,
    )
    conn.connect()

    assert calls == [("93.184.216.34", 80)]
    assert conn.sock is sentinel_socket


def test_pinned_https_connection_uses_validated_ip_and_original_sni(monkeypatch) -> None:
    calls: list[tuple[str, int]] = []
    raw_socket = object()
    tls_socket = object()

    class FakeContext:
        def wrap_socket(self, sock, *, server_hostname):
            assert sock is raw_socket
            assert server_hostname == "public.example"
            return tls_socket

    def fake_create_connection(address, timeout=None, source_address=None):
        calls.append(address)
        return raw_socket

    def unexpected_getaddrinfo(*_args, **_kwargs):
        raise AssertionError("connection attempted a second DNS lookup")

    monkeypatch.setattr(socket, "create_connection", fake_create_connection)
    monkeypatch.setattr(socket, "getaddrinfo", unexpected_getaddrinfo)

    conn = outbound_security._PinnedHTTPSConnection(
        "public.example",
        pinned_address="93.184.216.34",
        port=443,
        timeout=3,
        context=FakeContext(),
    )
    conn.connect()

    assert calls == [("93.184.216.34", 443)]
    assert conn.sock is tls_socket
