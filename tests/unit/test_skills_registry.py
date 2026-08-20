"""Regression tests for Slice E.2 skills hardening — scoped, contained
SKILL.md loading (SEC-004/SEC-007 alignment, mirrors scoped memory)."""

from __future__ import annotations

from pathlib import Path

from zcoder.claude.capabilities.code import SkillsRegistry


def _write_skill(root: Path, name: str, body: str, *, symlink_to: Path | None = None) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    md = skill_dir / "SKILL.md"
    if symlink_to is not None:
        md.symlink_to(symlink_to)
    else:
        md.write_text(body)
    return skill_dir


def test_custom_skill_loaded_with_description(tmp_path):
    _write_skill(tmp_path, "demo", "# Demo Skill\n\nDoes a thing.\n")
    reg = SkillsRegistry(tmp_path)
    reg.load()
    names = {s["name"] for s in reg.list()}
    assert "demo" in names
    demo = reg.get("demo")
    assert demo["description"] == "Demo Skill"
    assert demo["source"] == "custom"


def test_symlink_escape_rejected_no_leak(tmp_path):
    # a 'secret' file OUTSIDE the skills tree (e.g. /etc/shadow analogue)
    secret = tmp_path.parent / "secret.txt"
    secret.write_text("TOP_SECRET=should-never-be-surfaces\n")
    _write_skill(tmp_path, "evil", "", symlink_to=secret)
    reg = SkillsRegistry(tmp_path)
    reg.load()
    surfaced = " ".join(s["description"] for s in reg.list())
    assert "TOP_SECRET" not in surfaced
    assert reg.get("evil") is None


def test_oversized_skill_skipped(tmp_path):
    _write_skill(tmp_path, "big", "# Big\n" + ("X" * (300 * 1024)))
    reg = SkillsRegistry(tmp_path)
    reg.load()
    assert reg.get("big") is None


def test_traversal_name_rejected(tmp_path):
    # names containing '..' must be skipped regardless of content
    _write_skill(tmp_path, "bad..name", "# Bad\n")
    reg = SkillsRegistry(tmp_path)
    reg.load()
    assert reg.get("bad..name") is None


def test_anthropic_managed_skills_present(tmp_path):
    # ANTHROPIC_MANAGED_SKILLS entries load regardless of disk
    reg = SkillsRegistry(tmp_path)
    reg.load()
    assert any(s["source"] == "anthropic" for s in reg.list())
    # managed entries have no on-disk path
    for s in reg.list():
        if s["source"] == "anthropic":
            assert s["path"] == ""


def test_plugin_skill_loaded_via_plugin_dir(monkeypatch, tmp_path):
    plugin_dir = tmp_path / "myplugin"
    skill_dir = plugin_dir / "skills" / "pskill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Plugin Skill\n")

    def fake_load():
        return [
            {
                "name": "pskill",
                "path": str(skill_dir / "SKILL.md"),
                "plugin": "myplugin",
                "plugin_dir": str(plugin_dir),
            }
        ]

    monkeypatch.setattr("zcoder.claude.tools.plugins.load_plugin_skills", fake_load)
    reg = SkillsRegistry(tmp_path)
    reg.load()
    key = "myplugin:pskill"
    assert reg.get(key) is not None
    assert reg.get(key)["source"] == "plugin:myplugin"
    assert reg.get(key)["description"] == "Plugin Skill"


def test_plugin_skill_symlink_escape_rejected(monkeypatch, tmp_path):
    plugin_dir = tmp_path / "myplugin"
    skill_dir = plugin_dir / "skills" / "evil"
    skill_dir.mkdir(parents=True)
    secret = tmp_path / "secret.txt"
    secret.write_text("PLUGIN_TOP_SECRET\n")
    (skill_dir / "SKILL.md").symlink_to(secret)

    def fake_load():
        return [
            {
                "name": "evil",
                "path": str(skill_dir / "SKILL.md"),
                "plugin": "myplugin",
                "plugin_dir": str(plugin_dir),
            }
        ]

    monkeypatch.setattr("zcoder.claude.tools.plugins.load_plugin_skills", fake_load)
    reg = SkillsRegistry(tmp_path)
    reg.load()
    assert reg.get("myplugin:evil") is None


def test_read_skill_unit_containment(tmp_path):
    good = tmp_path / "good.md"
    good.write_text("# ok\n")
    assert SkillsRegistry._read_skill(good, tmp_path) == "# ok\n"

    # symlink to a target outside the base dir must be rejected
    outside = tmp_path.parent / "outside_secret.txt"
    outside.write_text("OUTSIDE_LEAK\n")
    outside_link = tmp_path / "outside.md"
    outside_link.symlink_to(outside)
    assert SkillsRegistry._read_skill(outside_link, tmp_path) is None

    # oversized file must be rejected
    huge = tmp_path / "huge.md"
    huge.write_text("X" * (300 * 1024))
    assert SkillsRegistry._read_skill(huge, tmp_path) is None
