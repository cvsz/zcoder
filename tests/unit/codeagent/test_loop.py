from __future__ import annotations

import asyncio
import json

import pytest

from tests.unit.codeagent.conftest import collect
from zcoder.agent.codeagent.audit import AuditLog
from zcoder.agent.codeagent.events import (
    Decision,
    ModeChanged,
    Notice,
    TextDelta,
    ToolEnd,
    ToolStart,
    TurnDone,
)
from zcoder.agent.codeagent.hooks import Hooks
from zcoder.agent.codeagent.llm import LLMError
from zcoder.agent.codeagent.permissions import Mode


def kinds(events):
    return [type(e).__name__ for e in events]


def ends(events):
    return [e for e in events if isinstance(e, ToolEnd)]


def done(events):
    return [e for e in events if isinstance(e, TurnDone)][-1].stop_reason


async def test_plain_text_turn_persists_session(make_agent, tmp_path):
    agent = make_agent([{"text": "hello world"}])
    events = await collect(agent, "hi")
    assert "".join(e.text for e in events if isinstance(e, TextDelta)) == "hello world"
    assert done(events) == "end"
    assert [m["role"] for m in agent.messages] == ["user", "assistant"]
    assert agent.usage.requests == 1 and agent.usage.completion_tokens == 5
    assert agent.store.load(agent.session_id)["messages"][0]["content"] == "hi"


async def test_tool_roundtrip_feeds_result_back(make_agent, tmp_path):
    (tmp_path / "a.txt").write_text("alpha\n")
    agent = make_agent([{"calls": [("Read", {"path": "a.txt"})]}, {"text": "it says alpha"}])
    events = await collect(agent, "read it")
    assert ends(events)[0].output.endswith("alpha") and not ends(events)[0].is_error
    second_request = agent.llm.requests[1][0]
    assert second_request[-1]["role"] == "tool" and "alpha" in second_request[-1]["content"]
    assert second_request[0]["role"] == "system" and "Working directory" in second_request[0]["content"]
    assert len(agent.llm.requests[0][1]) == 9  # all tool definitions are offered


async def test_edit_requires_approval_and_applies_when_allowed(make_agent, tmp_path):
    asked = []

    async def ask(req):
        asked.append(req)
        return Decision("allow")

    agent = make_agent(
        [{"calls": [("Write", {"path": "n.py", "content": "x = 1\n"})]}, {"text": "done"}], ask=ask
    )
    events = await collect(agent, "make n.py")
    assert (tmp_path / "n.py").read_text() == "x = 1\n"
    assert asked[0].tool == "Write" and "+x = 1" in asked[0].diff
    assert "Created" in ends(events)[0].output and ends(events)[0].diff


async def test_denied_edit_reports_feedback_and_writes_nothing(make_agent, tmp_path):
    async def ask(req):
        return Decision("deny", "use a different name")

    agent = make_agent([{"calls": [("Write", {"path": "n.py", "content": "x"})]}, {"text": "ok"}], ask=ask)
    events = await collect(agent, "go")
    assert not (tmp_path / "n.py").exists()
    assert ends(events)[0].is_error and "different name" in ends(events)[0].output


async def test_edit_without_prompt_available_fails_closed(make_agent, tmp_path):
    agent = make_agent([{"calls": [("Write", {"path": "n.py", "content": "x"})]}, {"text": "ok"}])
    events = await collect(agent, "go")
    assert not (tmp_path / "n.py").exists()
    assert "needs user approval" in ends(events)[0].output


async def test_ask_callback_crash_fails_closed(make_agent, tmp_path):
    async def ask(req):
        raise ConnectionResetError("socket closed")

    agent = make_agent([{"calls": [("Write", {"path": "n.py", "content": "x"})]}, {"text": "ok"}], ask=ask)
    events = await collect(agent, "go")
    assert not (tmp_path / "n.py").exists() and "not run" in ends(events)[0].output


