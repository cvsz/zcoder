"""Regression tests for local-only provider routing."""

from __future__ import annotations

import json

import pytest

import zcoder.agent.orchestration.providers as providers
from zcoder.agent.orchestration.router import _call, _post, classify, route_and_call


def test_provider_choices_and_defaults(monkeypatch):
    assert set(providers.PROVIDER_CHOICES) == {"local", "llama_cpp"}
    monkeypatch.delenv("ZCODER_PROVIDER", raising=False)
    monkeypatch.delenv("ZCODER_LOCAL_MODE", raising=False)
    assert providers.resolve_provider() == "local"
    assert providers.resolve_provider("llama_cpp") == "local"


def test_remote_providers_are_rejected(monkeypatch):
    with pytest.raises(ValueError, match="Unknown provider"):
        providers.resolve_provider("anthropic")
    with pytest.raises(ValueError, match="Unknown provider"):
        providers.resolve_provider("gemini")
    monkeypatch.setenv("ZCODER_PROVIDER", "xai")
    with pytest.raises(ValueError, match="Unknown ZCODER_PROVIDER"):
        providers.resolve_provider()


def test_local_provider_never_resolves_cloud_credentials(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-be-used")
    monkeypatch.setenv("GEMINI_API_KEY", "must-not-be-used")
    assert providers.resolve_api_key("local", "explicit-secret") == ""


def test_local_base_url_and_endpoint_validation(monkeypatch):
    monkeypatch.setenv("ZCODER_BASE_URL", "http://127.0.0.1:9090")
    assert providers.resolve_base_url("local") == "http://127.0.0.1:9090"
    assert providers.endpoint_for("local", "http://127.0.0.1:8080", "zcoder-qwen2.5-coder-7b") == (
        "http://127.0.0.1:8080/v1/chat/completions"
    )
    with pytest.raises(ValueError, match="Unsupported provider base URL scheme"):
        providers.resolve_base_url("local", "file:///etc/passwd")


def test_model_aliases_use_zcoder_names():
    assert providers.resolve_model(None) == "zcoder-qwen2.5-coder-7b"
    assert providers.resolve_model("zcoder-qwen2.5-coder-1.5b") == "zcoder-qwen2.5-coder-1.5b"
    with pytest.raises(ValueError, match="Unsupported local model"):
        providers.resolve_model("claude-sonnet-5")


def test_router_call_local_uses_loopback(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"choices":[{"message":{"content":"local answer"}}]}'

    def fake_local_open(req, timeout):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data)
        return Response()

    monkeypatch.setattr("zcoder.agent.orchestration.router.safe_local_urlopen", fake_local_open)
    data = _call(
        "unused",
        {"messages": [{"role": "user", "content": "hi"}], "max_tokens": 10},
        provider="local",
        model="zcoder-qwen2.5-coder-1.5b",
    )
    assert captured["url"] == "http://127.0.0.1:8080/v1/chat/completions"
    assert captured["body"]["model"] == "zcoder-qwen2.5-coder-1.5b"
    assert data["content"][0]["text"] == "local answer"


def test_router_call_rejects_nonlocal_model_and_bad_scheme():
    with pytest.raises(ValueError, match="Unsupported local model"):
        _call("", {"messages": []}, provider="local", model="claude-sonnet-5")
    with pytest.raises(ValueError, match="Unsupported provider base URL scheme"):
        _call("", {"messages": []}, provider="local", base_url="file:///etc/passwd")


def test_classify_and_route_forward_local_provider(monkeypatch):
    def fake_call(api_key, payload, provider=None, base_url=None, model=None):
        return {"content": [{"type": "text", "text": '{"agent": "research", "reason": "test"}'}]}

    monkeypatch.setattr("zcoder.agent.orchestration.router._call", fake_call)
    agent, reason = classify(
        "do research", {"research": "desc", "code": "desc"}, "", "zcoder-qwen2.5-coder-7b"
    )
    assert agent == "research"
    assert reason == "test"


def test_route_parallel_uses_local_provider(monkeypatch):
    calls = []

    def fake_call(api_key, payload, provider=None, base_url=None, model=None):
        calls.append(provider)
        return {"content": [{"type": "text", "text": "answer"}]}

    monkeypatch.setattr("zcoder.agent.orchestration.router._call", fake_call)
    result = route_and_call(
        "hi",
        "",
        "zcoder-qwen2.5-coder-7b",
        table={"code": "desc", "research": "desc"},
        parallel=True,
        provider="local",
    )
    assert result
    assert len(calls) >= 2
    assert set(calls) == {"local"}


def test_post_preserves_error_contract(monkeypatch):
    monkeypatch.setattr(
        "zcoder.agent.orchestration.router._call",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert "boom" in _post("", {}, provider="local")["error"]
