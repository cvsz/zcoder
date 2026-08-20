"""Regression guards for Slice D permission/approval parity hardening.

Covers:
- acceptEdits auto-approves file edits and read-only tools only; other
  tools (Bash, TodoWrite, ...) require approval and fail closed
  non-interactively.
- PreToolUse hooks fail closed: timeout, error, or unrecognized exit
  codes block the tool call instead of silently allowing it.
- Audit: every denial path records the tool call with approved=False.
"""

from __future__ import annotations

import subprocess

from zcoder.claude.capabilities.code import CodeAgent, CodeSession, HooksEngine


def _agent() -> CodeAgent:
    return CodeAgent(api_key="test-key", model="test-model")


def _session(tmp_path) -> CodeSession:
    return CodeSession(cwd=str(tmp_path), model="test-model")


class _NoopHooks:
    def pre_tool_use(self, *_args, **_kwargs):
        return {"allowed": True, "message": ""}

    def post_tool_use(self, *_args, **_kwargs):
        return None


# ── D1: acceptEdits auto-approves edits/reads, gates everything else ─────


def test_accept_edits_auto_approves_write(tmp_path) -> None:
    session = _session(tmp_path)
    result = _agent()._execute_tool(
        "Write",
        {"path": "a.txt", "content": "alpha"},
        session,
        _NoopHooks(),
        permission="acceptEdits",
    )
    assert result.startswith("Written")
    assert session.tool_calls[-1]["approved"] is True


def test_accept_edits_auto_approves_read(tmp_path) -> None:
    session = _session(tmp_path)
    (tmp_path / "a.txt").write_text("alpha", encoding="utf-8")
    result = _agent()._execute_tool(
        "Read",
        {"path": "a.txt"},
        session,
        _NoopHooks(),
        permission="acceptEdits",
    )
    assert result == "alpha"


def test_accept_edits_denies_bash_noninteractive(tmp_path, monkeypatch) -> None:
    def no_input(prompt=""):
        raise EOFError()

    monkeypatch.setattr("builtins.input", no_input)
    session = _session(tmp_path)
    result = _agent()._execute_tool(
        "Bash",
        {"command": "echo hi"},
        session,
        _NoopHooks(),
        permission="acceptEdits",
    )
    assert result == "[DENIED — no terminal]"
    assert session.tool_calls[-1]["approved"] is False


def test_accept_edits_respects_can_use_tool_deny(tmp_path) -> None:
    session = _session(tmp_path)
    result = _agent()._execute_tool(
        "Bash",
        {"command": "echo hi"},
        session,
        _NoopHooks(),
        permission="acceptEdits",
        can_use_tool=lambda name, inputs: False,
    )
    assert result == "[DENIED by user]"


def test_accept_edits_denies_todo_write_noninteractive(tmp_path, monkeypatch) -> None:
    def no_input(prompt=""):
        raise EOFError()

    monkeypatch.setattr("builtins.input", no_input)
    session = _session(tmp_path)
    result = _agent()._execute_tool(
        "TodoWrite",
        {"todos": [{"content": "x", "priority": "medium"}]},
        session,
        _NoopHooks(),
        permission="acceptEdits",
    )
    assert result == "[DENIED — no terminal]"


def test_bypass_permissions_still_approves_everything(tmp_path) -> None:
    session = _session(tmp_path)
    result = _agent()._execute_tool(
        "Bash",
        {"command": "echo hi"},
        session,
        _NoopHooks(),
        permission="bypassPermissions",
    )
    assert "hi" in result


# ── D2: PreToolUse hooks fail closed on timeout/error/unknown exit ────────


class _FakeCompleted:
    def __init__(self, returncode: int):
        self.returncode = returncode
        self.stdout = ""
        self.stderr = ""


def _hook_engine() -> HooksEngine:
    return HooksEngine({"PreToolUse": [{"command": "guard"}]})


def test_pre_tool_use_hook_exit_2_blocks(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "zcoder.claude.capabilities.code.subprocess.run",
        lambda *a, **k: _FakeCompleted(2),
    )
    session = _session(tmp_path)
    result = _agent()._execute_tool(
        "Read",
        {"path": "."},
        session,
        _hook_engine(),
        permission="askPermission",
    )
    assert result.startswith("[BLOCKED by hook]")