async def test_allow_session_remembers_prefix_rule(make_agent, tmp_path):
    count = 0

    async def ask(req):
        nonlocal count
        count += 1
        return Decision("allow_session")

    script = [
        {"calls": [("Bash", {"command": "mkdir a"})]},
        {"calls": [("Bash", {"command": "mkdir b"})]},
        {"text": "ok"},
    ]
    agent = make_agent(script, ask=ask)
    await collect(agent, "go")
    assert count == 1 and (tmp_path / "a").is_dir() and (tmp_path / "b").is_dir()
    assert "Bash(mkdir:*)" in agent.policy.allow_rules


async def test_hard_denied_command_never_prompts(make_agent):
    async def ask(req):  # pragma: no cover - must not be called
        raise AssertionError("prompted for a hard-denied command")

    agent = make_agent([{"calls": [("Bash", {"command": "rm -rf /"})]}, {"text": "ok"}], ask=ask)
    events = await collect(agent, "go")
    assert ends(events)[0].is_error and "never allowed" in ends(events)[0].output


async def test_plan_mode_blocks_edits_and_exit_plan_switches_mode(make_agent, tmp_path):
    async def ask(req):
        return Decision("allow_session")

    script = [
        {"calls": [("Write", {"path": "x.py", "content": "1"})]},
        {"calls": [("ExitPlanMode", {"plan": "1. do it"})]},
        {"text": "implementing"},
    ]
    agent = make_agent(script, ask=ask, mode=Mode.PLAN)
    events = await collect(agent, "plan it")
    assert "read-only" in ends(events)[0].output and not (tmp_path / "x.py").exists()
    assert any(isinstance(e, ModeChanged) and e.mode == "acceptEdits" for e in events)
    assert agent.mode == Mode.ACCEPT_EDITS


async def test_rejecting_plan_keeps_plan_mode(make_agent):
    async def ask(req):
        return Decision("deny", "also cover tests")

    agent = make_agent(
        [{"calls": [("ExitPlanMode", {"plan": "p"})]}, {"text": "revising"}], ask=ask, mode=Mode.PLAN
    )
    events = await collect(agent, "plan")
    assert agent.mode == Mode.PLAN and "cover tests" in ends(events)[0].output


async def test_text_protocol_tool_calls_are_hidden_and_executed(make_agent, tmp_path):
    (tmp_path / "f.txt").write_text("x")
    chunks = ["Let me look. <tool", '_call>{"name": "LS", "arguments": {}}</tool_', "call>"]
    agent = make_agent([{"chunks": chunks}, {"text": "saw f.txt"}])
    events = await collect(agent, "ls")
    visible = "".join(e.text for e in events if isinstance(e, TextDelta))
    assert "tool_call" not in visible and visible.startswith("Let me look.")
    assert ends(events)[0].output == "f.txt"


async def test_literal_angle_text_is_not_swallowed(make_agent):
    agent = make_agent([{"chunks": ["use a <t", "able> element"]}])
    events = await collect(agent, "html")
    assert "".join(e.text for e in events if isinstance(e, TextDelta)) == "use a <table> element"


async def test_identical_call_loop_is_broken(make_agent):
    same = {"calls": [("LS", {})]}
    agent = make_agent([same, same, same, {"text": "giving up"}])
    events = await collect(agent, "go")
    outs = [e.output for e in ends(events)]
    assert "3 times in a row" in outs[2] and "3 times" not in outs[1]


async def test_step_limit_stops_the_turn(make_agent):
    script = [{"calls": [("Grep", {"pattern": f"p{i}"})]} for i in range(5)]
    agent = make_agent(script, max_steps=2)
    events = await collect(agent, "go")
    assert done(events) == "max_turns" and any(
        isinstance(e, Notice) and "Stopped after 2" in e.text for e in events
    )


async def test_interrupt_during_approval_ends_turn(make_agent, tmp_path):
    holder = {}

    async def ask(req):
        holder["agent"].interrupt()
        return Decision("allow")

    agent = make_agent(
        [{"calls": [("Write", {"path": "z.txt", "content": "x"})]}, {"text": "never"}], ask=ask
    )
    holder["agent"] = agent
    events = await collect(agent, "go")
    assert done(events) == "interrupted" and not (tmp_path / "z.txt").exists()
    assert agent.running is False


