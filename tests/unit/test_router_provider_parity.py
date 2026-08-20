"""Regression tests for Slice E — provider-neutral routing in the multi-agent router."""

from __future__ import annotations

import urllib.parse

import pytest

import zcoder.claude.orchestration.providers as providers
from zcoder.claude.orchestration.router import _call, _post, classify, route_and_call

# ── providers module ──────────────────────────────────────────────────────────


def test_provider_choices_and_defaults():
    assert set(providers.PROVIDER_CHOICES) == {"anthropic", "gemini", "xai", "ollama", "local"}
    for name in providers.PROVIDER_CHOICES:
        assert name in providers.PROVIDER_DEFAULTS
    assert providers.PROVIDER_DEFAULTS["anthropic"]["base_url"] == "https://api.anthropic.com"
    assert providers.PROVIDER_DEFAULTS["ollama"]["base_url"] == "http://localhost:11434"


def test_resolve_provider_defaults_to_anthropic(monkeypatch):
    monkeypatch.delenv("ZCODER_PROVIDER", raising=False)
    monkeypatch.delenv("ZCODER_LOCAL_MODE", raising=False)
    assert providers.resolve_provider(None) == "anthropic"
    assert providers.resolve_provider("") == "anthropic"


def test_resolve_provider_cli_wins_over_env(monkeypatch):
    monkeypatch.setenv("ZCODER_PROVIDER", "gemini")
    assert providers.resolve_provider("xai") == "xai"


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
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")
    assert providers.resolve_api_key("anthropic", "cli-key") == "cli-key"


def test_resolve_api_key_provider_env(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "gem-key")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert providers.resolve_api_key("gemini", None) == "gem-key"


def test_resolve_api_key_gemini_fallback_google(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")
    assert providers.resolve_api_key("gemini", None) == "google-key"


def test_resolve_api_key_ollama_no_key_needed():
    assert providers.resolve_api_key("ollama", None) == ""
    assert providers.resolve_api_key("local", None) == ""


def test_resolve_base_url_cli_wins(monkeypatch):
    monkeypatch.setenv("ZCODER_BASE_URL", "https://env.example.com")
    assert providers.resolve_base_url("anthropic", "https://cli.example.com") == "https://cli.example.com"


def test_resolve_base_url_env_gateway(monkeypatch):
    monkeypatch.setenv("ZCODER_BASE_URL", "https://gateway.example.com")
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    assert providers.resolve_base_url("anthropic", None) == "https://gateway.example.com"


def test_resolve_base_url_ollama_env(monkeypatch):
    monkeypatch.delenv("ZCODER_BASE_URL", raising=False)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.local:11434")
    assert providers.resolve_base_url("ollama", None) == "http://ollama.local:11434"


def test_resolve_base_url_rejects_file_scheme():
    with pytest.raises(ValueError, match="Unsupported provider base URL scheme"):
        providers.resolve_base_url("anthropic", "file:///etc/passwd")
    with pytest.raises(ValueError, match="Unsupported provider base URL scheme"):
        providers.resolve_base_url("anthropic", "ftp://example.com")


def test_endpoint_for_each_provider():
    assert (
        providers.endpoint_for("anthropic", "https://api.anthropic.com", "claude-sonnet-5")
        == "https://api.anthropic.com/v1/messages"
    )
    assert (
        providers.endpoint_for("xai", "https://api.x.ai", "grok-3") == "https://api.x.ai/v1/chat/completions"
    )
    assert (
        providers.endpoint_for("ollama", "http://localhost:11434", "llama3")
        == "http://localhost:11434/api/chat"
    )
    assert (
        providers.endpoint_for("gemini", "https://generativelanguage.googleapis.com", "gemini-2.0-flash")
        == "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
    )
    assert providers.endpoint_for("local", "", "any") == ""


def test_headers_for_each_provider():
    h = providers.headers_for("anthropic", "sk-123")
    assert h["x-api-key"] == "sk-123"
    assert h["anthropic-version"] == "2023-06-01"
    h = providers.headers_for("gemini", "g-key")
    assert h["x-goog-api-key"] == "g-key"
    h = providers.headers_for("xai", "x-key")
    assert h["Authorization"] == "Bearer x-key"
    h = providers.headers_for("ollama", "")
    assert "Authorization" not in h and "x-api-key" not in h
    h = providers.headers_for("local", "")
    assert "Authorization" not in h


def test_build_payload_anthropic():
    p = providers.build_payload(
        "anthropic", "claude-sonnet-5", [{"role": "user", "content": "hi"}], "sys", 100, {"temperature": 0.5}
    )
    assert p["model"] == "claude-sonnet-5"
    assert p["system"] == "sys"
    assert p["messages"] == [{"role": "user", "content": "hi"}]
    assert p["temperature"] == 0.5


def test_build_payload_xai_injects_system():
    p = providers.build_payload("xai", "grok-3", [{"role": "user", "content": "hi"}], "sys", 100, {})
    assert p["messages"][0] == {"role": "system", "content": "sys"}
    assert p["messages"][1] == {"role": "user", "content": "hi"}


def test_build_payload_gemini():
    p = providers.build_payload(
        "gemini",
        "gemini-2.0-flash",
        [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "there"}],
        None,
        100,
        {"temperature": 0.7},
    )
    assert p["contents"][0] == {"role": "user", "parts": [{"text": "hi"}]}
    assert p["contents"][1] == {"role": "model", "parts": [{"text": "there"}]}
    assert p["generationConfig"]["temperature"] == 0.7
    assert p["generationConfig"]["maxOutputTokens"] == 100


