from zcoder.services.messaging_service import run_messaging_turn_once


class FakeCapability:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def stream_with_tools(self, prompt, tools, system=None, **kwargs):
        self.calls.append((prompt, tools, system, kwargs))
        return self.response


def test_messaging_turn_delegates_exactly_once_and_preserves_result():
    raw_tool_call = {
        "name": "write_file",
        "id": "tool_1",
        "input_raw": '{"path":',
        "input": None,
    }
    capability = FakeCapability(
        {
            "text": "partial",
            "tool_calls": [raw_tool_call],
            "stop_reason": "max_tokens",
            "stop_details": {"reason": "bounded"},
        }
    )

    result = run_messaging_turn_once(
        capability,
        "do work",
        tools=[{"name": "write_file"}],
        system="system",
    )

    assert len(capability.calls) == 1
    assert capability.calls[0] == (
        "do work",
        [{"name": "write_file"}],
        "system",
        {"verbose": False},
    )
    assert result.text == "partial"
    assert result.tool_calls == (raw_tool_call,)
    assert result.stop_reason == "max_tokens"
    assert result.stop_details == {"reason": "bounded"}


def test_messaging_turn_forwards_explicit_verbose_mode_without_extra_calls():
    capability = FakeCapability({"text": "hello", "tool_calls": [], "stop_reason": "end_turn"})

    result = run_messaging_turn_once(capability, "request", verbose=True)

    assert capability.calls == [("request", [], None, {"verbose": True})]
    assert result.text == "hello"


def test_messaging_turn_does_not_execute_returned_tool_calls():
    executed = []
    tool_call = {"name": "dangerous", "input": {"command": "echo no"}}
    capability = FakeCapability({"text": "", "tool_calls": [tool_call], "stop_reason": "tool_use"})

    result = run_messaging_turn_once(capability, "request")

    assert len(capability.calls) == 1
    assert executed == []
    assert result.tool_calls == (tool_call,)