async def test_second_run_while_running_is_rejected(make_agent):
    gate = asyncio.Event()

    async def ask(req):
        await gate.wait()
        return Decision("deny")

    agent = make_agent([{"calls": [("Write", {"path": "a", "content": "x"})]}, {"text": "ok"}], ask=ask)
    first = asyncio.create_task(collect(agent, "one"))
    await asyncio.sleep(0.05)
    second = await collect(agent, "two")
    assert any(isinstance(e, Notice) and "already working" in e.text for e in second)
    gate.set()
    await first


async def test_llm_error_ends_turn_with_notice(make_agent):
    agent = make_agent([LLMError("model exploded")])
    events = await collect(agent, "go")
    assert done(events) == "error" and any(isinstance(e, Notice) and e.level == "error" for e in events)


async def test_transient_error_is_retried(make_agent):
    agent = make_agent(
        [LLMError("Cannot reach llama-server", retryable=True), {"text": "back"}], retry_delays=(0.0,)
    )
    events = await collect(agent, "go")
    assert done(events) == "end"
    assert any(isinstance(e, Notice) and e.level == "warn" and "retrying" in e.text for e in events)


async def test_non_retryable_error_is_not_retried(make_agent):
    agent = make_agent([LLMError("HTTP 401", retryable=False), {"text": "never"}], retry_delays=(0.0,))
    events = await collect(agent, "go")
    assert done(events) == "error" and len(agent.llm.requests) == 1


async def test_retries_are_bounded(make_agent):
    agent = make_agent([LLMError("down", retryable=True)] * 5, retry_delays=(0.0, 0.0))
    events = await collect(agent, "go")
    assert done(events) == "error" and len(agent.llm.requests) == 3


async def test_context_overflow_triggers_compaction_then_retry(make_agent):
    agent = make_agent(
        [
            LLMError("llama-server returned HTTP 400: prompt exceeds the context size"),
            {"text": "SUMMARY"},
            {"text": "final"},
        ]
    )
    agent.messages = [{"role": "user", "content": "old"}, {"role": "assistant", "content": "older"}]
    events = await collect(agent, "new task")
    assert done(events) == "end" and "too long" in next(e.text for e in events if isinstance(e, Notice))
    assert agent.messages[0]["content"].startswith("[Summary of earlier conversation]")


async def test_auto_compaction_near_context_limit(make_agent):
    agent = make_agent([{"text": "SUMMARY"}, {"text": "continuing"}], context_window=1000)
    agent.messages = [{"role": "user" if i % 2 == 0 else "assistant", "content": "x" * 900} for i in range(6)]
    events = await collect(agent, "more")
    assert any(isinstance(e, Notice) and "summarized" in e.text for e in events) and done(events) == "end"


async def test_at_mentions_attach_files(make_agent, tmp_path):
    (tmp_path / "a.py").write_text("print('hi')\n")
    agent = make_agent([{"text": "ok"}])
    events = await collect(agent, "explain @a.py and @../etc/passwd")
    sent = agent.llm.requests[0][0][-1]["content"]
    assert '<file path="a.py">' in sent and "passwd" not in sent.split("</file>")[-1]
    assert any(isinstance(e, Notice) and "a.py" in e.text for e in events)


async def test_undo_reverts_last_turn(make_agent, tmp_path):
    async def ask(req):
        return Decision("allow")

    (tmp_path / "keep.txt").write_text("v1")
    script = [
        {"calls": [("Read", {"path": "keep.txt"})]},
        {"calls": [("Write", {"path": "keep.txt", "content": "v2"})]},
        {"text": "ok"},
    ]
    agent = make_agent(script, ask=ask)
    await collect(agent, "edit")
    assert (tmp_path / "keep.txt").read_text() == "v2"
    assert agent.undo() and (tmp_path / "keep.txt").read_text() == "v1"


