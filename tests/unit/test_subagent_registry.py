"""Regression tests for Slice E.3 agent-loader hardening — contained .claude/agents/*.md
loading (mirrors scoped skills/memory, SEC-004/SEC-007 alignment)."""

from __future__ import annotations

from pathlib import Path

from zcoder.claude.capabilities.code import SubagentRegistry


def _write_agent(root: Path, name: str, body: str, *, symlink_to: Path | None = None) -> Path:
    f = root / f"{name}.md"
    if symlink_to is not None:
        f.symlink_to(symlink_to)
    else:
        f.write_text(body)
    return f


def test_normal_agent_loaded(tmp_path):
    _write_agent(tmp_path, "helper", "---\ndescription: Helper\n---\nYou are a helper.\n")
    reg = SubagentRegistry(tmp_path)
    reg.load()
    names = {a["name"] for a in reg.list()}
    assert "helper" in names
    a = reg.get("helper")
    assert a["description"] == "Helper"
    assert a["system_prompt"] == "You are a helper."


def test_symlink_escape_rejected_no_leak(tmp_path):
    secret = tmp_path.parent / "secret_agent.txt"
    secret.write_text("TOP_SECRET_AGENT_CONTENT\n")
    _write_agent(tmp_path, "evil", "", symlink_to=secret)
    reg = SubagentRegistry(tmp_path)
    reg.load()
    surfaced = " ".join(a["description"] + a.get("system_prompt", "") for a in reg.list())
    assert "TOP_SECRET_AGENT_CONTENT" not in surfaced
    assert reg.get("evil") is None


def test_oversized_agent_skipped(tmp_path):
    _write_agent(tmp_path, "big", "---\ndescription: Big\n---\n" + ("X" * (300 * 1024)))
    reg = SubagentRegistry(tmp_path)
    reg.load()
    assert reg.get("big") is None


def test_plugin_agent_loaded_via_plugin_dir(monkeypatch, tmp_path):
    plugin_dir = tmp_path / "myplugin"
    agent_file = plugin_dir / "agents" / "pagent.md"
    agent_file.parent.mkdir(parents=True)
    agent_file.write_text("---\ndescription: Plugin Agent\n---\nDo things.\n")

    def fake_load():
        return [
            {
                "name": "pagent",
                "path": str(agent_file),
                "plugin": "myplugin",
                "plugin_dir": str(plugin_dir),
            }
        ]

    monkeypatch.setattr("zcoder.claude.tools.plugins.load_plugin_agents", fake_load)
    reg = SubagentRegistry(tmp_path)
    reg.load()
    key = "myplugin:pagent"
    assert reg.get(key) is not None
    assert reg.get(key)["plugin"] == "myplugin"


def test_plugin_agent_symlink_escape_rejected(monkeypatch, tmp_path):
    plugin_dir = tmp_path / "myplugin"
    agent_file = plugin_dir / "agents" / "evil.md"
    agent_file.parent.mkdir(parents=True)
    secret = tmp_path / "secret.txt"
    secret.write_text("PLUGIN_AGENT_SECRET\n")
    agent_file.symlink_to(secret)

    def fake_load():
        return [
            {
                "name": "evil",
                "path": str(agent_file),
                "plugin": "myplugin",
                "plugin_dir": str(plugin_dir),
            }
        ]

    monkeypatch.setattr("zcoder.claude.tools.plugins.load_plugin_agents", fake_load)
    reg = SubagentRegistry(tmp_path)
    reg.load()
    assert reg.get("myplugin:evil") is None


def test_load_one_size_cap(tmp_path):
    f = _write_agent(tmp_path, "cap", "---\ndescription: Cap\n---\n" + ("X" * (300 * 1024)))
    reg = SubagentRegistry(tmp_path)
    reg._load_one(f)
    assert reg.get("cap") is None
