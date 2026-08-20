"""Regression guards for SEC-006 tool-agent loop containment and approval.

The `cmd_tool_agent` / `run_agent` loop previously executed every model
tool call with no permission gate and no filesystem containment: a model
(whose decisions are influenced by tool output) could run arbitrary Python
via `run_python` and write to arbitrary paths via `write_file`. These
tests lock the fail-closed approval and containment boundaries.
"""

from __future__ import annotations

import pytest

from zcoder.claude.tools.registry import ToolCoder, build_code_tools_registry


def _registry(tmp_path) -> tuple:
    return build_code_tools_registry(cwd=str(tmp_path))


def _agent() -> ToolCoder:
    return ToolCoder(api_key="test-key", model="test-model")


def test_read_file_blocks_parent_escape(tmp_path) -> None:
    secret = tmp_path.parent / "secret.txt"
    secret.write_text("outside-secret", encoding="utf-8")
    reg = _registry(tmp_path)

    result = reg._funcs["read_file"](str(secret))

    assert "Path escapes" in result
    assert "outside-secret" not in result


def test_write_file_blocks_parent_escape(tmp_path) -> None:
    reg = _registry(tmp_path)
    outside = tmp_path.parent / "created.txt"

    result = reg._funcs["write_file"](str(outside), "must-not-be-written")

    assert "Path escapes" in result
    assert not outside.exists()


def test_write_file_allows_workspace_paths(tmp_path) -> None:
    reg = _registry(tmp_path)

    result = reg._funcs["write_file"]("notes/a.txt", "alpha")

    assert result.startswith("Written")
    assert (tmp_path / "notes" / "a.txt").read_text(encoding="utf-8") == "alpha"
    assert reg._funcs["read_file"]("notes/a.txt") == "alpha"


def test_list_files_blocks_parent_escape(tmp_path) -> None:
    reg = _registry(tmp_path)

    result = reg._funcs["list_files"]("..")

    assert "Path escapes" in result


def test_run_python_denied_in_noninteractive_ask_permission(monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda prompt="": (_ for _ in ()).throw(EOFError()))
    agent = _agent()
    assert agent._approve("run_python", {"code": "print(1)"}, "askPermission", None) is False


def test_write_file_denied_in_noninteractive_ask_permission(monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda prompt="": (_ for _ in ()).throw(EOFError()))
    agent = _agent()
    assert agent._approve("write_file", {"path": "x.txt", "content": "y"}, "askPermission", None) is False


def test_read_only_tools_auto_approved_noninteractive() -> None:
    agent = _agent()
    assert agent._approve("read_file", {"path": "a.txt"}, "askPermission", None) is True
    assert agent._approve("list_files", {"directory": "."}, "askPermission", None) is True


def test_plan_mode_and_dont_ask_deny_everything() -> None:
    agent = _agent()
    for permission in ("planMode", "dontAsk"):
        assert agent._approve("read_file", {"path": "a.txt"}, permission, None) is False
        assert agent._approve("run_python", {"code": "1"}, permission, None) is False


def test_bypass_permissions_allows_everything() -> None:
    agent = _agent()
    assert agent._approve("run_python", {"code": "1"}, "bypassPermissions", None) is True


def test_can_use_tool_callback_is_authoritative() -> None:
    agent = _agent()
    deny = lambda name, inputs: False  # noqa: E731
    allow = lambda name, inputs: True  # noqa: E731
    assert agent._approve("run_python", {}, "askPermission", deny) is False
    assert agent._approve("run_python", {}, "askPermission", allow) is True


def test_run_agent_denies_unapproved_mutating_tool(tmp_path, monkeypatch) -> None:
    from zcoder.claude.tools.registry import ToolRegistry

    reg = ToolRegistry()
    executed = {"n": 0}

    def run_python(code: str) -> str:
        executed["n"] += 1
        return "executed"

    reg.register(
        "run_python",
        "execute code",
        {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]},
        run_python,
    )

    seen_payloads = []

    def fake_post(payload):
        seen_payloads.append(payload)
        return {
            "stop_reason": "tool_use",
            "content": [{"type": "tool_use", "name": "run_python", "id": "t1", "input": {"code": "1"}}],
        }

    agent = _agent()
    monkeypatch.setattr(agent, "_post", fake_post)
    monkeypatch.setattr("builtins.input", lambda prompt="": (_ for _ in ()).throw(EOFError()))
    result = agent.run_agent("do it", reg, max_turns=2, permission="askPermission")
    assert result == "[MAX TURNS REACHED]"
    assert executed["n"] == 0  # the exec tool never ran despite the model requesting it
    assert any(
        isinstance(block, dict) and block.get("content") == "[DENIED] Tool call not approved"
        for payload in seen_payloads
        for msg in payload["messages"]
        if msg.get("role") == "user" and isinstance(msg.get("content"), list)
        for block in msg["content"]
    )
