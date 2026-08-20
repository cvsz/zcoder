"""Regression guards for SEC-005 CodeAgent WebFetch SSRF containment."""

from __future__ import annotations

import socket
import urllib.request
from pathlib import Path

from zcoder.claude.capabilities.code import CodeAgent, CodeSession


def _agent() -> CodeAgent:
    return CodeAgent(api_key="test-key", model="test-model")


def _session(workspace: Path) -> CodeSession:
    return CodeSession(cwd=str(workspace), model="test-model")


def _unexpected_network(*_args, **_kwargs):
    raise AssertionError("network sink reached before SSRF validation")


def test_webfetch_blocks_loopback_before_network(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(urllib.request, "urlopen", _unexpected_network)

    result = _agent()._run_tool(
        "WebFetch",
        {"url": "http://127.0.0.1:8080/internal"},
        _session(tmp_path),
    )

    assert "non-public" in result
    assert "network sink reached" not in result


def test_webfetch_blocks_private_dns_before_network(monkeypatch, tmp_path: Path) -> None:
    def fake_getaddrinfo(host, port, *, type):
        assert host == "internal.example"
        assert type == socket.SOCK_STREAM
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.23.4.5", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(urllib.request, "urlopen", _unexpected_network)

    result = _agent()._run_tool(
        "WebFetch",
        {"url": "https://internal.example/data"},
        _session(tmp_path),
    )

    assert "non-public" in result
    assert "network sink reached" not in result


def test_noninteractive_webfetch_still_uses_network_boundary(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(urllib.request, "urlopen", _unexpected_network)

    class AllowingHooks:
        def pre_tool_use(self, *_args, **_kwargs):
            return {"allowed": True, "message": ""}

        def post_tool_use(self, *_args, **_kwargs):
            return None

    result = _agent()._execute_tool(
        "WebFetch",
        {"url": "http://127.0.0.1:8080/internal"},
        _session(tmp_path),
        AllowingHooks(),
        permission="askPermission",
        can_use_tool=None,
    )

    assert "non-public" in result
    assert "network sink reached" not in result
