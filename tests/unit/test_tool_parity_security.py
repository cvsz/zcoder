"""Regression tests for Slice E.13 — built-in tool parity security boundaries."""

from unittest.mock import MagicMock, patch

from zcoder.claude.capabilities.code import CodeAgent, CodeSession


def _make_agent():
    agent = CodeAgent.__new__(CodeAgent)
    agent.model = "test-model"
    agent.max_tokens = 1024
    agent.api_key = "test"
    agent._post = MagicMock(
        return_value={
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": "done"}],
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }
    )
    return agent


def test_unknown_tool_name_rejected():
    agent = _make_agent()
    session = CodeSession(cwd=".")
    session.model = "test-model"
    content = [
        {"type": "tool_use", "name": "FakeTool", "id": "1", "input": {}},
        {"type": "text", "text": "done"},
    ]
    with patch.object(
        agent,
        "_post",
        return_value={
            "stop_reason": "tool_use",
            "content": content,
            "usage": {"input_tokens": 100, "output_tokens": 50},
        },
    ):
        agent.query("task", session, tools="all", permission="acceptEdits")
    assert any(tc["name"] == "FakeTool" and not tc["approved"] for tc in session.tool_calls)
    assert session.tool_calls[-1]["result"].startswith("[DENIED] unknown tool FakeTool")


def test_known_tool_accepted():
    agent = _make_agent()
    session = CodeSession(cwd=".")
    session.model = "test-model"
    with patch.object(
        agent,
        "_post",
        side_effect=[
            {
                "stop_reason": "tool_use",
                "content": [{"type": "tool_use", "name": "Read", "id": "1", "input": {"path": "foo"}}],
                "usage": {"input_tokens": 100, "output_tokens": 50},
            },
            {
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "done"}],
                "usage": {"input_tokens": 100, "output_tokens": 50},
            },
        ],
    ):
        result = agent.query(
            "task", session, tools="all", permission="acceptEdits", can_use_tool=lambda n, i: True
        )
    assert "done" in result
    assert not any(tc["name"] == "Read" and not tc["approved"] for tc in session.tool_calls)


def test_mcp_tool_prefix_accepted():
    agent = _make_agent()
    session = CodeSession(cwd=".")
    session.model = "test-model"
    with patch.object(
        agent,
        "_post",
        side_effect=[
            {
                "stop_reason": "tool_use",
                "content": [{"type": "tool_use", "name": "mcp__server__tool", "id": "1", "input": {}}],
                "usage": {"input_tokens": 100, "output_tokens": 50},
            },
            {
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "done"}],
                "usage": {"input_tokens": 100, "output_tokens": 50},
            },
        ],
    ):
        result = agent.query(
            "task", session, tools="all", permission="acceptEdits", can_use_tool=lambda n, i: True
        )
    assert "done" in result
    assert not any(tc["name"] == "mcp__server__tool" and not tc["approved"] for tc in session.tool_calls)
