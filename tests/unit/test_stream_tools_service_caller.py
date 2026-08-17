from zcoder.claude.capabilities.stream import cmd_stream_tools
from zcoder.services.messaging_service import MessagingTurnResult


def test_cmd_stream_tools_delegates_once_and_preserves_cli_contract(monkeypatch, capsys):
    constructions = []
    calls = []
    capability = object()
    tool_call = {
        "name": "write_file",
        "id": "tool_1",
        "input_raw": '{"path":"README.md"}',
        "input": {"path": "README.md"},
    }

    def fake_stream_coder(**kwargs):
        constructions.append(kwargs)
        return capability

    def fake_run_messaging_turn_once(injected_capability, prompt, **kwargs):
        calls.append((injected_capability, prompt, kwargs))
        return MessagingTurnResult(
            text="done",
            tool_calls=(tool_call,),
            stop_reason="tool_use",
            stop_details=None,
        )

    monkeypatch.setattr(
        "zcoder.claude.capabilities.stream.StreamCoder",
        fake_stream_coder,
    )
    monkeypatch.setattr(
        "zcoder.services.messaging_service.run_messaging_turn_once",
        fake_run_messaging_turn_once,
    )

    tools = [{"name": "write_file", "input_schema": {"type": "object"}}]
    result = cmd_stream_tools(
        "update docs",
        tools,
        "sk-test",
        "claude-sonnet-5",
        system="be precise",
    )

    assert constructions == [{"api_key": "sk-test", "model": "claude-sonnet-5"}]
    assert calls == [
        (
            capability,
            "update docs",
            {
                "tools": tools,
                "system": "be precise",
                "verbose": True,
            },
        )
    ]
    assert result == {
        "text": "done",
        "tool_calls": [tool_call],
        "stop_reason": "tool_use",
        "stop_details": None,
    }

    out = capsys.readouterr().out
    assert "Streaming with fine-grained tool input" in out
    assert "1 tool call(s)" in out
    assert "write_file: {'path': 'README.md'}" in out


def test_cmd_stream_tools_does_not_execute_returned_tool_calls(monkeypatch):
    executed = []

    def dangerous_tool():
        executed.append(True)

    tool_call = {
        "name": "dangerous_tool",
        "id": "tool_2",
        "input_raw": "{}",
        "input": {},
        "callable": dangerous_tool,
    }

    monkeypatch.setattr(
        "zcoder.claude.capabilities.stream.StreamCoder",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        "zcoder.services.messaging_service.run_messaging_turn_once",
        lambda capability, prompt, **kwargs: MessagingTurnResult(
            text="",
            tool_calls=(tool_call,),
            stop_reason="tool_use",
        ),
    )

    result = cmd_stream_tools("inspect", [], "sk-test", "claude-sonnet-5")

    assert executed == []
    assert result["tool_calls"] == [tool_call]
