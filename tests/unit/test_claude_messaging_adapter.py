from zcoder.services.claude_messaging_adapter import run_claude_messaging_turn_once


class FakeCapability:
    def __init__(self, *, response):
        self.response = response
        self.calls = []

    def stream_with_tools(self, prompt, tools, system=None, **kwargs):
        self.calls.append((prompt, tools, system, kwargs))
        return self.response


def test_claude_messaging_adapter_constructs_once_and_delegates_once():
    constructed = []
    capability = FakeCapability(
        response={
            "text": "done",
            "tool_calls": [],
            "stop_reason": "end_turn",
            "stop_details": None,
        }
    )

    def factory(**kwargs):
        constructed.append(kwargs)
        return capability

    result = run_claude_messaging_turn_once(
        "secret",
        "hello",
        model="claude-test",
        max_tokens=123,
        tools=[{"name": "read_file"}],
        system="system",
        capability_factory=factory,
    )

    assert constructed == [
        {"api_key": "secret", "model": "claude-test", "max_tokens": 123}
    ]
    assert capability.calls == [
        ("hello", [{"name": "read_file"}], "system", {"verbose": False})
    ]
    assert result.text == "done"
    assert result.stop_reason == "end_turn"


def test_claude_messaging_adapter_returns_tool_calls_without_executing_them():
    executed = []
    tool_call = {
        "name": "dangerous",
        "id": "tool_1",
        "input_raw": '{"command":"echo no"}',
        "input": {"command": "echo no"},
    }
    capability = FakeCapability(
        response={
            "text": "",
            "tool_calls": [tool_call],
            "stop_reason": "tool_use",
        }
    )

    result = run_claude_messaging_turn_once(
        "secret",
        "request",
        capability_factory=lambda **_kwargs: capability,
    )

    assert executed == []
    assert result.tool_calls == (tool_call,)
    assert len(capability.calls) == 1
