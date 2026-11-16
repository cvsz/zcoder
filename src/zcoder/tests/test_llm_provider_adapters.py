"""Unit tests for LLM provider adapters (Anthropic, Gemini, Ollama)."""

from __future__ import annotations

import pytest

from zcoder.services.llm.anthropic_adapter import AnthropicAdapter, AnthropicError
from zcoder.services.llm.gemini_adapter import GeminiAdapter, GeminiError
from zcoder.services.llm.ollama_adapter import OllamaAdapter, OllamaError
from zcoder.services.llm.types import GenerateOptions


class TestAnthropicAdapter:
    """Tests for Anthropic provider adapter."""

    def test_constructor_with_api_key(self):
        adapter = AnthropicAdapter(api_key="test-key-123")
        assert adapter.api_key == "test-key-123"
        assert adapter.provider_name == "anthropic"
        assert adapter.base_url == "https://api.anthropic.com/v1"
        assert adapter.timeout == 60.0

    def test_constructor_with_env_key(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")
        adapter = AnthropicAdapter()
        assert adapter.api_key == "env-key"

    def test_constructor_missing_key_raises(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(AnthropicError, match="API key is required"):
            AnthropicAdapter()

    def test_constructor_custom_base_url(self):
        adapter = AnthropicAdapter(api_key="key", base_url="https://custom.anthropic.com")
        assert adapter.base_url == "https://custom.anthropic.com"

    def test_constructor_base_url_trailing_slash_stripped(self):
        adapter = AnthropicAdapter(api_key="key", base_url="https://api.anthropic.com/v1/")
        assert adapter.base_url == "https://api.anthropic.com/v1"

    def test_build_payload_basic(self):
        adapter = AnthropicAdapter(api_key="key")
        options = GenerateOptions(
            model="claude-3-opus",
            messages=[{"role": "user", "content": "Hello"}],
        )
        payload = adapter._build_payload(options)
        assert payload["model"] == "claude-3-opus"
        assert payload["messages"] == [{"role": "user", "content": "Hello"}]
        assert payload["stream"] is False

    def test_build_payload_with_system(self):
        adapter = AnthropicAdapter(api_key="key")
        options = GenerateOptions(
            model="claude-3-opus",
            messages=[{"role": "user", "content": "Hello"}],
            system="You are helpful",
        )
        payload = adapter._build_payload(options)
        assert payload["system"] == "You are helpful"
        assert payload["messages"] == [{"role": "user", "content": "Hello"}]

    def test_build_payload_system_in_messages(self):
        adapter = AnthropicAdapter(api_key="key")
        options = GenerateOptions(
            model="claude-3-opus",
            messages=[
                {"role": "system", "content": "System instruction"},
                {"role": "user", "content": "Hello"},
            ],
        )
        payload = adapter._build_payload(options)
        assert payload["system"] == "System instruction"
        assert len(payload["messages"]) == 1
        assert payload["messages"][0]["role"] == "user"


class TestGeminiAdapter:
    """Tests for Gemini provider adapter."""

    def test_constructor_with_api_key(self):
        adapter = GeminiAdapter(api_key="test-key-123")
        assert adapter.api_key == "test-key-123"
        assert adapter.provider_name == "gemini"
        assert "generativelanguage.googleapis.com" in adapter.base_url
        assert adapter.timeout == 60.0

    def test_constructor_with_env_key(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "env-key")
        adapter = GeminiAdapter()
        assert adapter.api_key == "env-key"

    def test_constructor_missing_key_raises(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        with pytest.raises(GeminiError, match="API key is required"):
            GeminiAdapter()

    def test_constructor_custom_base_url(self):
        adapter = GeminiAdapter(api_key="key", base_url="https://custom.googleapis.com")
        assert adapter.base_url == "https://custom.googleapis.com"

    def test_build_payload_basic(self):
        adapter = GeminiAdapter(api_key="key")
        options = GenerateOptions(
            model="gemini-1.5-pro",
            messages=[{"role": "user", "content": "Hello"}],
        )
        payload = adapter._build_payload(options)
        assert "contents" in payload
        assert payload["contents"][0]["role"] == "user"
        assert payload["contents"][0]["parts"][0]["text"] == "Hello"

    def test_build_payload_with_system(self):
        adapter = GeminiAdapter(api_key="key")
        options = GenerateOptions(
            model="gemini-1.5-pro",
            messages=[{"role": "user", "content": "Hello"}],
            system="You are helpful",
        )
        payload = adapter._build_payload(options)
        assert "systemInstruction" in payload
        assert payload["systemInstruction"]["parts"][0]["text"] == "You are helpful"

    def test_model_endpoint_strips_prefix(self):
        adapter = GeminiAdapter(api_key="key")
        url = adapter._model_endpoint("models/gemini-1.5-pro")
        assert "gemini-1.5-pro:generateContent" in url
        # Should not have double "models/models/" prefix
        assert "models/models/" not in url

    def test_model_endpoint_keeps_name(self):
        adapter = GeminiAdapter(api_key="key")
        url = adapter._model_endpoint("gemini-1.5-pro")
        assert "gemini-1.5-pro:generateContent" in url


class TestOllamaAdapter:
    """Tests for Ollama provider adapter."""

    def test_constructor_defaults(self):
        adapter = OllamaAdapter()
        assert adapter.provider_name == "ollama"
        assert adapter.base_url == "http://127.0.0.1:11434"
        assert adapter.timeout == 60.0
        # Ollama doesn't require an API key
        assert adapter.api_key == ""

    def test_constructor_with_api_key(self):
        adapter = OllamaAdapter(api_key="test-key")
        assert adapter.api_key == "test-key"

    def test_constructor_custom_base_url(self):
        adapter = OllamaAdapter(base_url="http://127.0.0.1:11435")
        assert adapter.base_url == "http://127.0.0.1:11435"

    def test_constructor_base_url_trailing_slash_stripped(self):
        adapter = OllamaAdapter(base_url="http://127.0.0.1:11434/")
        assert adapter.base_url == "http://127.0.0.1:11434"

    def test_build_payload_basic(self):
        adapter = OllamaAdapter()
        options = GenerateOptions(
            model="llama3.1",
            messages=[{"role": "user", "content": "Hello"}],
        )
        payload = adapter._build_payload(options)
        assert payload["model"] == "llama3.1"
        assert payload["messages"] == [{"role": "user", "content": "Hello"}]
        assert payload["stream"] is False

    def test_build_payload_with_max_tokens(self):
        adapter = OllamaAdapter()
        options = GenerateOptions(
            model="llama3.1",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=512,
        )
        payload = adapter._build_payload(options)
        assert payload["num_predict"] == 512  # Ollama uses num_predict, not max_tokens


class TestAdapterErrorTypes:
    """Tests that provider errors have correct error codes."""

    def test_anthropic_error_code(self):
        err = AnthropicError("test", provider="anthropic")
        assert err.error_code == "ANTHROPIC_ERROR"
        assert err.provider == "anthropic"

    def test_gemini_error_code(self):
        err = GeminiError("test", provider="gemini")
        assert err.error_code == "GEMINI_ERROR"
        assert err.provider == "gemini"

    def test_ollama_error_code(self):
        err = OllamaError("test", provider="ollama")
        assert err.error_code == "OLLAMA_ERROR"
        assert err.provider == "ollama"
