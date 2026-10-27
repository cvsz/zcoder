import json

import pytest

from zcoder.agent.capabilities.stream import StreamCoder


class FakeSseResponse:
    def __init__(self, events):
        self.lines = [f"data: {json.dumps(event)}\n".encode() for event in events]
        self.lines.append(b"data: [DONE]\n")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __iter__(self):
        return iter(self.lines)


def test_text_stream_uses_loopback_sse_without_credentials(monkeypatch, capsys):
    monkeypatch.setenv("ZCODER_BASE_URL", "http://127.0.0.1:8080/v1")
    captured = {}

    def fake_open(_opener, request, timeout=0):
        captured["url"] = request.full_url
        captured["headers"] = {key.lower(): value for key, value in request.header_items()}
        captured["payload"] = json.loads(request.data)
        captured["timeout"] = timeout
        return FakeSseResponse(
            [
                {"choices": [{"delta": {"content": "local "}, "finish_reason": None}]},
                {"choices": [{"delta": {"content": "stream"}, "finish_reason": "stop"}]},
                {"usage": {"prompt_tokens": 8, "completion_tokens": 2}},
            ]
        )

    monkeypatch.setattr("urllib.request.OpenerDirector.open", fake_open)
    result = StreamCoder(api_key="must-not-be-used", model="qwen-local").stream("hello", system="Be concise")

    assert result == "local stream"
    assert captured["url"] == "http://127.0.0.1:8080/v1/chat/completions"
    assert "authorization" not in captured["headers"]
    assert "x-api-key" not in captured["headers"]
    assert captured["payload"]["stream"] is True
    assert captured["payload"]["stream_options"] == {"include_usage": True}
    assert captured["payload"]["messages"][0] == {"role": "system", "content": "Be concise"}
    assert captured["timeout"] == 300
    assert "local stream" in capsys.readouterr().out


def test_text_stream_rejects_remote_model_urls(monkeypatch):
    monkeypatch.setenv("ZCODER_BASE_URL", "https://models.example/v1")

    with pytest.raises(ValueError, match="loopback"):
        StreamCoder().stream("hello")


def test_stream_cli_flag_is_local_provider_eligible(monkeypatch, capsys):
    import sys

    from zcoder.agent.capabilities import stream
    from zcoder.main import main

    called = {}
    monkeypatch.setenv("ZCODER_LOCAL_MODE", "1")
    monkeypatch.setattr(sys, "argv", ["zcoder", "--stream", "--prompt", "hello"])
    monkeypatch.setattr(stream, "cmd_stream", lambda *args, **kwargs: called.update(args=args, kwargs=kwargs))

    main()

    assert called["args"][0] == "hello"
    capsys.readouterr()