def test_build_payload_gemini_system_instruction():
    p = providers.build_payload(
        "gemini", "gemini-2.0-flash", [{"role": "user", "content": "hi"}], "be helpful", 50, {}
    )
    assert p["systemInstruction"] == {"parts": [{"text": "be helpful"}]}


def test_build_payload_ollama():
    p = providers.build_payload(
        "ollama", "llama3", [{"role": "user", "content": "hi"}], "sys", 200, {"temperature": 0.3}
    )
    assert p["messages"][0] == {"role": "system", "content": "sys"}
    assert p["stream"] is False
    assert p["options"]["num_predict"] == 200
    assert p["options"]["temperature"] == 0.3


def test_parse_response_each_provider():
    assert providers.parse_response("anthropic", {"content": [{"type": "text", "text": "hello"}]}) == "hello"
    assert providers.parse_response("xai", {"choices": [{"message": {"content": "xai hi"}}]}) == "xai hi"
    assert (
        providers.parse_response("gemini", {"candidates": [{"content": {"parts": [{"text": "g hi"}]}}]})
        == "g hi"
    )
    assert (
        providers.parse_response("ollama", {"message": {"role": "assistant", "content": "ollama hi"}})
        == "ollama hi"
    )
    assert "local mode" in providers.parse_response("local", {}).lower()


# ── router integration (mocked network) ─────────────────────────────────────


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

    monkeypatch.setattr("zcoder.claude.orchestration.router.urlopen_json", fake)
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
    # local provider must not call urlopen_json at all
    def _fail(*a, **kw):
        raise AssertionError("local provider must not make a network call")

    monkeypatch.setattr("zcoder.claude.orchestration.router.urlopen_json", _fail)
    data = _call(
        "", {"messages": [{"role": "user", "content": "hi"}], "max_tokens": 10}, provider="local", model="any"
    )
    assert "local mode" in data.get("text", "").lower()


def test_router_call_rejects_file_scheme(monkeypatch):
    with pytest.raises(ValueError, match="Unsupported provider base URL scheme"):
        _call(
            "k",
            {"messages": [{"role": "user", "content": "hi"}], "max_tokens": 10},
            provider="anthropic",
            base_url="file:///etc/passwd",
            model="m",
        )


def test_classify_and_route_use_provider(monkeypatch):
    # classify and route_and_call should thread provider/base_url through
    def fake_call(api_key, payload, provider=None, base_url=None, model=None):
        return {"content": [{"type": "text", "text": '{"agent": "research", "reason": "test"}'}]}

    monkeypatch.setattr("zcoder.claude.orchestration.router._call", fake_call)
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

    monkeypatch.setattr("zcoder.claude.orchestration.router._call", fake_call)
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

    monkeypatch.setattr("zcoder.claude.orchestration.router._call", raising_call)
    assert "boom" in _post("k", {}, provider="anthropic", model="m")["error"]
