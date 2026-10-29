from __future__ import annotations

import os
import threading
import time

import pytest

from zcoder.agent.codeagent.tools import ToolContext, default_tools, validate_args
from zcoder.agent.codeagent.workspace import ToolError, Workspace


@pytest.fixture
def ctx(tmp_path):
    return ToolContext(Workspace(tmp_path))


def run(ctx, name, **args):
    tool = default_tools()[name]
    return tool.func(ctx, validate_args(tool, args))


def test_read_numbers_lines_and_paginates(ctx, tmp_path):
    (tmp_path / "a.txt").write_text("\n".join(f"l{i}" for i in range(1, 11)))
    out = run(ctx, "Read", path="a.txt", offset=3, limit=2).text
    assert out.splitlines()[0].endswith("l3") and "more lines" in out


def test_read_rejects_binary_and_missing(ctx, tmp_path):
    (tmp_path / "b.bin").write_bytes(b"\x00\x01")
    with pytest.raises(ToolError, match="binary"):
        run(ctx, "Read", path="b.bin")
    with pytest.raises(ToolError, match="not found"):
        run(ctx, "Read", path="nope")


def test_sandbox_blocks_escape_and_symlink(ctx, tmp_path):
    with pytest.raises(ToolError, match="outside"):
        run(ctx, "Read", path="../etc/passwd")
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("x")
    os.symlink(outside, tmp_path / "link.txt")
    with pytest.raises(ToolError, match="outside"):
        run(ctx, "Read", path="link.txt")


def test_grep_does_not_read_external_symlink(ctx, tmp_path):
    outside = tmp_path.parent / "private-marker.txt"
    outside.write_text("credential-marker")
    try:
        os.symlink(outside, tmp_path / "external.txt")
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is not supported")
    assert run(ctx, "Grep", pattern="credential-marker", output_mode="content").text == "No matches found"


def test_write_creates_then_requires_read_then_overwrites(ctx, tmp_path):
    assert "Created" in run(ctx, "Write", path="d/n.py", content="x = 1\n").text
    (tmp_path / "e.txt").write_text("old\n")
    with pytest.raises(ToolError, match="not been read"):
        run(ctx, "Write", path="e.txt", content="new\n")
    run(ctx, "Read", path="e.txt")
    out = run(ctx, "Write", path="e.txt", content="new\n")
    assert "-old" in out.diff and "+new" in out.diff


def test_edit_unique_replace_all_and_stale(ctx, tmp_path):
    f = tmp_path / "m.py"
    f.write_text("a = 1\nb = 1\n")
    run(ctx, "Read", path="m.py")
    with pytest.raises(ToolError, match="2 places"):
        run(ctx, "Edit", path="m.py", old_string="= 1", new_string="= 2")
    with pytest.raises(ToolError, match="not found"):
        run(ctx, "Edit", path="m.py", old_string="zzz", new_string="y")
    run(ctx, "Edit", path="m.py", old_string="= 1", new_string="= 2", replace_all=True)
    assert f.read_text() == "a = 2\nb = 2\n"
    f.write_text("changed externally\n")
    os.utime(f, ns=(time.time_ns() + 10**9, time.time_ns() + 10**9))
    with pytest.raises(ToolError, match="changed since"):
        run(ctx, "Edit", path="m.py", old_string="changed", new_string="x")


def test_git_dir_is_protected(ctx, tmp_path):
    (tmp_path / ".git").mkdir()
    with pytest.raises(ToolError, match=".git"):
        run(ctx, "Write", path=".git/config", content="x")


def test_undo_restores_and_deletes(ctx, tmp_path):
    ws = ctx.workspace
    ws.begin_turn()
    (tmp_path / "k.txt").write_text("orig")
    run(ctx, "Read", path="k.txt")
    run(ctx, "Write", path="k.txt", content="mod")
    run(ctx, "Write", path="new.txt", content="n")
    assert len(ws.undo_last_turn()) == 2
    assert (tmp_path / "k.txt").read_text() == "orig" and not (tmp_path / "new.txt").exists()
    assert ws.undo_last_turn() == []


def test_glob_grep_ls_skip_ignored_dirs(ctx, tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("def foo():\n    pass\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.py").write_text("def foo(): pass")
    assert run(ctx, "Glob", pattern="**/*.py").text == "src/a.py"
    assert run(ctx, "Grep", pattern="def foo").text == "src/a.py"
    assert run(ctx, "Grep", pattern="def (\\w+)", output_mode="content").text == "src/a.py:1:def foo():"
    assert run(ctx, "Grep", pattern="zzz").text == "No matches found"
    with pytest.raises(ToolError, match="invalid regex"):
        run(ctx, "Grep", pattern="(")
    assert "src/" in run(ctx, "LS").text and "node_modules" not in run(ctx, "LS").text
    with pytest.raises(ToolError):
        run(ctx, "Glob", pattern="../*")


def test_bash_output_exit_code_timeout_cancel(ctx):
    assert run(ctx, "Bash", command="echo hi").text.strip() == "hi"
    with pytest.raises(ToolError, match=r"exit code 3"):
        run(ctx, "Bash", command="echo bad; exit 3")
    with pytest.raises(ToolError, match="timed out"):
        run(ctx, "Bash", command="sleep 5", timeout=1)
    threading.Timer(0.3, ctx.cancel.set).start()
    with pytest.raises(ToolError, match="interrupted"):
        run(ctx, "Bash", command="sleep 5")


def test_todos_validation(ctx):
    run(
        ctx,
        "TodoWrite",
        todos=[{"content": "a", "status": "in_progress"}, {"content": "b", "status": "pending"}],
    )
    assert len(ctx.todos) == 2
    with pytest.raises(ToolError, match="in_progress"):
        run(
            ctx,
            "TodoWrite",
            todos=[{"content": "a", "status": "in_progress"}, {"content": "b", "status": "in_progress"}],
        )


def test_validate_args_coerces_and_rejects():
    t = default_tools()["Read"]
    assert validate_args(t, {"path": "x", "limit": "5"})["limit"] == 5
    with pytest.raises(ToolError, match="missing"):
        validate_args(t, {})
    with pytest.raises(ToolError, match="valid JSON"):
        validate_args(t, {"__parse_error__": "{"})
