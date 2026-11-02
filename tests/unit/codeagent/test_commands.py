from __future__ import annotations

import shutil
import subprocess

import pytest

from zcoder.agent.codeagent.commands import command_names, dispatch, list_commands
from zcoder.agent.codeagent.permissions import Mode


async def test_help_lists_every_command(make_agent):
    out = (await dispatch(make_agent([]), "/help")).output
    assert all(f"/{c.name}" in out for c in list_commands())
    assert "/help" in command_names()


async def test_unknown_command_is_an_error(make_agent):
    r = await dispatch(make_agent([]), "/nope")
    assert r.is_error and "Unknown command" in r.output


async def test_aliases(make_agent):
    agent = make_agent([])
    assert (await dispatch(agent, "/new")).action == "clear"
    assert (await dispatch(agent, "/quit")).action == "exit"
    assert (await dispatch(agent, "/rewind")).output == "Nothing to undo."


async def test_mode_commands(make_agent):
    agent = make_agent([])
    assert (await dispatch(agent, "/mode")).output == "Mode: default"
    assert (await dispatch(agent, "/mode acceptEdits")).action == "mode" and agent.mode == Mode.ACCEPT_EDITS
    assert (await dispatch(agent, "/mode accept")).action == "mode"
    assert (await dispatch(agent, "/mode bogus")).is_error
    r = await dispatch(agent, "/mode bypass")
    assert r.is_error and "disabled" in r.output and agent.mode != Mode.BYPASS
    await dispatch(agent, "/plan")
    assert agent.mode == Mode.PLAN
    await dispatch(agent, "/plan")
    assert agent.mode == Mode.DEFAULT


async def test_permissions_rules_editing(make_agent):
    agent = make_agent([])
    await dispatch(agent, "/permissions allow Bash(npm:*)")
    await dispatch(agent, "/permissions deny Bash(npm publish:*)")
    out = (await dispatch(agent, "/permissions")).output
    assert "Bash(npm:*)" in out and "Bash(npm publish:*)" in out
    await dispatch(agent, "/permissions reset")
    assert agent.policy.allow_rules == [] and agent.policy.deny_rules == []


async def test_status_cost_tools_memory_todos(make_agent):
    agent = make_agent([])
    assert "Session:" in (await dispatch(agent, "/status")).output
    assert "$0.00" in (await dispatch(agent, "/cost")).output
    assert "Bash [exec]" in (await dispatch(agent, "/tools")).output
    assert "/init" in (await dispatch(agent, "/memory")).output
    assert (await dispatch(agent, "/todos")).output == "No todos."
    agent.todos.append({"content": "x", "status": "in_progress"})
    assert "◐ x" in (await dispatch(agent, "/todos")).output


async def test_init_returns_a_prompt_for_the_model(make_agent):
    r = await dispatch(make_agent([]), "/init")
    assert r.action == "prompt" and "ZCODER.md" in r.prompt


async def test_compact_requires_history_then_works(make_agent):
    agent = make_agent([{"text": "SUMMARY"}])
    assert (await dispatch(agent, "/compact")).is_error
    agent.messages = [
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "b"},
        {"role": "user", "content": "c"},
    ]
    r = await dispatch(agent, "/compact focus on tests")
    assert not r.is_error and agent.messages[0]["content"].startswith("[Summary")
    assert "focus on tests" in agent.llm.requests[0][0][0]["content"]


async def test_sessions_and_resume(make_agent):
    from tests.unit.codeagent.conftest import collect

    agent = make_agent([{"text": "done"}])
    await collect(agent, "first task")
    sid = agent.session_id
    agent.clear()
    assert sid in (await dispatch(agent, "/sessions")).output
    r = await dispatch(agent, "/resume")
    assert r.action == "resumed" and agent.session_id == sid
    assert (await dispatch(agent, "/resume 20000101-000000-abcdef")).is_error
    assert (await dispatch(agent, "/resume ../../x")).is_error


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
async def test_diff_reports_changes(make_agent, tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=a@b", "-c", "user.name=t", "commit", "--allow-empty", "-qm", "i"],
        cwd=tmp_path,
        check=True,
    )
    agent = make_agent([])
    assert (await dispatch(agent, "/diff")).output == "No changes."
    (tmp_path / "f.txt").write_text("a")
    subprocess.run(["git", "add", "f.txt"], cwd=tmp_path, check=True)
    (tmp_path / "f.txt").write_text("b")
    assert "f.txt" in (await dispatch(agent, "/diff")).output
