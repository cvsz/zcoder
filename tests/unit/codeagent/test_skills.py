"""Tests for the Skills system (.claude/skills/<name>/SKILL.md)."""

from __future__ import annotations

from pathlib import Path

import pytest

from zcoder.agent.codeagent.commands import command_names, dispatch
from zcoder.agent.codeagent.skills import (
    Skill,
    SkillRegistry,
    inject_dynamic_context,
    render_skill,
)


class TestFrontmatterParsing:
    def test_parse_valid_frontmatter(self):
        text = """---
name: my-skill
description: Does something useful
when_to_use: When you need to do something
disable-model-invocation: true
user-invocable: false
arguments: [issue, format]
allowed-tools: Read Grep
disallowed-tools: Write Edit
model: sonnet
effort: high
context: fork
background: true
paths: ["src/*.py", "tests/*.py"]
shell: bash
license: MIT
compatibility: Python >=3.12
---

This is the skill body with `` !`git diff` `` dynamic content.
"""
        data, body = __import__("zcoder.agent.codeagent.skills", fromlist=["_parse_frontmatter"])._parse_frontmatter(text)
        assert data["name"] == "my-skill"
        assert data["description"] == "Does something useful"
        assert data["when_to_use"] == "When you need to do something"
        assert data["disable-model-invocation"] is True
        assert data["user-invocable"] is False
        assert data["arguments"] == ["issue", "format"]
        assert data["allowed-tools"] == ["Read", "Grep"]
        assert data["disallowed-tools"] == ["Write", "Edit"]
        assert data["model"] == "sonnet"
        assert data["effort"] == "high"
        assert data["context"] == "fork"
        assert data["background"] is True
        assert data["paths"] == ["src/*.py", "tests/*.py"]
        assert data["shell"] == "bash"
        assert data["license"] == "MIT"
        assert data["compatibility"] == "Python >=3.12"
        assert "This is the skill body" in body

    def test_no_frontmatter(self):
        text = "Just plain markdown content."
        from zcoder.agent.codeagent.skills import _parse_frontmatter

        data, body = _parse_frontmatter(text)
        assert data == {}
        assert body == text

    def test_frontmatter_not_first_line(self):
        text = "some text\n---\nname: x\n---\nbody"
        from zcoder.agent.codeagent.skills import _parse_frontmatter

        data, body = _parse_frontmatter(text)
        assert data == {}
        assert body == text


class TestSkillConstruction:
    def test_skill_defaults(self):
        skill = Skill(name="test-skill", description="A test skill")
        assert skill.name == "test-skill"
        assert skill.description == "A test skill"
        assert skill.disable_model_invocation is False
        assert skill.user_invocable is True
        assert skill.context == "inline"
        assert skill.background is True
        assert skill.shell == "bash"
        assert skill.command_name() == "test-skill"

    def test_full_listing_truncation(self):
        skill = Skill(
            name="long-skill",
            description="A" * 2000,
        )
        listing = skill.full_listing()
        assert len(listing) <= 1536


class TestDynamicContextInjection:
    def test_inline_dynamic_block(self):
        body = "Current diff: `` !`echo hello` `` end."
        result = inject_dynamic_context(body, Path.cwd())
        assert "hello" in result
        assert "!`echo hello`" not in result

    def test_fenced_dynamic_block(self):
        body = "Files:\n```!\nls\n```\nEnd."
        result = inject_dynamic_context(body, Path.cwd())
        assert "End." in result
        # Should contain some file listing
        assert "```!" not in result

    def test_no_dynamic_blocks(self):
        body = "Just plain text with no commands."
        result = inject_dynamic_context(body, Path.cwd())
        assert result == body

    def test_command_failure(self):
        body = "Result: `` !`nonexistent_command_xyz123` `` end."
        result = inject_dynamic_context(body, Path.cwd())
        assert "command failed" in result or "command error" in result or "command timed out" in result


