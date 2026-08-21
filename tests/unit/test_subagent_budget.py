"""Regression tests for Slice E.11 — subagent budget enforcement."""

from unittest.mock import MagicMock, patch

from zcoder.claude.capabilities.code import CodeAgent, CodeSession


def _make_agent(tool_response="stop"):
    agent = CodeAgent.__new__(CodeAgent)
    agent.model = "test-model"
    agent.max_tokens = 1024
    agent.api_key = "test"
    agent._post = MagicMock(
        return_value={
            "stop_reason": tool_response,
            "content": [{"type": "text", "text": "done"}],
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }
    )
    return agent


def test_subagent_respects_max_turns():
    agent = _make_agent("tool_use")
    session = CodeSession(cwd=".")
    session.model = "test-model"

    with patch.object(
        agent,
        "_post",
        side_effect=[
            {
                "stop_reason": "tool_use",
                "content": [{"type": "tool_use", "name": "Read", "id": "1", "input": {}}],
                "usage": {"input_tokens": 100, "output_tokens": 50},
            },
            {
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "done"}],
                "usage": {"input_tokens": 100, "output_tokens": 50},
            },
        ],
    ):
        result = agent.query("task", session, tools="safe", permission="acceptEdits", max_turns=2)
    assert "done" in result


def test_subagent_stops_on_cost_budget():
    agent = _make_agent("tool_use")
    session = CodeSession(cwd=".")
    session.model = "test-model"
    session.cost_usd = 0.05

    with patch.object(
        agent,
        "_post",
        return_value={
            "stop_reason": "tool_use",
            "content": [{"type": "tool_use", "name": "Read", "id": "1", "input": {}}],
            "usage": {"input_tokens": 100, "output_tokens": 50},
        },
    ):
        result = agent.query(
            "task", session, tools="safe", permission="acceptEdits", max_turns=10, max_cost_usd=0.04
        )
    assert "[budget] cost budget exhausted" in result


def test_subagent_default_no_cost_limit():
    agent = _make_agent("end_turn")
    session = CodeSession(cwd=".")
    session.model = "test-model"
    session.cost_usd = 100.0

    result = agent.query("task", session, tools="safe", permission="acceptEdits")
    assert "budget" not in result
    assert "done" in result
