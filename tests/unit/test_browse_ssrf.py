"""Regression guards for SEC-006 browsing-agent network containment.

The browsing agent previously fetched model/page-derived navigation URLs
through `safe_urlopen` (scheme-only check), leaving the same SSRF surface
SEC-005 closed for CodeAgent WebFetch. These tests lock the strict
external-URL boundary on the browse fetch path.
"""

from __future__ import annotations

import pytest

from zcoder.claude.integrations.chrome import _fetch_retrying


def test_browse_fetch_blocks_loopback_literal():
    with pytest.raises(ValueError, match="non-public"):
        _fetch_retrying("http://127.0.0.1:8080/internal", timeout=5)


def test_browse_fetch_blocks_cloud_metadata():
    with pytest.raises(ValueError, match="non-public"):
        _fetch_retrying("http://169.254.169.254/latest/meta-data/", timeout=5)


def test_browse_fetch_blocks_ipv6_loopback():
    with pytest.raises(ValueError, match="non-public"):
        _fetch_retrying("http://[::1]/internal", timeout=5)


def test_browse_fetch_blocks_userinfo_confusion():
    with pytest.raises(ValueError, match="userinfo"):
        _fetch_retrying("https://public.example@127.0.0.1/internal", timeout=5)


def test_browse_fetch_blocks_private_dns(monkeypatch):
    import socket

    def fake_getaddrinfo(host, port, *, type):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.9", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(ValueError, match="non-public"):
        _fetch_retrying("https://private.example/data", timeout=5)
