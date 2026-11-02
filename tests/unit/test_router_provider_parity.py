"""Regression tests for Slice E — provider-neutral routing in the multi-agent router."""

from __future__ import annotations

import urllib.parse

import pytest

import zcoder.agent.orchestration.providers as providers
from zcoder.agent.orchestration.router import _call, _post, classify, route_and_call

# ── providers module ──────────────────────────────────────────────────────────


def test_provider_choices_and_defaults():
    assert set(providers.PROVIDER_CHOICES) == {
        "gemini",
        "xai",
        "groq",
        "openrouter",
        "cerebras",
        "nvidia",
        "openai_compatible",
        "ollama",
        "local",
    }
    for name in providers.PROVIDER_CHOICES:
        assert name in providers.PROVIDER_DEFAULTS
    assert providers.PROVIDER_DEFAULTS["ollama"]["base_url"] == "http://localhost:11434"


def test_resolve_provider_defaults_to_local_compatible_gateway(monkeypatch):
    monkeypatch.delenv("ZCODER_PROVIDER", raising=False)
    monkeypatch.delenv("ZCODER_LOCAL_MODE", raising=False)
    assert providers.resolve_provider(None) == "openai_compatible"
    assert providers.resolve_provider("") == "openai_compatible"


def test_resolve_provider_cli_wins_over_env(monkeypatch):
    monkeypatch.setenv("ZCODER_PROVIDER", "local")
    assert providers.resolve_provider("ollama") == "ollama"


def test_resolve_provider_env(monkeypatch):
    monkeypatch.setenv("ZCODER_PROVIDER", "ollama")
    monkeypatch.delenv("ZCODER_LOCAL_MODE", raising=False)
    assert providers.resolve_provider(None) == "ollama"


def test_resolve_provider_local_mode(monkeypatch):
    monkeypatch.delenv("ZCODER_PROVIDER", raising=False)
    monkeypatch.setenv("ZCODER_LOCAL_MODE", "1")
    assert providers.resolve_provider(None) == "local"
    monkeypatch.setenv("ZCODER_LOCAL_MODE", "true")
    assert providers.resolve_provider(None) == "local"


@pytest.mark.parametrize("local_mode", ["1", "true", "yes"])
def test_local_mode_overrides_cli_and_environment_provider(local_mode, monkeypatch):
    monkeypatch.setenv("ZCODER_LOCAL_MODE", local_mode)
    monkeypatch.setenv("ZCODER_PROVIDER", "gemini")

    assert providers.resolve_provider("xai") == "local"
    assert providers.resolve_provider(None) == "local"


def test_router_uses_local_client_when_remote_provider_is_overridden(monkeypatch):
    monkeypatch.setenv("ZCODER_LOCAL_MODE", "1")
    monkeypatch.setenv("ZCODER_PROVIDER", "gemini")
    monkeypatch.delenv("ZCODER_BASE_URL", raising=False)
    captured = {}

    class FakeCoder:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs

        def generate(self, prompt, **kwargs):
            captured["prompt"] = prompt
            return "local response"

    monkeypatch.setattr("zcoder.services.coder.Coder", FakeCoder)
    monkeypatch.setattr(
        "zcoder.agent.orchestration.router.urlopen_json",
        lambda *args, **kwargs: pytest.fail("remote provider network must remain unused"),
    )

    result = _call(
        "remote-key-must-not-be-used",
        {"model": "local-qwen", "messages": [{"role": "user", "content": "hello"}]},
        provider="xai",
        model="local-qwen",
    )

    assert result == {"text": "local response", "_provider": "local"}
    assert captured["kwargs"]["provider"] == "local"
    assert captured["prompt"] == "hello"


def test_resolve_provider_rejects_unknown():
    with pytest.raises(ValueError, match="Unknown provider"):
        providers.resolve_provider("openai")
    with pytest.raises(ValueError, match="Unknown ZCODER_PROVIDER"):
        import os as _os

        old = _os.getenv("ZCODER_PROVIDER")
        try:
            _os.environ["ZCODER_PROVIDER"] = "openai"
            providers.resolve_provider(None)
        finally:
            if old is None:
                _os.environ.pop("ZCODER_PROVIDER", None)
            else:
                _os.environ["ZCODER_PROVIDER"] = old


