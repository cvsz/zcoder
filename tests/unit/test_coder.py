"""Tests for the loopback-only OpenAI-compatible model client."""

import io
import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

import zcoder.core.resilience as resilience
from zcoder.services.coder import Coder, _RejectRedirects


@pytest.fixture(autouse=True)
def fresh_breaker(monkeypatch):
    monkeypatch.setattr(
        "zcoder.services.coder._default_breaker",
        resilience.CircuitBreaker(failure_threshold=10, reset_timeout=0.01),
    )


def _fake_response(text: str):
    body = json.dumps({"choices": [{"message": {"content": text}}]}).encode()
    response = MagicMock()
    response.read.return_value = body
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


def test_generate_uses_local_chat_completions_without_api_key():
    coder = Coder(model="zqwen2.5-coder-7b-instruct-q4_k_m")
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["request"] = request
        captured["payload"] = json.loads(request.data.decode())
        return _fake_response("local response")

    with patch("zcoder.services.coder._open_local", side_effect=fake_urlopen):
        result = coder.generate("hello", system="Be concise")

    assert result == "local response"
    assert captured["request"].full_url == "http://127.0.0.1:8080/v1/chat/completions"
    assert captured["request"].get_header("Authorization") is None
    assert captured["payload"]["model"] == "zqwen2.5-coder-7b-instruct-q4_k_m"
    assert captured["payload"]["messages"] == [
        {"role": "system", "content": "Be concise"},
        {"role": "user", "content": "hello"},
    ]


def test_generate_records_provider_neutral_model_metrics(monkeypatch):
    from zcoder.infrastructure.observability.otel import ZCoderMetrics

    metrics = ZCoderMetrics()
    monkeypatch.setattr("zcoder.infrastructure.observability.otel.get_metrics", lambda: metrics)
    coder = Coder(model="local-qwen")
    with patch("zcoder.services.coder._open_local", return_value=_fake_response("ok")):
        assert coder.generate("hello") == "ok"

    assert metrics.model_calls_total.get() == 1
    assert metrics.model_errors_total.get() == 0


def test_generate_includes_file_content_and_history():
    coder = Coder()
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["payload"] = json.loads(request.data.decode())
        return _fake_response("ok")

    with patch("zcoder.services.coder._open_local", side_effect=fake_urlopen):
        coder.generate(
            "summarize", file_content="source", history=[{"role": "assistant", "content": "prior"}]
        )

    assert captured["payload"]["messages"] == [
        {"role": "assistant", "content": "prior"},
        {"role": "user", "content": "File content:\n```\nsource\n```\n\nsummarize"},
    ]


def test_generate_adds_v1_path_when_base_url_omits_it():
    coder = Coder(base_url="http://127.0.0.1:8080")
    with patch("zcoder.services.coder._open_local", return_value=_fake_response("ok")) as request:
        assert coder.generate("hello") == "ok"
    assert request.call_args.args[0].full_url == "http://127.0.0.1:8080/v1/chat/completions"


@pytest.mark.parametrize("url", ["https://example.com/v1", "http://127.0.0.1:8080/v1?redirect=1"])
def test_generate_rejects_non_local_or_ambiguous_base_url(url):
    coder = Coder(base_url=url)
    with patch("zcoder.services.coder._open_local") as request:
        result = coder.generate("hello")
    assert "local llama-server" in result
    request.assert_not_called()


def test_cloud_only_options_fail_closed_without_network_call():
    coder = Coder(fast_mode=True)
    with patch("zcoder.services.coder._open_local") as request:
        result = coder.generate("hello")
    assert "unavailable with the local model" in result
    request.assert_not_called()


def test_non_local_provider_fails_closed_without_network_call():
    coder = Coder(provider="anthropic")
    with patch("zcoder.services.coder._open_local") as request:
        result = coder.generate("hello")
    assert "only supports the local model server" in result
    request.assert_not_called()


def test_local_http_client_refuses_redirects():
    handler = _RejectRedirects()
    assert handler.redirect_request(None, None, 302, "Found", {}, "https://example.com") is None


def test_http_error_returns_api_status_without_retrying_auth_failure():
    coder = Coder()
    calls = 0

    def unauthorized(request, timeout=None):
        nonlocal calls
        calls += 1
        raise urllib.error.HTTPError(
            url=request.full_url,
            code=401,
            msg="unauthorized",
            hdrs=None,
            fp=io.BytesIO(b'{"error":"bad key"}'),
        )

    with patch("zcoder.services.coder._open_local", side_effect=unauthorized):
        result = coder.generate("hello")
    assert "[API ERROR 401]" in result
    assert calls == 1


def test_invalid_completion_shape_returns_actionable_error():
    coder = Coder()
    response = MagicMock()
    response.read.return_value = b"{}"
    response.__enter__.return_value = response
    with patch("zcoder.services.coder._open_local", return_value=response):
        result = coder.generate("hello")
    assert "invalid chat completion" in result
