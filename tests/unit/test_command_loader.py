"""Regression tests for Slice E.4 command-loader containment — .claude/commands/*.md
and plugin command loading (mirrors scoped skills/memory/agents, SEC-004/SEC-007)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from zcoder.claude.capabilities import code as code_module
from zcoder.claude.capabilities.code import cmd_code_slash


def _write_command(root: Path, name: str, body: str, *, symlink_to: Path | None = None) -> Path:
    f = root / f"{name}.md"
    if symlink_to is not None:
        f.symlink_to(symlink_to)
    else:
        f.write_text(body)
    return f


def _invoke(cmd: str, cwd: Path, monkeypatch) -> MagicMock:
    mock_agent = MagicMock()
    monkeypatch.setattr(
        "zcoder.claude.capabilities.code.CodeAgent",
        lambda *a, **kw: mock_agent,
    )
    monkeypatch.setattr(
        "zcoder.claude.capabilities.code.CodeSession",
        lambda *a, **kw: MagicMock(),
    )
    cmd_code_slash(cmd, api_key="test", model="test", cwd=str(cwd))
    return mock_agent


def test_custom_command_loaded(tmp_path, monkeypatch):
    cmds = tmp_path / ".claude" / "commands"
    cmds.mkdir(parents=True)
    _write_command(cmds, "greet", "# Greet\n\nHello!\n")
    monkeypatch.setattr(code_module, "COMMANDS_DIR", cmds)
    monkeypatch.setattr(code_module, "SKILLS_DIR", tmp_path / ".claude" / "skills")
    mock_agent = _invoke("greet", tmp_path, monkeypatch)
    assert mock_agent.query.called
    assert "Hello!" in mock_agent.query.call_args[0][0]


def test_custom_command_symlink_escape_rejected(tmp_path, monkeypatch):
    cmds = tmp_path / ".claude" / "commands"
    cmds.mkdir(parents=True)
    secret = tmp_path.parent / "secret_cmd.txt"
    secret.write_text("SECRET_CMD_CONTENT\n")
    _write_command(cmds, "evil", "", symlink_to=secret)
    monkeypatch.setattr(code_module, "COMMANDS_DIR", cmds)
    monkeypatch.setattr(code_module, "SKILLS_DIR", tmp_path / ".claude" / "skills")
    mock_agent = _invoke("evil", tmp_path, monkeypatch)
    assert not mock_agent.query.called


def test_custom_command_oversized_skipped(tmp_path, monkeypatch):
    cmds = tmp_path / ".claude" / "commands"
    cmds.mkdir(parents=True)
    _write_command(cmds, "big", "# Big\n" + ("X" * (300 * 1024)))
    monkeypatch.setattr(code_module, "COMMANDS_DIR", cmds)
    monkeypatch.setattr(code_module, "SKILLS_DIR", tmp_path / ".claude" / "skills")
    mock_agent = _invoke("big", tmp_path, monkeypatch)
    assert not mock_agent.query.called


def test_plugin_command_loaded_via_plugin_dir(monkeypatch):
    plugin_dir = Path("/tmp/test_plugin")
    cmd_file = plugin_dir / "commands" / "pcmd.md"
    cmd_file.parent.mkdir(parents=True, exist_ok=True)
    cmd_file.write_text("# Plugin Cmd\n\nPlugin!\n")

    def fake_load():
        return [
            {
                "name": "myplugin:pcmd",
                "path": str(cmd_file),
                "plugin": "myplugin",
                "plugin_dir": str(plugin_dir),
            }
        ]

    monkeypatch.setattr("zcoder.claude.tools.plugins.load_plugin_commands", fake_load)
    mock_agent = _invoke("pcmd", Path("."), monkeypatch)
    assert mock_agent.query.called
    assert "Plugin!" in mock_agent.query.call_args[0][0]


def test_plugin_command_symlink_escape_rejected(monkeypatch, tmp_path):
    plugin_dir = tmp_path / "myplugin"
    cmd_file = plugin_dir / "commands" / "evil.md"
    cmd_file.parent.mkdir(parents=True)
    secret = tmp_path / "secret.txt"
    secret.write_text("PLUGIN_CMD_SECRET\n")
    cmd_file.symlink_to(secret)

    def fake_load():
        return [
            {
                "name": "myplugin:evil",
                "path": str(cmd_file),
                "plugin": "myplugin",
                "plugin_dir": str(plugin_dir),
            }
        ]

    monkeypatch.setattr("zcoder.claude.tools.plugins.load_plugin_commands", fake_load)
    mock_agent = _invoke("evil", Path("."), monkeypatch)
    assert not mock_agent.query.called
