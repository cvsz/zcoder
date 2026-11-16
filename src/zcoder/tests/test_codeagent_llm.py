"""Unit tests for zcoder.agent.codeagent.llm - local OpenAI-compatible streaming client."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from zcoder.agent.codeagent.llm import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    LLMChunk,
    LLMError,
    LocalLLM,
    ToolCallRequest,
    _finish_call,
    endpoint,
    local_base_url,
)


class TestLocalBaseUrl:
    """Tests for local_base_url() — loopback-only URL validation."""

    def test_default_when_no_env(self, monkeypatch):
        monkeypatch.delenv("ZCODER_BASE_URL", raising=False)
        assert local_base_url() == DEFAULT_BASE_URL

    def test_env_value_used(self, monkeypatch):
        monkeypatch.setenv("ZCODER_BASE_URL", "http://127.0.0.1:9000")
        assert local_base_url() == "http://127.0.0.1:9000"

    def test_explicit_arg_overrides_env(self, monkeypatch):
        monkeypatch.setenv("ZCODER_BASE_URL", "http://127.0.0.1:9000")
        assert local_base_url("http://127.0.0.1:8081") == "http://127.0.0.1:8081"

    def test_trailing_slash_stripped(self, monkeypatch):
        monkeypatch.setenv("ZCODER_BASE_URL", "http://127.0.0.1:8080/")
        assert local_base_url() == "http://127.0.0.1:8080"

    def test_localhost_v4_allowed(self):
        assert local_base_url("http://127.0.0.1:8080") == "http://127.0.0.1:8080"

    def test_localhost_v6_allowed(self):
        assert local_base_url("http://[::1]:8080") == "http://[::1]:8080"

    @pytest.mark.parametrize(
        "bad_url",
        [
            "https://127.0.0.1:8080",  # wrong scheme
            "http://localhost:8080",  # not loopback IP
            "http://example.com:8080",  # remote host
            "http://user:pass@127.0.0.1:8080",  # credentials
            "http://127.0.0.1:8080/?q=1",  # query string
            "http://127.0.0.1:8080#frag",  # fragment
        ],
    )
    def test_rejects_non_loopback(self, monkeypatch, bad_url):
        monkeypatch.delenv("ZCODER_BASE_URL", raising=False)
        with pytest.raises(ValueError, match="loopback"):
            local_base_url(bad_url)

    def test_rejects_env_non_loopback(self, monkeypatch):
        monkeypatch.setenv("ZCODER_BASE_URL", "http://example.com:8080")
        with pytest.raises(ValueError, match="loopback"):
            local_base_url()


class TestEndpoint:
    """Tests for endpoint() — API URL construction."""

    def test_appends_v1_when_base_lacks_it(self):
        assert endpoint("models") == f"{DEFAULT_BASE_URL}/v1/models"
        assert endpoint("chat/completions") == f"{DEFAULT_BASE_URL}/v1/chat/completions"

    def test_no_double_v1_when_base_has_it(self):
        base = f"{DEFAULT_BASE_URL}/v1"
        assert endpoint("models", base) == f"{base}/models"

    def test_strips_leading_slash_from_path(self):
        base = f"{DEFAULT_BASE_URL}/v1"
        assert endpoint("/models", base) == f"{base}/models"


class TestLLMError:
    """Tests for LLMError exception class."""

    def test_default_retryable_false(self):
        err = LLMError("boom")
        assert str(err) == "boom"
        assert err.retryable is False

    def test_retryable_true(self):
        err = LLMError("transient", retryable=True)
        assert err.retryable is True


class TestToolCallRequest:
    """Tests for ToolCallRequest dataclass."""

    def test_create(self):
        req = ToolCallRequest(id="call_1", name="read", args={"path": "/tmp/x"})
        assert req.id == "call_1"
        assert req.name == "read"
        assert req.args == {"path": "/tmp/x"}


class TestLLMChunk:
    """Tests for LLMChunk dataclass."""

    def test_minimal(self):
        chunk = LLMChunk(kind="text")
        assert chunk.kind == "text"
        assert chunk.text == ""
        assert chunk.tool_calls == []
        assert chunk.prompt_tokens == 0
        assert chunk.completion_tokens == 0
        assert chunk.finish_reason == ""

    def test_full(self):
        chunk = LLMChunk(
            kind="tool_calls",
            text="hello",
            tool_calls=[ToolCallRequest(id="c1", name="read", args={})],
            prompt_tokens=10,
            completion_tokens=5,
            finish_reason="stop",
        )
        assert chunk.kind == "tool_calls"
        assert chunk.text == "hello"
        assert len(chunk.tool_calls) == 1
        assert chunk.tool_calls[0].id == "c1"
        assert chunk.prompt_tokens == 10
        assert chunk.completion_tokens == 5
        assert chunk.finish_reason == "stop"


class TestLocalLLMInit:
    """Tests for LocalLLM constructor."""

    def test_defaults(self, monkeypatch):
        monkeypatch.delenv("ZCODER_MODEL", raising=False)
        llm = LocalLLM()
        assert llm.model == DEFAULT_MODEL
        assert llm.base_url == DEFAULT_BASE_URL
        assert llm.temperature == 0.2
        assert llm.max_tokens == 4096
        assert llm.timeout == 600

    def test_custom_model(self):
        llm = LocalLLM(model="my-model")
        assert llm.model == "my-model"

    def test_env_model(self, monkeypatch):
        monkeypatch.setenv("ZCODER_MODEL", "env-model")
        llm = LocalLLM()
        assert llm.model == "env-model"

    def test_custom_base_url(self):
        llm = LocalLLM(base_url="http://127.0.0.1:9000")
        assert llm.base_url == "http://127.0.0.1:9000"

    def test_invalid_base_url_raises(self):
        with pytest.raises(ValueError, match="loopback"):
            LocalLLM(base_url="http://example.com:8080")

    def test_custom_temperature_and_max_tokens(self):
        llm = LocalLLM(temperature=0.7, max_tokens=2048)
        assert llm.temperature == 0.7
        assert llm.max_tokens == 2048


class TestFinishCall:
    """Tests for _finish_call() — tool call argument parsing."""

    def test_valid_json_args(self):
        call = _finish_call(0, {"id": "c1", "name": "read", "args": '{"path": "/tmp/x"}'})
        assert call.id == "c1"
        assert call.name == "read"
        assert call.args == {"path": "/tmp/x"}

    def test_empty_args(self):
        call = _finish_call(0, {"id": "c1", "name": "read", "args": ""})
        assert call.args == {}

    def test_missing_id_defaults(self):
        call = _finish_call(3, {"name": "read", "args": ""})
        assert call.id == "call_3"

    def test_invalid_json_args(self):
        call = _finish_call(0, {"id": "c1", "name": "read", "args": "{not json"})
        assert call.id == "c1"
        assert call.name == "read"
        assert "__parse_error__" in call.args

    def test_missing_name(self):
        call = _finish_call(0, {"id": "c1", "args": '{"x": 1}'})
        assert call.name == ""


class TestDiscoverModel:
    """Tests for LocalLLM.discover_model() with mocked network."""

    def test_returns_model_id(self, monkeypatch):
        llm = LocalLLM()

        class FakeResp:
            def read(self):
                return json.dumps({"data": [{"id": "gguf-model-q4"}]}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        with patch.object(llm, "_open", return_value=FakeResp()):
            result = llm.discover_model()
        assert result == "gguf-model-q4"
        assert llm.model == "gguf-model-q4"

    def test_returns_none_on_error(self, monkeypatch):
        llm = LocalLLM()

        def boom(*a, **k):
            raise OSError("connection refused")

        with patch.object(llm, "_open", side_effect=boom):
            result = llm.discover_model()
        assert result is None

    def test_returns_none_on_empty_data(self, monkeypatch):
        llm = LocalLLM()

        class FakeResp:
            def read(self):
                return json.dumps({"data": []}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        with patch.object(llm, "_open", return_value=FakeResp()):
            result = llm.discover_model()
        assert result is None
