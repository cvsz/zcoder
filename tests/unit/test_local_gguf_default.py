"""Local GGUF integration: CLI defaults and no Anthropic network fallback."""

import json
from unittest.mock import patch

from zcoder.main import _api_key, build_parser
from zcoder.services.coder import Coder


def test_default_prompt_provider_is_local(monkeypatch):
    monkeypatch.delenv("ZCODER_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    args = build_parser().parse_args(["--agent", "security_auditor", "-p", "review code"])
    assert args.provider is None
    assert _api_key(args) == ""


def test_legacy_stream_requires_anthropic_key_even_with_local_default(monkeypatch):
    monkeypatch.delenv("ZCODER_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    args = build_parser().parse_args(["--stream", "-p", "hello"])

    with patch("sys.exit", side_effect=SystemExit) as exit_call:
        try:
            _api_key(args)
        except SystemExit:
            pass
    exit_call.assert_called_once_with(1)


def test_legacy_stream_preserves_explicit_anthropic_key(monkeypatch):
    monkeypatch.delenv("ZCODER_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    args = build_parser().parse_args(["--stream", "--api-key", "explicit-key", "-p", "hello"])

    assert _api_key(args) == "explicit-key"


def test_local_chat_calls_only_loopback(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "should-not-be-used")
    c = Coder(provider="llama_cpp", base_url="http://127.0.0.1:8080", model="local")
    assert c.api_key == ""
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

    with patch("zcoder.services.coder.safe_local_urlopen", side_effect=fake_open):
        assert c.generate("scan") == "local answer"
    assert len(seen) == 1


def test_explicit_anthropic_rejected_without_network():
    c = Coder(provider="anthropic", api_key="unused", model="claude-sonnet-5")
    with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")) as mock:
        assert "disabled" in c.generate("hi")
        mock.assert_not_called()


def test_non_loopback_endpoint_rejected_without_network():
    c = Coder(provider="llama_cpp", base_url="https://api.anthropic.com", model="local")
    with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")) as mock:
        assert "[ERROR]" in c.generate("hi")
        mock.assert_not_called()
