"""Upgrade-56 / parity W1 — real ``/compact`` and ``/context`` budget bars.

Before this slice the code-agent ``/compact`` command was an explicit
stub ("Stub: in real SDK this compacts via PreCompact hook") and
``/context`` did not exist. These tests pin the real implementations:
the CodeAgent.compact() summarization round-trip (fail-closed, audited,
hook-fired), the context-budget estimate math, the report renderer, and
the cmd_code_slash wiring — all offline via a stubbed ``_call``.
"""

import json
import types

import pytest

from zcoder.agent.capabilities.code import (
    BUILTIN_SLASH_COMMANDS,
    SLASH_COMMAND_ALIASES,
    CodeAgent,
    CodeSession,
    cmd_code_slash,
    estimate_tokens,
    render_context_report,
)
from zcoder.agent.optimization.cost import LEGACY_CONTEXT_WINDOW, context_window
from zcoder.core.exceptions import ZCoderError


def _seed_long_session(n=3, content_len=20000):
    s = CodeSession(model="claude-sonnet-5")
    s.add_turn("user", "long task " * (content_len // 10))
    for i in range(n):
        s.add_turn("assistant", f"step {i} okay " * (content_len // 10))
        s.add_turn("user", f"continue {i} " * (content_len // 12))
    return s


def _agent_with_stub_call(text=None, raise_exc=None):
    calls = []
    agent = CodeAgent(api_key="test-key", model="claude-sonnet-5")

    def stub(payload, betas=None):
        calls.append(payload)
        if raise_exc:
            raise raise_exc
        return {"content": [{"type": "text", "text": text}]}

    agent._call = stub
    return agent, calls


# ---------------------------------------------------------------------------
# estimate_tokens / window map
# ---------------------------------------------------------------------------


def test_estimate_tokens_rounds_up():
    assert estimate_tokens("") == 1
    assert estimate_tokens("ab") == 1
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcde") == 2


def test_context_window_known_and_fallback():
    assert context_window("claude-sonnet-5") == 1_000_000
    assert context_window("claude-opus-5") == 1_000_000
    assert context_window("definitely-not-a-model") == LEGACY_CONTEXT_WINDOW == 200_000


# ---------------------------------------------------------------------------
# CodeSession.context_estimate
# ---------------------------------------------------------------------------


def test_context_estimate_math():
    s = CodeSession(model="claude-sonnet-5", system_prompt="SYS")
    s.add_turn("user", "U" * 400)
    tool_defs = [{"name": "Read", "input_schema": {}}]
    rep = s.context_estimate(tool_defs)

    assert rep["window"] == 1_000_000
    assert rep["conversation"] == estimate_tokens("U" * 400)
    assert rep["system"] == estimate_tokens("SYS")
    assert rep["tools"] == estimate_tokens(json.dumps(tool_defs))
    assert rep["used"] == rep["conversation"] + rep["system"] + rep["tools"]
    assert rep["free"] == rep["window"] - rep["used"]


# ---------------------------------------------------------------------------
# CodeAgent.compact — fail-closed summarization
# ---------------------------------------------------------------------------


def test_compact_short_session_is_noop():
    s = CodeSession()
    s.add_turn("user", "only one turn")
    agent, calls = _agent_with_stub_call("SHOULD NOT RUN")
    before = list(s.turns)

    assert agent.compact(s) is None
    assert calls == []  # no API call for nothing-to-do
    assert s.turns == before


def test_compact_replaces_turns_and_audits():
    s = _seed_long_session()
    before_est = s.context_estimate()["conversation"]
    agent, calls = _agent_with_stub_call("summary text about the task")

    summary = agent.compact(s)

    assert summary == "summary text about the task"
    assert len(calls) == 1  # exactly one summarization call
    assert "<transcript>" in calls[0]["messages"][0]["content"]
    assert len(s.turns) == 1
    assert "CONVERSATION COMPACTED" in s.turns[0]["content"]
    assert "summary text about the task" in s.turns[0]["content"]

    audit = s.audit_events[-1]
    assert audit["event"] == "compact"
    assert audit["detail"]["before_est_tokens"] == before_est
    # Honest budgets: the summary must estimate smaller than the transcript.
    assert audit["detail"]["after_est_tokens"] < before_est


def test_compact_empty_summary_fails_closed():
    s = _seed_long_session()
    turns_before = len(s.turns)
    agent, _ = _agent_with_stub_call("")

    with pytest.raises(ZCoderError, match="left untouched"):
        agent.compact(s)
    assert len(s.turns) == turns_before  # transcript untouched


def test_compact_api_failure_leaves_session_intact():
    s = _seed_long_session()
    turns_before = len(s.turns)
    agent, _ = _agent_with_stub_call(raise_exc=ConnectionError("boom"))

    with pytest.raises(ConnectionError):
        agent.compact(s)
    assert len(s.turns) == turns_before


def test_compact_fires_precompact_hook():
    s = _seed_long_session()
    fired = []
    hooks = types.SimpleNamespace(
        fire=lambda event, payload, fail_closed=False: fired.append((event, payload))
    )
    agent, _ = _agent_with_stub_call("ok")

    agent.compact(s, hooks=hooks)

    assert fired and fired[0][0] == "PreCompact"
    assert fired[0][1]["turns"] == 7
    assert fired[0][1]["session_id"] == s.id


# ---------------------------------------------------------------------------
# /context rendering and slash wiring
# ---------------------------------------------------------------------------


def test_builtin_table_has_context():
    assert "/context" in BUILTIN_SLASH_COMMANDS
    assert SLASH_COMMAND_ALIASES["context"] == "/context"


def test_render_context_report_shape():
    rep = _seed_long_session().context_estimate()
    out = render_context_report(rep, model="claude-sonnet-5", live=True)
    assert "Context budget (claude-sonnet-5)" in out
    for label in ("system", "tools", "conversation", "free", "used"):
        assert label in out
    assert "█" in out and "░" in out
    assert "% of window" in out


def test_render_marks_scratch_estimate_only():
    rep = _seed_long_session().context_estimate()
    out = render_context_report(rep, model="x", live=False)
    assert "estimates only" in out


def test_slash_context_without_session(capsys, tmp_path):
    cmd_code_slash("context", api_key="k", model="claude-sonnet-5", cwd=str(tmp_path))
    out = capsys.readouterr().out
    assert "estimates only" in out
    assert "conversation" in out


def test_slash_compact_requires_session(capsys, tmp_path):
    cmd_code_slash("compact", api_key="k", model="claude-sonnet-5", cwd=str(tmp_path))
    assert "needs a live session" in capsys.readouterr().out


def test_slash_compact_end_to_end(tmp_path, monkeypatch, capsys):
    session = _seed_long_session(n=1, content_len=4000)
    session.cwd = str(tmp_path)

    def fake_call(self, payload, betas=None):
        return {"content": [{"type": "text", "text": "e2e summary"}]}

    monkeypatch.setattr(CodeAgent, "_call", fake_call)
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("zcoder.agent.capabilities.code.SESSIONS_DIR", sessions_dir)

    cmd_code_slash("compact", api_key="k", model="claude-sonnet-5", cwd=str(tmp_path), session=session)

    out = capsys.readouterr().out
    assert "Compacted" in out
    assert len(session.turns) == 1 and "e2e summary" in session.turns[0]["content"]
    # The compacted state is persisted for resume under the same session ID.
    assert (tmp_path / "sessions" / f"{session.id}.json").exists()