class TestSkillRegistry:
    def test_discover_empty(self, tmp_path):
        skills_dir = tmp_path / ".claude" / "skills"
        skills_dir.mkdir(parents=True)
        registry = SkillRegistry(tmp_path, home=tmp_path / ".home")
        # Override dirs to use tmp_path
        registry.cwd = tmp_path
        registry.home = tmp_path / ".home"
        registry.discover()
        assert registry.list_all() == {}

    def test_discover_project_skill(self, tmp_path):
        skills_dir = tmp_path / ".claude" / "skills" / "summarize"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text(
            """---
name: summarize
description: Summarize uncommitted changes
---

Current changes:

!`git diff HEAD`
"""
        )
        registry = SkillRegistry(tmp_path, home=tmp_path / ".home")
        registry.cwd = tmp_path
        registry.home = tmp_path / ".home"
        registry.discover()
        assert "summarize" in registry.list_all()
        skill = registry.get("summarize")
        assert skill is not None
        assert skill.description == "Summarize uncommitted changes"
        assert skill.scope == "project"

    def test_name_conflict_higher_scope_wins(self, tmp_path):
        # Personal skill
        personal_dir = tmp_path / ".home" / ".claude" / "skills" / "deploy"
        personal_dir.mkdir(parents=True)
        (personal_dir / "SKILL.md").write_text(
            """---
name: deploy
description: Personal deploy skill
---
Personal deploy body
"""
        )
        # Project skill (lower priority)
        project_dir = tmp_path / ".claude" / "skills" / "deploy"
        project_dir.mkdir(parents=True)
        (project_dir / "SKILL.md").write_text(
            """---
name: deploy
description: Project deploy skill
---
Project deploy body
"""
        )
        registry = SkillRegistry(tmp_path, home=tmp_path / ".home")
        registry.cwd = tmp_path
        registry.home = tmp_path / ".home"
        registry.discover()
        skill = registry.get("deploy")
        assert skill is not None
        assert skill.description == "Personal deploy skill"
        assert skill.scope == "personal"

    def test_skip_invalid_skill(self, tmp_path):
        skills_dir = tmp_path / ".claude" / "skills" / "bad"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text("No frontmatter, no body content really.\n")
        registry = SkillRegistry(tmp_path, home=tmp_path / ".home")
        registry.cwd = tmp_path
        registry.home = tmp_path / ".home"
        registry.discover()
        assert "bad" not in registry.list_all()

    def test_eligible_for_context(self, tmp_path):
        skills_dir = tmp_path / ".claude" / "skills" / "pythonskill"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text(
            """---
name: pythonskill
description: Python-specific skill
paths: ["src/*.py"]
---

Python skill body
"""
        )
        registry = SkillRegistry(tmp_path, home=tmp_path / ".home")
        registry.cwd = tmp_path
        registry.home = tmp_path / ".home"
        registry.discover()
        # No src/*.py files exist, so not eligible
        eligible = registry.eligible_for_context(tmp_path)
        assert "pythonskill" not in eligible

        # Create a matching file
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("x = 1\n")
        eligible = registry.eligible_for_context(tmp_path)
        assert "pythonskill" in eligible

    def test_get_nonexistent(self, tmp_path):
        registry = SkillRegistry(tmp_path, home=tmp_path / ".home")
        registry.cwd = tmp_path
        registry.home = tmp_path / ".home"
        registry.discover()
        assert registry.get("nonexistent") is None


class TestRenderSkill:
    def test_render_basic(self, tmp_path):
        skill = Skill(
            name="greet",
            description="Greets the user",
            body="Hello, $1! Welcome to ${CLAUDE_PROJECT_DIR}.",
        )
        rendered = render_skill(skill, ["Alice"], tmp_path)
        assert "Hello, Alice!" in rendered
        assert str(tmp_path) in rendered
        assert "# Skill: greet" in rendered

    def test_render_no_args(self):
        skill = Skill(
            name="plain",
            description="A plain skill",
            body="Just some content.",
        )
        rendered = render_skill(skill, [], Path.cwd())
        assert "Just some content." in rendered


class TestSkillCommands:
    @pytest.mark.asyncio
    async def test_skills_lists_registered(self, make_agent_with_skills):
        agent = make_agent_with_skills()
        result = await dispatch(agent, "/skills")
        assert not result.is_error
        assert "/skills" in command_names()

    @pytest.mark.asyncio
    async def test_skill_invocation_returns_prompt(self, make_agent_with_skills):
        agent = make_agent_with_skills()
        result = await dispatch(agent, "/skill summarize")
        assert result.action == "prompt"
        assert result.prompt is not None
        assert "# Skill: summarize" in result.prompt

    @pytest.mark.asyncio
    async def test_skill_not_found(self, make_agent_with_skills):
        agent = make_agent_with_skills()
        result = await dispatch(agent, "/skill nonexistent")
        assert result.is_error
        assert "not found" in result.output


@pytest.fixture
def make_agent_with_skills():
    def _make():
        import tempfile

        from zcoder.agent.codeagent.llm import LocalLLM
        from zcoder.agent.codeagent.permissions import PermissionPolicy
        from zcoder.agent.codeagent.sessions import SessionStore
        from zcoder.agent.codeagent.workspace import Workspace

        tmp = Path(tempfile.mkdtemp())
        ws = Workspace(tmp)
        llm = LocalLLM()
        policy = PermissionPolicy(workspace=ws)
        from zcoder.agent.codeagent.loop import CodeAgent

        agent = CodeAgent(llm, ws, policy=policy, store=SessionStore(), memory=[])
        agent.skills = SkillRegistry(tmp)
        agent.skills.discover()
        # Register a test skill directly
        agent.skills._skills["summarize"] = Skill(
            name="summarize",
            description="Summarize uncommitted changes",
            body="Current changes:\n!`git diff HEAD`\n",
            scope="project",
        )
        agent.skills._sources["summarize"] = "project"
        return agent

    return _make