def test_resolve_api_key_cli_wins(monkeypatch):
    assert providers.resolve_api_key("openai_compatible", "cli-key") == "cli-key"


def test_resolve_api_key_provider_env(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-be-used")
    assert providers.resolve_api_key("local", None) == ""


def test_resolve_api_key_ollama_no_key_needed():
    assert providers.resolve_api_key("ollama", None) == ""
    assert providers.resolve_api_key("local", None) == ""
    assert providers.resolve_api_key("local", "remote-key-must-not-be-used") == ""


def test_resolve_base_url_cli_wins(monkeypatch):
    monkeypatch.setenv("ZCODER_BASE_URL", "https://env.example.com")
    assert (
        providers.resolve_base_url("openai_compatible", "https://cli.example.com")
        == "https://cli.example.com"
    )


def test_default_compatible_gateway_uses_loopback_llama_server(monkeypatch):
    monkeypatch.delenv("ZCODER_BASE_URL", raising=False)
    assert providers.resolve_base_url("openai_compatible") == "http://127.0.0.1:8080/v1"


def test_resolve_base_url_env_gateway(monkeypatch):
    monkeypatch.setenv("ZCODER_BASE_URL", "https://gateway.example.com")
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    assert providers.resolve_base_url("openai_compatible", None) == "https://gateway.example.com"


def test_resolve_base_url_ollama_env(monkeypatch):
    monkeypatch.delenv("ZCODER_BASE_URL", raising=False)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.local:11434")
    assert providers.resolve_base_url("ollama", None) == "http://ollama.local:11434"


def test_resolve_base_url_rejects_file_scheme():
    with pytest.raises(ValueError, match="Unsupported provider base URL scheme"):
        providers.resolve_base_url("openai_compatible", "file:///etc/passwd")
    with pytest.raises(ValueError, match="Unsupported provider base URL scheme"):
        providers.resolve_base_url("openai_compatible", "ftp://example.com")


@pytest.mark.parametrize("url", ["https://", "http://user:pass@host", "https://host/v1?key=secret"])
def test_resolve_base_url_rejects_malformed_gateway(url):
    with pytest.raises(ValueError, match="Provider base URL must"):
        providers.resolve_base_url("openai_compatible", url)


def test_openai_compatible_defaults_to_local_gateway(monkeypatch):
    monkeypatch.delenv("ZCODER_BASE_URL", raising=False)
    assert providers.resolve_base_url("openai_compatible") == "http://127.0.0.1:8080/v1"
    assert (
        providers.resolve_base_url("openai_compatible", "http://localhost:1234/v1")
        == "http://localhost:1234/v1"
    )


def test_removed_remote_provider_is_rejected():
    with pytest.raises(ValueError, match="Unknown provider"):
        providers.resolve_provider("anthropic")


def test_endpoint_for_each_provider():
    assert (
        providers.endpoint_for("ollama", "http://localhost:11434", "llama3")
        == "http://localhost:11434/api/chat"
    )
    assert providers.endpoint_for("local", "", "any") == ""


@pytest.mark.parametrize(
    ("provider", "expected"),
    [
        ("groq", "https://api.groq.com/openai/v1/chat/completions"),
        ("openrouter", "https://openrouter.ai/api/v1/chat/completions"),
        ("cerebras", "https://api.cerebras.ai/v1/chat/completions"),
    ],
)
def test_hosted_free_tier_provider_endpoints(provider, expected, monkeypatch):
    monkeypatch.delenv("ZCODER_BASE_URL", raising=False)
    assert providers.endpoint_for(provider, providers.resolve_base_url(provider), "model") == expected


def test_openai_compatible_endpoint():
    assert (
        providers.endpoint_for("openai_compatible", "http://localhost:1234/v1", "model")
        == "http://localhost:1234/v1/chat/completions"
    )


def test_headers_for_local_providers():
    assert "Authorization" not in providers.headers_for("ollama", "unused")
    assert "x-api-key" not in providers.headers_for("local", "unused")


def test_build_payload_ollama():
    p = providers.build_payload(
        "ollama", "llama3", [{"role": "user", "content": "hi"}], "sys", 200, {"temperature": 0.3}
    )
    assert p["messages"][0] == {"role": "system", "content": "sys"}
    assert p["stream"] is False
    assert p["options"]["num_predict"] == 200
    assert p["options"]["temperature"] == 0.3


def test_parse_response_local_providers():
    assert providers.parse_response("ollama", {"message": {"role": "assistant", "content": "ollama hi"}}) == (
        "ollama hi"
    )
    assert providers.parse_response("local", {}) == "[local mode] No upstream call — local stub response."


def _mock_urlopen_json_for(provider_data: dict):
    """Return a monkeypatch target that captures the request and returns provider_data."""

    def fake(req, timeout=60):
        return provider_data

    return fake


def test_router_call_uses_provider_endpoint(monkeypatch):
    captured: dict = {}

    def fake(req, timeout=60):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.headers)
        return {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}

    monkeypatch.setattr("zcoder.agent.orchestration.router.urlopen_json", fake)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    # gemini provider should hit the gemini endpoint with x-goog-api-key
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    data = _call(
        "g-key",
        {"messages": [{"role": "user", "content": "hi"}], "max_tokens": 10},
        provider="gemini",
        base_url="https://generativelanguage.googleapis.com",
        model="gemini-2.0-flash",
    )
    assert urllib.parse.urlparse(captured["url"]).hostname == "generativelanguage.googleapis.com"
    assert "gemini-2.0-flash" in captured["url"]
    assert data["content"][0]["text"] == "ok"


