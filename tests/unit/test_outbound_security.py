"""Regression coverage for caller-supplied external URL SSRF guards."""

import socket

import pytest

from zcoder.core.outbound_security import validate_external_http_url


def test_external_url_rejects_loopback_ip_literal():
    with pytest.raises(ValueError, match="non-public"):
        validate_external_http_url("http://127.0.0.1:8080/internal")


def test_external_url_rejects_ipv6_loopback_literal():
    with pytest.raises(ValueError, match="non-public"):
        validate_external_http_url("http://[::1]/internal")


def test_external_url_rejects_private_dns_resolution(monkeypatch):
    def fake_getaddrinfo(host, port, *, type):
        assert host == "internal.example"
        assert type == socket.SOCK_STREAM
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.23.4.5", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    with pytest.raises(ValueError, match="non-public"):
        validate_external_http_url("https://internal.example/data")


def test_external_url_rejects_mixed_public_and_private_dns(monkeypatch):
    def fake_getaddrinfo(host, port, *, type):
        assert type == socket.SOCK_STREAM
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.9", port)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    with pytest.raises(ValueError, match="non-public"):
        validate_external_http_url("https://mixed.example/data")


def test_external_url_accepts_exclusively_public_dns(monkeypatch):
    def fake_getaddrinfo(host, port, *, type):
        assert host == "public.example"
        assert type == socket.SOCK_STREAM
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    assert validate_external_http_url("https://public.example/data") is None


def test_external_url_rejects_userinfo_hostname_confusion():
    with pytest.raises(ValueError, match="userinfo"):
        validate_external_http_url("https://public.example@127.0.0.1/internal")