async def test_todo_updates_emitted(make_agent):
    todos = [{"content": "step", "status": "in_progress"}]
    agent = make_agent([{"calls": [("TodoWrite", {"todos": todos})]}, {"text": "ok"}])
    events = await collect(agent, "plan")
    assert any(type(e).__name__ == "TodoUpdate" and e.todos == todos for e in events)


async def test_unknown_tool_and_bad_args_are_reported_not_raised(make_agent):
    script = [{"calls": [("Nope", {})]}, {"calls": [("Read", {})]}, {"text": "ok"}]
    agent = make_agent(script)
    events = await collect(agent, "go")
    assert "Unknown tool" in ends(events)[0].output and "missing required" in ends(events)[1].output
    assert done(events) == "end"


async def test_sessions_round_trip_into_new_agent(make_agent, tmp_path):
    agent = make_agent([{"text": "first answer"}])
    await collect(agent, "remember this")
    other = make_agent([{"text": "x"}])
    other.store = agent.store
    assert other.load_session(agent.session_id) == 1
    assert other.messages == agent.messages and other.session_id == agent.session_id


async def test_audit_trail_records_decisions_without_contents(make_agent, tmp_path):
    log = tmp_path / "audit" / "a.jsonl"

    async def ask(req):
        return Decision("allow")

    script = [
        {"calls": [("Write", {"path": "s.txt", "content": "TOP-SECRET-BODY"})]},
        {"calls": [("Bash", {"command": "echo hi --password=hunter2"})]},
        {"calls": [("Bash", {"command": "sudo ls"})]},
        {"text": "done"},
    ]
    agent = make_agent(script, ask=ask, audit=AuditLog(log))
    await collect(agent, "audit me")
    raw = log.read_text()
    rows = [json.loads(line) for line in raw.splitlines()]
    assert "TOP-SECRET-BODY" not in raw and "hunter2" not in raw
    tools = [r for r in rows if r["event"] == "tool"]
    assert [t["decision"] for t in tools] == ["user_allow", "auto", "policy_deny"]
    assert tools[0]["args"] == {"path": "s.txt", "bytes": 15}
    assert (
        rows[0]["event"] == "turn_start"
        and rows[-1]["event"] == "turn_end"
        and rows[-1]["stop_reason"] == "end"
    )
    assert all(r["session"] == agent.session_id for r in rows)
    assert (log.stat().st_mode & 0o777) == 0o600


async def test_pre_tool_hook_can_block(make_agent, tmp_path):
    hooks = Hooks(
        {"PreToolUse": [{"matcher": "Bash", "command": "echo 'no shell today' >&2; exit 2"}]}, tmp_path
    )
    agent = make_agent([{"calls": [("Bash", {"command": "ls"})]}, {"text": "ok"}], hooks=hooks)
    events = await collect(agent, "go")
    assert ends(events)[0].is_error and "no shell today" in ends(events)[0].output


async def test_post_tool_hook_feedback_reaches_model(make_agent, tmp_path):
    (tmp_path / "f.txt").write_text("x")
    hooks = Hooks(
        {"PostToolUse": [{"matcher": "Read", "command": "echo 'lint failed' >&2; exit 2"}]}, tmp_path
    )
    agent = make_agent([{"calls": [("Read", {"path": "f.txt"})]}, {"text": "ok"}], hooks=hooks)
    events = await collect(agent, "go")
    assert "lint failed" in ends(events)[0].output and not ends(events)[0].is_error


async def test_clear_resets_state_and_session_id(make_agent):
    agent = make_agent([{"text": "a"}])
    await collect(agent, "x")
    old = agent.session_id
    agent.clear()
    assert agent.messages == [] and agent.session_id != old and agent.audit.session_id == agent.session_id


@pytest.mark.parametrize("name", ["ToolStart"])
async def test_events_are_json_serialisable(make_agent, name):
    from zcoder.agent.codeagent.events import event_to_dict

    agent = make_agent([{"calls": [("LS", {})]}, {"text": "ok"}])
    events = await collect(agent, "go")
    starts = [e for e in events if isinstance(e, ToolStart)]
    assert json.dumps(event_to_dict(starts[0]))
