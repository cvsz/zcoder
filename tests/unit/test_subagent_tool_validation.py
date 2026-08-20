"""Regression tests for Slice E.8 — subagent frontmatter tool validation."""

from pathlib import Path

from zcoder.claude.capabilities.code import SubagentRegistry


def _write_agent(root: Path, name: str, frontmatter: str, body: str = "You are an agent.\n") -> Path:
    f = root / f"{name}.md"
    f.write_text(f"---\n{frontmatter}\n---\n{body}")
    return f


def test_valid_tools_all_ok(tmp_path):
    _write_agent(tmp_path, "ok", "tools: all")
    reg = SubagentRegistry(tmp_path)
    reg.load()
    assert reg.get("ok") is not None
    assert reg.get("ok")["tools"] == "all"


def test_valid_tool_list_ok(tmp_path):
    _write_agent(tmp_path, "ok", "tools: Read, Write, Edit")
    reg = SubagentRegistry(tmp_path)
    reg.load()
    assert reg.get("ok") is not None
    assert "Read" in reg.get("ok")["tools"]


def test_unknown_tool_rejected(tmp_path):
    _write_agent(tmp_path, "bad", "tools: FakeTool")
    reg = SubagentRegistry(tmp_path)
    reg.load()
    assert reg.get("bad") is None


def test_unknown_tool_in_list_rejected(tmp_path):
    _write_agent(tmp_path, "bad", "tools: Read, FakeTool, Write")
    reg = SubagentRegistry(tmp_path)
    reg.load()
    assert reg.get("bad") is None


def test_mcp_tool_prefix_accepted(tmp_path):
    _write_agent(tmp_path, "ok", "tools: mcp__server__tool")
    reg = SubagentRegistry(tmp_path)
    reg.load()
    assert reg.get("ok") is not None


def test_disallowed_unknown_tool_rejected(tmp_path):
    _write_agent(tmp_path, "bad", "disallowedTools: FakeDisallowed")
    reg = SubagentRegistry(tmp_path)
    reg.load()
    assert reg.get("bad") is None


def test_disallowed_known_tool_accepted(tmp_path):
    _write_agent(tmp_path, "ok", "disallowedTools: Bash")
    reg = SubagentRegistry(tmp_path)
    reg.load()
    assert reg.get("ok") is not None