def test_pre_tool_use_hook_unknown_exit_blocks(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "zcoder.claude.capabilities.code.subprocess.run",
        lambda *a, **k: _FakeCompleted(3),
    )
    session = _session(tmp_path)
    result = _agent()._execute_tool(
        "Read",
        {"path": "."},
        session,
        _hook_engine(),
        permission="askPermission",
    )
    assert result.startswith("[BLOCKED by hook]")


def test_pre_tool_use_hook_timeout_blocks(tmp_path, monkeypatch) -> None:
    def hang(*a, **k):
        raise subprocess.TimeoutExpired("guard", timeout=30)

    monkeypatch.setattr("zcoder.claude.capabilities.code.subprocess.run", hang)
    session = _session(tmp_path)
    result = _agent()._execute_tool(
        "Read",
        {"path": "."},
        session,
        _hook_engine(),
        permission="askPermission",
    )
    assert result.startswith("[BLOCKED by hook]")


def test_pre_tool_use_hook_error_blocks(tmp_path, monkeypatch) -> None:
    def crash(*a, **k):
        raise OSError("boom")

    monkeypatch.setattr("zcoder.claude.capabilities.code.subprocess.run", crash)
    session = _session(tmp_path)
    result = _agent()._execute_tool(
        "Read",
        {"path": "."},
        session,
        _hook_engine(),
        permission="askPermission",
    )
    assert result.startswith("[BLOCKED by hook]")


def test_pre_tool_use_hook_exit_0_and_1_allow(tmp_path, monkeypatch) -> None:
    session = _session(tmp_path)
    (tmp_path / "a.txt").write_text("alpha", encoding="utf-8")
    for code in (0, 1):
        fake = _FakeCompleted(code)
        monkeypatch.setattr(
            "zcoder.claude.capabilities.code.subprocess.run",
            lambda *a, fake=fake, **k: fake,
        )
        result = _agent()._execute_tool(
            "Read",
            {"path": "a.txt"},
            session,
            _hook_engine(),
            permission="askPermission",
        )
        assert result == "alpha"


def test_post_tool_use_hook_error_does_not_block(tmp_path, monkeypatch) -> None:
    def crash(*a, **k):
        raise OSError("boom")

    monkeypatch.setattr("zcoder.claude.capabilities.code.subprocess.run", crash)
    engine = HooksEngine({"PostToolUse": [{"command": "reporter"}]})
    session = _session(tmp_path)
    result = engine.fire("PostToolUse", {"session_id": session.id})
    assert result["allowed"] is True


# ── D3: denial paths record approved=False in the audit trail ─────────────


def test_dont_ask_denial_recorded_as_not_approved(tmp_path) -> None:
    session = _session(tmp_path)
    result = _agent()._execute_tool(
        "Read",
        {"path": "."},
        session,
        _NoopHooks(),
        permission="dontAsk",
    )
    assert result == "[DENIED] Tool not in allowed list."
    assert session.tool_calls[-1]["approved"] is False


def test_plan_mode_denial_recorded_as_not_approved(tmp_path) -> None:
    session = _session(tmp_path)
    result = _agent()._execute_tool(
        "Read",
        {"path": "."},
        session,
        _NoopHooks(),
        permission="planMode",
    )
    assert "PLAN MODE" in result
    assert session.tool_calls[-1]["approved"] is False


def test_hook_block_recorded_as_not_approved(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "zcoder.claude.capabilities.code.subprocess.run",
        lambda *a, **k: _FakeCompleted(2),
    )
    session = _session(tmp_path)
    _agent()._execute_tool(
        "Read",
        {"path": "."},
        session,
        _hook_engine(),
        permission="askPermission",
    )
    assert session.tool_calls[-1]["approved"] is False


def test_executed_tool_recorded_as_approved(tmp_path) -> None:
    session = _session(tmp_path)
    (tmp_path / "a.txt").write_text("alpha", encoding="utf-8")
    _agent()._execute_tool(
        "Read",
        {"path": "a.txt"},
        session,
        _NoopHooks(),
        permission="askPermission",
    )
    assert session.tool_calls[-1]["approved"] is True
