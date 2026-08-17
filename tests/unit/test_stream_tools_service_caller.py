from zcoder.claude.capabilities.stream import cmd_stream_tools
from zcoder.services.messaging_service import MessagingTurnResult


def test_cmd_stream_tools_delegates_once_and_preserves_cli_contract(monkeypatch, capsys):
    calls = []
    tool_call = {
        "name": "write_file",
        "id": "tool_1",
        "input_raw": '{"path":"README.md"}',
        "input": {"path": "README.md"},
    }

    def fake_run_claude_messaging_turn_once(**kwargs):
        calls.append(kwargs)
        return MessagingTurnResult(
            text="done",
            tool_calls=(tool_call,),
            stop_reason="tool_use",
            stop_details=None,
        )

    monkeypatch.setattr(
        "zcoder.services.claude_messaging_adapter.run_claude_messaging_turn_once",
        fake_run_claude_messaging_turn_once,
    )

    tools = [{"name": "write_file", "input_schema": {"type": "object"}}]
    result = cmd_stream_tools(
        "update docs",
        tools,
        "sk-test",
        "claude-sonnet-5",
        system="be precise",
    )

    assert calls == [
        {
            "api_key": "sk-test",
            "prompt": "update docs",
            "model": "claude-sonnet-5",
            "tools": tools,
            "system": "be precise",
            "verbose": True,
        }
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
        "zcoder.services.claude_messaging_adapter.run_claude_messaging_turn_once",
        lambda **kwargs: MessagingTurnResult(
            text="",
            tool_calls=(tool_call,),
            stop_reason="tool_use",
        ),
    )

    result = cmd_stream_tools("inspect", [], "sk-test", "claude-sonnet-5")

    assert executed == []
    assert result["tool_calls"] == [tool_call]
