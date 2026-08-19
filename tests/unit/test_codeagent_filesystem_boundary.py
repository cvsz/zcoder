"""Regression guards for SEC-004 CodeAgent workspace containment."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from zcoder.claude.capabilities.code import CodeAgent, CodeSession


def _agent() -> CodeAgent:
    return CodeAgent(api_key="test-key", model="test-model")


def _session(workspace: Path) -> CodeSession:
    return CodeSession(cwd=str(workspace), model="test-model")


def _assert_blocked(result: str) -> None:
    assert "Path escapes the allowed base directory" in result


def test_read_rejects_relative_traversal(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("outside-secret", encoding="utf-8")

    result = _agent()._run_tool("Read", {"path": "../secret.txt"}, _session(workspace))

    _assert_blocked(result)
    assert "outside-secret" not in result


def test_read_rejects_absolute_path_escape(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("outside-secret", encoding="utf-8")

    result = _agent()._run_tool(
        "Read", {"path": str(secret.resolve())}, _session(workspace)
    )

    _assert_blocked(result)
    assert "outside-secret" not in result


def test_read_rejects_symlink_escape(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("outside-secret", encoding="utf-8")
    link = workspace / "escape.txt"
    try:
        link.symlink_to(secret)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable in this environment")

    result = _agent()._run_tool("Read", {"path": "escape.txt"}, _session(workspace))

    _assert_blocked(result)
    assert "outside-secret" not in result


@pytest.mark.parametrize(
    ("tool", "inputs"),
    [
        ("Glob", {"pattern": "*", "path": ".."}),
        ("Grep", {"pattern": "outside-secret", "path": "..", "include": "*.txt"}),
        ("LS", {"path": ".."}),
    ],
)
def test_readonly_enumeration_tools_reject_workspace_escape(
    tmp_path: Path, tool: str, inputs: dict[str, str]
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (tmp_path / "secret.txt").write_text("outside-secret", encoding="utf-8")

    result = _agent()._run_tool(tool, inputs, _session(workspace))

    _assert_blocked(result)


def test_glob_pattern_cannot_traverse_above_safe_base(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (tmp_path / "secret.txt").write_text("outside-secret", encoding="utf-8")

    result = _agent()._run_tool(
        "Glob", {"pattern": "../*.txt", "path": "."}, _session(workspace)
    )

    assert "Glob pattern must stay inside the workspace" in result
    assert "secret.txt" not in result


def test_grep_include_pattern_cannot_traverse_above_safe_base(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (tmp_path / "secret.txt").write_text("outside-secret", encoding="utf-8")

    result = _agent()._run_tool(
        "Grep",
        {"pattern": "outside-secret", "path": ".", "include": "../*.txt"},
        _session(workspace),
    )

    assert "Grep include pattern must stay inside the workspace" in result
    assert "outside-secret" not in result


def test_write_rejects_escape_without_mutating_outside_workspace(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "created.txt"

    result = _agent()._run_tool(
        "Write",
        {"path": "../created.txt", "content": "must-not-be-written"},
        _session(workspace),
    )

    _assert_blocked(result)
    assert not outside.exists()


def test_edit_rejects_escape_without_mutating_outside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "editable.txt"
    outside.write_text("before", encoding="utf-8")

    result = _agent()._run_tool(
        "Edit",
        {"path": "../editable.txt", "old_string": "before", "new_string": "after"},
        _session(workspace),
    )

    _assert_blocked(result)
    assert outside.read_text(encoding="utf-8") == "before"


def test_filesystem_tools_keep_normal_workspace_behavior(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session = _session(workspace)
    agent = _agent()

    assert agent._run_tool(
        "Write", {"path": "notes/a.txt", "content": "alpha"}, session
    ).startswith("Written")
    assert agent._run_tool("Read", {"path": "notes/a.txt"}, session) == "alpha"
    assert "notes/a.txt" in agent._run_tool(
        "Glob", {"pattern": "**/*.txt"}, session
    )
    assert "alpha" in agent._run_tool(
        "Grep", {"pattern": "alpha", "path": ".", "include": "*.txt"}, session
    )
    assert "notes" in agent._run_tool("LS", {"path": "."}, session)
    assert agent._run_tool(
        "Edit",
        {"path": "notes/a.txt", "old_string": "alpha", "new_string": "beta"},
        session,
    ).startswith("Edited")
    assert (workspace / "notes" / "a.txt").read_text(encoding="utf-8") == "beta"


def test_noninteractive_ask_permission_still_routes_read_through_boundary(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("outside-secret", encoding="utf-8")
    session = _session(workspace)
    agent = _agent()

    class AllowingHooks:
        def pre_tool_use(self, *_args, **_kwargs):
            return {"allowed": True, "message": ""}

        def post_tool_use(self, *_args, **_kwargs):
            return None

    result = agent._execute_tool(
        "Read",
        {"path": os.path.relpath(secret, workspace)},
        session,
        AllowingHooks(),
        permission="askPermission",
        can_use_tool=None,
    )

    _assert_blocked(result)
    assert "outside-secret" not in result