def test_router_call_local_mode_no_network(monkeypatch):
    # Local provider uses the loopback Coder and never the router HTTP adapter.
    def _fail(*a, **kw):
        raise AssertionError("local provider must not make a network call")

    monkeypatch.setattr("zcoder.agent.orchestration.router.urlopen_json", _fail)
    from unittest.mock import Mock

    coder = Mock()
    coder.generate.return_value = "local inference result"
    constructor = Mock(return_value=coder)
    monkeypatch.setattr("zcoder.services.coder.Coder", constructor)
    data = _call(
        "", {"messages": [{"role": "user", "content": "hi"}], "max_tokens": 10}, provider="local", model="any"
    )
    assert data["text"] == "local inference result"
    constructor.assert_called_once_with(
        model="any", temperature=0.3, max_tokens=10, provider="local", base_url=None
    )
    coder.generate.assert_called_once_with("hi", system=None, history=[])


def test_router_call_rejects_file_scheme(monkeypatch):
    with pytest.raises(ValueError, match="Unsupported provider base URL scheme"):
        _call(
            "k",
            {"messages": [{"role": "user", "content": "hi"}], "max_tokens": 10},
            provider="openai_compatible",
            base_url="file:///etc/passwd",
            model="m",
        )


def test_classify_and_route_use_provider(monkeypatch):
    # classify and route_and_call should thread provider/base_url through
    def fake_call(api_key, payload, provider=None, base_url=None, model=None):
        return {"content": [{"type": "text", "text": '{"agent": "research", "reason": "test"}'}]}

    monkeypatch.setattr("zcoder.agent.orchestration.router._call", fake_call)
    agent, reason = classify(
        "do research",
        {"research": "desc", "code": "desc"},
        "k",
        "m",
        provider="xai",
        base_url="https://api.x.ai",
    )
    assert agent == "research"


def test_route_and_call_parallel_uses_provider(monkeypatch):
    calls: list[dict] = []

    def fake_call(api_key, payload, provider=None, base_url=None, model=None):
        calls.append({"provider": provider, "payload": payload})
        return {"content": [{"type": "text", "text": "ans"}]}

    monkeypatch.setattr("zcoder.agent.orchestration.router._call", fake_call)
    result = route_and_call(
        "hi",
        "k",
        "m",
        table={"code": "desc", "research": "desc"},
        parallel=True,
        provider="xai",
        base_url="https://api.x.ai",
    )
    # parallel fans out to each agent + one synthesis call
    assert len(calls) == 3
    assert all(c["provider"] == "xai" for c in calls)
    assert isinstance(result, str)


def test_post_preserves_error_contract(monkeypatch):
    def raising_call(*a, **kw):
        raise RuntimeError("boom")

    monkeypatch.setattr("zcoder.agent.orchestration.router._call", raising_call)
    assert "boom" in _post("k", {}, provider="local", model="m")["error"]
