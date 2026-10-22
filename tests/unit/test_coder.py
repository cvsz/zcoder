"""Local Coder transport tests; remote provider calls are forbidden."""

import json
from unittest.mock import patch

from zcoder.services.coder import Coder


def test_default_provider_uses_loopback_without_api_key(monkeypatch):
    monkeypatch.delenv("ZCODER_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    coder = Coder()
    assert coder.provider == "llama_cpp"
    assert coder.api_key == ""


def test_local_generate_sends_prompt_to_loopback_only():
    coder = Coder(provider="llama_cpp", base_url="http://127.0.0.1:8080", model="local")
    seen = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, *_args):
            return json.dumps({"choices": [{"message": {"content": "local answer"}}]}).encode()

    def fake_open(request, timeout):
        seen.append(request.full_url)
        assert request.full_url == "http://127.0.0.1:8080/v1/chat/completions"
        assert "x-api-key" not in {name.lower() for name, _value in request.header_items()}
        return Response()

    with patch("urllib.request.urlopen", side_effect=fake_open):
        assert coder.generate("hello") == "local answer"
    assert seen == ["http://127.0.0.1:8080/v1/chat/completions"]


def test_explicit_anthropic_provider_is_blocked_without_network():
    coder = Coder(provider="anthropic", api_key="unused", model="claude-sonnet-5")
    with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")) as urlopen:
        result = coder.generate("hello")
    assert "Anthropic calls are disabled" in result
    urlopen.assert_not_called()


def test_non_loopback_endpoint_is_blocked_without_network():
    coder = Coder(provider="llama_cpp", base_url="https://api.anthropic.com", model="local")
    with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")) as urlopen:
        result = coder.generate("hello")
    assert "loopback" in result
    urlopen.assert_not_called()


def test_local_server_failure_returns_safe_error():
    coder = Coder(provider="llama_cpp", base_url="http://127.0.0.1:8080", model="local")
    with patch("urllib.request.urlopen", side_effect=OSError("offline")):
        result = coder.generate("hello")
    assert result.startswith("[ERROR] Local llama.cpp inference failed:")
