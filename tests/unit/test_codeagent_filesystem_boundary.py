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


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace


def _assert_blocked(result: str) -> None:
    assert "Path escapes the allowed base directory" in result


def test_read_blocks_parent_escape(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    secret = tmp_path / "secret.txt"
    secret.write_text("outside-secret", encoding="utf-8")
    inputs = {"path": "../secret.txt"}

    result = _agent()._run_tool("Read", inputs, _session(workspace))

    _assert_blocked(result)
    assert "outside-secret" not in result


def test_read_blocks_absolute_escape(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    secret = tmp_path / "secret.txt"
    secret.write_text("outside-secret", encoding="utf-8")
    inputs = {"path": str(secret.resolve())}

    result = _agent()._run_tool("Read", inputs, _session(workspace))

    _assert_blocked(result)
    assert "outside-secret" not in result


def test_read_blocks_symlink_escape(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    secret = tmp_path / "secret.txt"
    secret.write_text("outside-secret", encoding="utf-8")
    link = workspace / "escape.txt"
    try:
        link.symlink_to(secret)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable in this environment")

    result = _agent()._run_tool(
        "Read",
        {"path": "escape.txt"},
        _session(workspace),
    )

    _assert_blocked(result)
    assert "outside-secret" not in result


@pytest.mark.parametrize(
    ("tool", "inputs"),
    [
        ("Glob", {"pattern": "*", "path": ".."}),
        (
            "Grep",
            {
                "pattern": "outside-secret",
                "path": "..",
                "include": "*.txt",
            },
        ),
        ("LS", {"path": ".."}),
    ],
)
def test_readonly_tools_block_parent_escape(
    tmp_path: Path,
    tool: str,
    inputs: dict[str, str],
) -> None:
    workspace = _workspace(tmp_path)
    (tmp_path / "secret.txt").write_text(
        "outside-secret",
        encoding="utf-8",
    )

    result = _agent()._run_tool(tool, inputs, _session(workspace))

    _assert_blocked(result)


def test_glob_blocks_parent_pattern(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    (tmp_path / "secret.txt").write_text(
        "outside-secret",
        encoding="utf-8",
    )
    inputs = {"pattern": "../*.txt", "path": "."}

    result = _agent()._run_tool("Glob", inputs, _session(workspace))

    assert "Glob pattern must stay inside the workspace" in result
    assert "secret.txt" not in result


def test_grep_blocks_parent_include(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    (tmp_path / "secret.txt").write_text(
        "outside-secret",
        encoding="utf-8",
    )
    inputs = {
        "pattern": "outside-secret",
        "path": ".",
        "include": "../*.txt",
    }

    result = _agent()._run_tool("Grep", inputs, _session(workspace))

    assert "Grep include pattern must stay inside the workspace" in result
    assert "outside-secret" not in result


def test_write_blocks_parent_mutation(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    outside = tmp_path / "created.txt"
    inputs = {
        "path": "../created.txt",
        "content": "must-not-be-written",
    }

    result = _agent()._run_tool("Write", inputs, _session(workspace))

    _assert_blocked(result)
    assert not outside.exists()


def test_edit_blocks_parent_mutation(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    outside = tmp_path / "editable.txt"
    outside.write_text("before", encoding="utf-8")
    inputs = {
        "path": "../editable.txt",
        "old_string": "before",
        "new_string": "after",
    }

    result = _agent()._run_tool("Edit", inputs, _session(workspace))

    _assert_blocked(result)
    assert outside.read_text(encoding="utf-8") == "before"


def test_filesystem_tools_allow_workspace_paths(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    session = _session(workspace)
    agent = _agent()

    write_result = agent._run_tool(
        "Write",
        {"path": "notes/a.txt", "content": "alpha"},
        session,
    )
    assert write_result.startswith("Written")
    assert agent._run_tool("Read", {"path": "notes/a.txt"}, session) == "alpha"

    glob_result = agent._run_tool(
        "Glob",
        {"pattern": "**/*.txt"},
        session,
    )
    assert "notes/a.txt" in glob_result

    grep_result = agent._run_tool(
        "Grep",
        {"pattern": "alpha", "path": ".", "include": "*.txt"},
        session,
    )
    assert "alpha" in grep_result
    assert "notes" in agent._run_tool("LS", {"path": "."}, session)

    edit_result = agent._run_tool(
        "Edit",
        {
            "path": "notes/a.txt",
            "old_string": "alpha",
            "new_string": "beta",
        },
        session,
    )
    assert edit_result.startswith("Edited")
    assert (workspace / "notes" / "a.txt").read_text(encoding="utf-8") == "beta"


def test_noninteractive_read_still_uses_boundary(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
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
