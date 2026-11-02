import json

import pytest

from zgpu.dashboard.server import DashboardBackend
from zgpu.llm.openai_compat import CompletionRequestError
from zgpu.llm.tool_calls import ToolCallError, ZGPUToolRegistry


def test_tool_registry_validates_schema_and_bounds_results():
    registry = ZGPUToolRegistry()
    registry.register(
        "zgpu_echo",
        "Return bounded input.",
        {
            "type": "object",
            "properties": {"text": {"type": "string", "maxLength": 8}},
            "required": ["text"],
            "additionalProperties": False,
        },
        lambda text: {"text": text},
    )

    assert json.loads(registry.execute("zgpu_echo", '{"text":"hello"}')) == {"text": "hello"}
    for arguments in (
        '{"text":"too long input"}',
        '{"text":"ok","extra":true}',
        '{"text":"first","text":"second"}',
        "[]",
    ):
        with pytest.raises(ToolCallError):
            registry.execute("zgpu_echo", arguments)
    with pytest.raises(ToolCallError, match="unknown"):
        registry.execute("run_shell", "{}")


def test_remote_tool_completion_runs_allowlisted_tool_and_returns_final_answer():
    backend = DashboardBackend.__new__(DashboardBackend)
    backend.chat_tools = ZGPUToolRegistry()
    backend.chat_tools.register(
        "zgpu_echo",
        "Return bounded input.",
        {
            "type": "object",
            "properties": {"text": {"type": "string", "maxLength": 8}},
            "required": ["text"],
            "additionalProperties": False,
        },
        lambda text: {"text": text},
    )
    calls = []

    class FakeChatAPI:
        def create_completion(self, payload):
            calls.append(payload)
            if len(calls) == 1:
                return {
                    "id": "call-1",
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "tool_calls": [
                                    {
                                        "id": "tool-1",
                                        "type": "function",
                                        "function": {"name": "zgpu_echo", "arguments": '{"text":"hello"}'},
                                    }
                                ],
                            }
                        }
                    ],
                }
            assert payload["messages"][-1] == {
                "role": "tool",
                "tool_call_id": "tool-1",
                "content": '{"text":"hello"}',
            }
            return {"id": "final", "choices": [{"message": {"role": "assistant", "content": "Done"}}]}

    backend.chat_api = FakeChatAPI()
    result = backend.create_tool_completion(
        {"model": "zgpu-remote-test", "messages": [{"role": "user", "content": "Say hello"}], "stream": True}
    )

    assert result["choices"][0]["message"]["content"] == "Done"
    assert calls[0]["stream"] is False
    assert calls[0]["tool_choice"] == "auto"
    assert calls[0]["parallel_tool_calls"] is False


@pytest.mark.parametrize(
    "payload",
    [
        {"model": "zgpu-local-test", "messages": [{"role": "user", "content": "run"}]},
        {
            "model": "zgpu-remote-test",
            "messages": [{"role": "user", "content": "run"}],
            "tools": [{"type": "function"}],
        },
    ],
)
def test_tool_completion_rejects_local_models_and_client_tool_definitions(payload):
    backend = DashboardBackend.__new__(DashboardBackend)
    backend.chat_tools = ZGPUToolRegistry()
    with pytest.raises(CompletionRequestError):
        backend.create_tool_completion(payload)
