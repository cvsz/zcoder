from types import SimpleNamespace

from zcoder.claude.capabilities.stream import StreamCoder


class _FakeStream:
    def __enter__(self):
        return iter(
            [
                SimpleNamespace(
                    type="content_block_delta",
                    delta=SimpleNamespace(type="text_delta", text="hello"),
                ),
                SimpleNamespace(
                    type="message_delta",
                    delta=SimpleNamespace(stop_reason="end_turn", stop_details=None),
                ),
            ]
        )

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeMessages:
    def stream(self, **kwargs):
        return _FakeStream()


class _FakeClient:
    messages = _FakeMessages()


def _coder():
    coder = object.__new__(StreamCoder)
    coder.client = _FakeClient()
    coder.model = "claude-sonnet-5"
    coder.max_tokens = 32
    return coder


def test_stream_with_tools_verbose_false_is_quiet(capsys):
    result = _coder().stream_with_tools("prompt", [], verbose=False)

    assert result["text"] == "hello"
    assert result["stop_reason"] == "end_turn"
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_stream_with_tools_verbose_true_preserves_cli_output(capsys):
    result = _coder().stream_with_tools("prompt", [], verbose=True)

    assert result["text"] == "hello"
    captured = capsys.readouterr()
    assert captured.out == "hello\n"
    assert captured.err == ""
