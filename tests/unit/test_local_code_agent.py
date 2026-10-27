import json

from zcoder.agent.capabilities.code import CodeAgent, CodeSession


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def test_code_agent_uses_loopback_tools_without_provider_credentials(monkeypatch):
    monkeypatch.setenv("ZCODER_BASE_URL", "http://127.0.0.1:8080/v1")
    response = {
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "content": "I will inspect the file.",
                    "tool_calls": [
                        {
                            "id": "call-read-1",
                            "type": "function",
                            "function": {"name": "Read", "arguments": '{"path":"README.md"}'},
                        }
                    ],
                },
            }
        ],
        "usage": {"prompt_tokens": 120, "completion_tokens": 16},
    }
    captured = {}

    def fake_open(_opener, request, timeout=0):
        captured["url"] = request.full_url
        captured["headers"] = request.headers
        captured["payload"] = json.loads(request.data)
        captured["timeout"] = timeout
        return FakeResponse(response)

    monkeypatch.setattr("urllib.request.OpenerDirector.open", fake_open)
    result = CodeAgent(api_key="must-not-be-used", model="qwen-local")._call(
        {
            "model": "qwen-local",
            "max_tokens": 512,
            "system": "Follow the safety policy.",
            "messages": [{"role": "user", "content": "Read README.md"}],
            "tools": [
                {
                    "name": "Read",
                    "description": "Read a file",
                    "input_schema": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                }
            ],
        }
    )

    assert captured["url"] == "http://127.0.0.1:8080/v1/chat/completions"
    assert "x-api-key" not in {key.lower() for key in captured["headers"]}
    assert "authorization" not in {key.lower() for key in captured["headers"]}
    assert captured["payload"]["messages"][0] == {
        "role": "system",
        "content": "Follow the safety policy.",
    }
    assert captured["payload"]["tools"][0]["function"]["name"] == "Read"
    assert result["stop_reason"] == "tool_use"
    assert result["content"] == [
        {"type": "text", "text": "I will inspect the file."},
        {"type": "tool_use", "id": "call-read-1", "name": "Read", "input": {"path": "README.md"}},
    ]
    assert result["usage"] == {"input_tokens": 120, "output_tokens": 16, "cost_usd": 0.0}


def test_code_agent_rejects_non_loopback_base_url(monkeypatch):
    monkeypatch.setenv("ZCODER_BASE_URL", "https://model.example/v1")

    result = CodeAgent(api_key="ignored", model="qwen-local")._post(
        {"messages": [{"role": "user", "content": "hello"}]}
    )

    assert "loopback" in result["error"]


def test_local_agent_recognizes_exact_allowlisted_json_tool_envelope():
    tools = [
        {"name": "Read"},
        {"name": "Write"},
    ]

    calls = CodeAgent._tool_calls_from_json(
        '```json\n{"name":"Read","arguments":{"path":"README.md"}}\n```', tools
    )

    assert len(calls) == 1
    assert calls[0]["type"] == "function"
    assert calls[0]["function"]["name"] == "Read"
    assert json.loads(calls[0]["function"]["arguments"]) == {"path": "README.md"}
    assert CodeAgent._tool_calls_from_json('{"name":"Bash","arguments":{"command":"id"}}', tools) == []
    assert CodeAgent._tool_calls_from_json('{"name":"Read","arguments":"bad"}', tools) == []


def test_local_agent_history_preserves_tool_call_protocol():
    assistant_tool_calls = [
        {
            "id": "call-read-1",
            "type": "function",
            "function": {"name": "Read", "arguments": '{"path":"README.md"}'},
        }
    ]
    session = CodeSession(cwd=".", model="qwen-local")
    session.add_turn("user", "Read README.md")
    session.add_turn("assistant", "")
    session.turns[-1]["local_tool_calls"] = assistant_tool_calls
    session.add_turn(
        "user",
        json.dumps([{"type": "tool_result", "tool_use_id": "call-read-1", "content": "file contents"}]),
    )

    messages = CodeAgent._local_messages(session.messages())

    assert messages == [
        {"role": "user", "content": "Read README.md"},
        {"role": "assistant", "content": None, "tool_calls": assistant_tool_calls},
        {"role": "tool", "tool_call_id": "call-read-1", "content": "file contents"},
    ]


def test_local_agent_session_records_zero_cost_usage():
    session = CodeSession(cwd=".", model="qwen-local")

    session.add_turn("assistant", "done", {"input_tokens": 300, "output_tokens": 20, "cost_usd": 0.0})

    assert session.input_tokens == 300
    assert session.output_tokens == 20
    assert session.cost_usd == 0.0
