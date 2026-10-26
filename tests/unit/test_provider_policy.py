import urllib.request

import pytest

from zcoder.core.outbound_security import safe_external_urlopen
from zcoder.core.provider_policy import create_anthropic_client
from zcoder.core.resilience import safe_urlopen


@pytest.mark.parametrize("value", ["1", "true", "yes"])
def test_sdk_client_construction_fails_closed_in_local_mode(value, monkeypatch):
    monkeypatch.setenv("ZCODER_LOCAL_MODE", value)

    with pytest.raises(RuntimeError, match="Anthropic API access is disabled"):
        create_anthropic_client("must-not-be-used")


def test_anthropic_capability_constructor_obeys_local_mode(monkeypatch):
    from zcoder.agent.capabilities.thinking import ThinkingCoder

    monkeypatch.setenv("ZCODER_LOCAL_MODE", "1")

    with pytest.raises(RuntimeError, match="Anthropic API access is disabled"):
        ThinkingCoder(api_key="must-not-be-used", model="claude-test")


def test_urllib_anthropic_endpoint_is_blocked_before_network(monkeypatch):
    monkeypatch.setenv("ZCODER_LOCAL_MODE", "1")
    opened = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: opened.append(args))
    request = urllib.request.Request("https://api.anthropic.com/v1/messages", method="POST")

    with pytest.raises(RuntimeError, match="Anthropic API access is disabled"):
        safe_urlopen(request, timeout=1)

    assert opened == []


def test_untrusted_url_anthropic_endpoint_is_blocked_before_dns(monkeypatch):
    monkeypatch.setenv("ZCODER_LOCAL_MODE", "1")
    request = urllib.request.Request("https://api.anthropic.com/v1/messages")

    with pytest.raises(RuntimeError, match="Anthropic API access is disabled"):
        safe_external_urlopen(request, timeout=1)


@pytest.mark.parametrize(
    "url",
    [
        "https://api.voyageai.com/v1/embeddings",
        "https://generativelanguage.googleapis.com/v1/models",
        "https://api.x.ai/v1/chat/completions",
        "https://api.groq.com/openai/v1/chat/completions",
        "https://openrouter.ai/api/v1/chat/completions",
        "https://api.cerebras.ai/v1/chat/completions",
        "https://api.openai.com/v1/chat/completions",
    ],
)
def test_local_mode_blocks_hosted_model_apis_before_network(url, monkeypatch):
    monkeypatch.setenv("ZCODER_LOCAL_MODE", "1")
    opened = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: opened.append(args))

    with pytest.raises(RuntimeError, match="Hosted model API access is disabled"):
        safe_urlopen(urllib.request.Request(url, method="POST"), timeout=1)

    assert opened == []


def test_local_mode_keeps_non_anthropic_integrations_available(monkeypatch):
    monkeypatch.setenv("ZCODER_LOCAL_MODE", "1")
    sentinel = object()
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return sentinel

    class FakeOpener:
        def open(self, request, timeout):
            return fake_urlopen(request, timeout)

    monkeypatch.setattr(urllib.request, "build_opener", lambda *handlers: FakeOpener())
    result = safe_urlopen(urllib.request.Request("https://api.github.com/repos"), timeout=2)

    assert result is sentinel
    assert captured == {"url": "https://api.github.com/repos", "timeout": 2}


def test_local_mode_blocks_anthropic_redirect_before_following(monkeypatch):
    from zcoder.core.outbound_security import _ExternalRedirectHandler
    from zcoder.core.resilience import _LocalOnlyRedirectHandler

    monkeypatch.setenv("ZCODER_LOCAL_MODE", "1")
    handler = _LocalOnlyRedirectHandler()
    request = urllib.request.Request("https://api.github.com/repos")

    with pytest.raises(RuntimeError, match="Anthropic API access is disabled"):
        handler.redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "https://api.anthropic.com/v1/messages",
        )

    with pytest.raises(RuntimeError, match="Anthropic API access is disabled"):
        _ExternalRedirectHandler().redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "https://api.anthropic.com/v1/messages",
        )

    with pytest.raises(RuntimeError, match="Hosted model API access is disabled"):
        handler.redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "https://api.voyageai.com/v1/embeddings",
        )


def test_local_mode_blocks_anthropic_oidc_jwks_before_httpx(monkeypatch):
    from zcoder.infrastructure.auth import oidc

    monkeypatch.setenv("ZCODER_LOCAL_MODE", "1")
    called = []
    monkeypatch.setattr(oidc, "_HTTPX_AVAILABLE", True)
    from types import SimpleNamespace

    monkeypatch.setattr(
        oidc,
        "httpx",
        SimpleNamespace(get=lambda *args, **kwargs: called.append(args)),
        raising=False,
    )

    with pytest.raises(RuntimeError, match="Anthropic API access is disabled"):
        oidc._fetch_jwks("https://api.anthropic.com/v1/jwks")

    assert called == []
