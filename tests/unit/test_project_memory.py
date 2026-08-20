"""Regression tests for Slice E.2 — scoped CLAUDE.md memory + trust boundary."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from zcoder.claude.capabilities.code import MemoryManager, MemoryScope


@pytest.fixture
def scoped_tree(tmp_path: Path):
    # workspace with nested CLAUDE.md (project, higher precedence)
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "CLAUDE.md").write_text("PROJECT_ROOT_MEMORY")
    nested = ws / "sub" / "deep"
    nested.mkdir(parents=True)
    (nested / ".claude").mkdir()
    (nested / ".claude" / "CLAUDE.md").write_text("PROJECT_NESTED_MEMORY")
    # user memory file
    user_mem = tmp_path / "user_claude.md"
    user_mem.write_text("USER_MEMORY_CONTENT")
    # enterprise memory dir
    ent = tmp_path / "enterprise"
    ent.mkdir()
    (ent / "CLAUDE.md").write_text("ENTERPRISE_MEMORY")
    return {
        "ws": ws,
        "nested": nested,
        "user_mem": user_mem,
        "ent": ent,
    }


def test_discover_precedence_order(scoped_tree):
    mm = MemoryManager(
        scoped_tree["ws"],
        enterprise_dir=str(scoped_tree["ent"]),
        user_memory_path=str(scoped_tree["user_mem"]),
    )
    layers = mm.discover()
    scopes = [layer.scope for layer in layers]
    # enterprise (lowest) then user then project(s)
    assert MemoryScope.ENTERPRISE in scopes
    assert MemoryScope.USER in scopes
    assert MemoryScope.PROJECT in scopes
    assert scopes.index(MemoryScope.ENTERPRISE) < scopes.index(MemoryScope.USER)
    assert scopes.index(MemoryScope.USER) < scopes.index(MemoryScope.PROJECT)


def test_discover_walks_up_for_nested_project(scoped_tree):
    mm = MemoryManager(
        scoped_tree["nested"],
        enterprise_dir=str(scoped_tree["ent"]),
        user_memory_path=str(scoped_tree["user_mem"]),
    )
    contents = [layer.content for layer in mm.discover() if layer.scope is MemoryScope.PROJECT]
    # both the nested .claude/CLAUDE.md and the root workspace CLAUDE.md are found
    assert "PROJECT_NESTED_MEMORY" in contents
    assert "PROJECT_ROOT_MEMORY" in contents


def test_combined_renders_delimited_block(scoped_tree):
    mm = MemoryManager(
        scoped_tree["ws"],
        enterprise_dir=str(scoped_tree["ent"]),
        user_memory_path=str(scoped_tree["user_mem"]),
    )
    out = mm.combined()
    assert out.startswith("<loaded_memory")
    assert 'context="untrusted-project-and-user-files"' in out
    assert "ENTERPRISE_MEMORY" in out
    assert "USER_MEMORY_CONTENT" in out
    assert "PROJECT_ROOT_MEMORY" in out
    assert out.rstrip().endswith("</loaded_memory>")


def test_combined_opt_out_returns_only_user_memory(scoped_tree):
    mm = MemoryManager(
        scoped_tree["ws"],
        enterprise_dir=str(scoped_tree["ent"]),
        user_memory_path=str(scoped_tree["user_mem"]),
    )
    out = mm.combined(load_project_memory=False)
    assert "ENTERPRISE_MEMORY" not in out
    assert "PROJECT_ROOT_MEMORY" not in out
    assert "USER_MEMORY_CONTENT" in out
    assert "<loaded_memory" not in out


def test_combined_empty_when_no_memory(tmp_path):
    mm = MemoryManager(
        str(tmp_path),
        enterprise_dir=str(tmp_path / "none"),
        user_memory_path=str(tmp_path / "nope.md"),
    )
    assert mm.combined() == ""


def test_containment_rejects_symlink_escape(tmp_path):
    # a project CLAUDE.md symlink pointing outside the workspace must be rejected
    ws = tmp_path / "ws"
    ws.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP_SECRET")
    link = ws / "CLAUDE.md"
    os.symlink(secret, link)
    mm = MemoryManager(str(ws))
    project_layers = [layer for layer in mm.discover() if layer.scope is MemoryScope.PROJECT]
    # the escaped symlink must not be loaded
    assert all("TOP_SECRET" not in layer.content for layer in project_layers)
    assert all(layer.path != link for layer in project_layers)


def test_missing_files_skipped(tmp_path):
    mm = MemoryManager(
        str(tmp_path),
        enterprise_dir=str(tmp_path / "missing_ent"),
        user_memory_path=str(tmp_path / "missing_user.md"),
    )
    # must not raise; just returns nothing
    assert mm.discover() == []
    assert mm.combined() == ""


def test_oversized_file_skipped(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    big = ws / "CLAUDE.md"
    big.write_text("X" * (300 * 1024))  # exceeds 256KiB cap
    mm = MemoryManager(str(ws))
    project = [layer for layer in mm.discover() if layer.scope is MemoryScope.PROJECT]
    assert project == []


def test_backward_compat_read_append(tmp_path, monkeypatch):
    # read_project/read_user/append_* keep working against cwd
    monkeypatch.chdir(tmp_path)
    mm = MemoryManager(str(tmp_path))
    mm.append_project("APPENDED_PROJECT")
    assert "APPENDED_PROJECT" in mm.read_project()
    # discover should still find it
    assert any(
        layer.scope is MemoryScope.PROJECT and "APPENDED_PROJECT" in layer.content for layer in mm.discover()
    )
