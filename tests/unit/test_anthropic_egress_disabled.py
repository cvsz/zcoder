"""Anthropic compatibility paths must fail before opening network sockets."""

import urllib.request
from unittest.mock import patch
from urllib.request import Request

import httpx2
import pytest

from zcoder.core.anthropic_disabled import create_anthropic_client
from zcoder.core.exceptions import AnthropicCallsDisabledError
from zcoder.core.outbound_security import safe_external_urlopen
from zcoder.core.resilience import safe_urlopen


def test_safe_urlopen_rejects_anthropic_host_before_network(monkeypatch):
    called = False

    def forbidden(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("network access must not occur")

    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    request = Request("https://api.anthropic.com/v1/messages")

    with pytest.raises(AnthropicCallsDisabledError):
        safe_urlopen(request, timeout=1)
    assert called is False


def test_safe_urlopen_rejects_anthropic_redirect_before_opening_target(monkeypatch):
    handler = __import__(
        "zcoder.core.resilience", fromlist=["_AnthropicRedirectHandler"]
    )._AnthropicRedirectHandler()
    request = Request("https://public.example/start")

    with pytest.raises(AnthropicCallsDisabledError):
        handler.redirect_request(
            request,
            fp=None,
            code=302,
            msg="Found",
            headers={},
            newurl="https://api.anthropic.com./v1/messages",
        )


def test_safe_urlopen_uses_checked_opener(monkeypatch):
    captured = []

    class FakeOpener:
        def open(self, request, timeout):
            captured.append((request.full_url, timeout))
            return object()

    def fake_build_opener(*handlers):
        assert any(isinstance(handler, urllib.request.HTTPRedirectHandler) for handler in handlers)
        return FakeOpener()

    monkeypatch.setattr("urllib.request.build_opener", fake_build_opener)
    safe_urlopen(Request("https://public.example/data"), timeout=3)
    assert captured == [("https://public.example/data", 3)]


def test_safe_external_urlopen_rejects_anthropic_host_before_network(monkeypatch):
    request = Request("https://api.anthropic.com/v1/compliance")
    monkeypatch.setattr(
        "urllib.request.build_opener",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network setup must not occur")),
    )

    with pytest.raises(AnthropicCallsDisabledError):
        safe_external_urlopen(request, timeout=1)


def test_anthropic_sdk_client_uses_network_blocking_transport():
    client = create_anthropic_client(api_key="test-only")

    with patch.object(httpx2.HTTPTransport, "handle_request", side_effect=AssertionError("network access")):
        with pytest.raises(Exception) as raised:
            client.messages.create(model="blocked", max_tokens=1, messages=[{"role": "user", "content": "x"}])

    cause = raised.value
    while cause is not None and not isinstance(cause, AnthropicCallsDisabledError):
        cause = cause.__cause__
    assert isinstance(cause, AnthropicCallsDisabledError)
