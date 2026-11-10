"""Skills — .claude/skills/<name>/SKILL.md loader with dynamic context injection.

Skills are the Claude Code extension mechanism: a SKILL.md file with YAML
frontmatter plus Markdown body. The body can contain dynamic context blocks
(`` !`command` `` and fenced `` ```! ` `` blocks) whose shell output is
injected before Claude reads the skill. Skills are invoked with /<name>
or auto-loaded by Claude when relevant (unless disable-model-invocation).

zcoder runs entirely on loopback local inference — no hosted model calls.
"""

from __future__ import annotations

import fnmatch
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Frontmatter fields that accept a list (space/comma-separated or YAML list)
_LIST_FIELDS = {"arguments", "allowed-tools", "disallowed-tools", "paths"}

# Bounded scan for skill_matches_paths — keeps discovery cheap on large repos.
_SKILL_SCAN_LIMIT = 4096


@dataclass
class Skill:
    """A single skill loaded from SKILL.md."""

    name: str
    description: str = ""
    when_to_use: str = ""
    argument_hint: str | None = None
    arguments: list[str] = field(default_factory=list)
    disable_model_invocation: bool = False
    user_invocable: bool = True
    allowed_tools: list[str] = field(default_factory=list)
    disallowed_tools: list[str] = field(default_factory=list)
    model: str = "inherit"
    effort: str = "inherit"
    context: str = "inline"  # inline | fork
    agent: str | None = None
    background: bool = True
    hooks: list[dict[str, Any]] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    shell: str = "bash"
    metadata: dict[str, Any] = field(default_factory=dict)
    license: str | None = None
    compatibility: str | None = None
    body: str = ""
    source: str = ""  # filesystem path to SKILL.md
    scope: str = ""  # personal | project | enterprise | plugin | added-dir

    def command_name(self) -> str:
        """The /<name> used to invoke this skill."""
        return self.name

    def full_listing(self) -> str:
        """One-line listing for /skills menu (truncated to 1536 chars)."""
        text = f"{self.description}"
        if self.when_to_use:
            text += f" {self.when_to_use}"
        return text[:1536]


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "on", "1"}
    return bool(value)


def _parse_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [p.strip() for p in re.split(r"[\s,]+", value) if p.strip()]
    return [str(value).strip()] if str(value).strip() else []


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split SKILL.md into (frontmatter_dict, body). Returns ({}, text) if no
    valid frontmatter block (opening --- must be the very first line)."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text
    fm_text = text[4:end]
    body = text[end + 4 :]
    if body.startswith("\n"):
        body = body[1:]
    data: dict[str, Any] = {}
    for line in fm_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            data[key] = [p.strip().strip('"').strip("'") for p in inner.split(",") if p.strip()] if inner else []
        elif key in _LIST_FIELDS:
            data[key] = _parse_list(val)
        elif key in {"disable-model-invocation", "user-invocable", "background"}:
            data[key] = _parse_bool(val)
        else:
            data[key] = val.strip('"').strip("'")
    return data, body


_DYNAMIC_RX = re.compile(r"!`([^`]+)`")


def _run_dynamic(command: str, cwd: Path, shell: str = "bash", timeout: int = 30) -> str:
    """Run a shell command and return its stdout, or an error marker."""
    try:
        bin_sh = "/bin/bash" if shell == "bash" and os.path.exists("/bin/bash") else "/bin/sh"
        r = subprocess.run(
            [bin_sh, "-c", command],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if r.returncode != 0:
            return f"[command failed: {r.stderr.strip()[:200]}]"
        return r.stdout
    except subprocess.TimeoutExpired:
        return "[command timed out]"
    except OSError as exc:
        return f"[command error: {exc}]"


def inject_dynamic_context(body: str, cwd: Path, shell: str = "bash") -> str:
    """Replace `` !`command` `` inline blocks and fenced `` ```! ` `` blocks
    with their shell output. Everything else passes through unchanged."""

    def repl(m: re.Match[str]) -> str:
        return _run_dynamic(m.group(1), cwd, shell)

    out = _DYNAMIC_RX.sub(repl, body)

    # Fenced dynamic blocks: ```! ... ```
    fenced_rx = re.compile(r"```!\s*\n(.*?)\n```", re.DOTALL)

    def fenced_repl(m: re.Match[str]) -> str:
        return _run_dynamic(m.group(1).strip(), cwd, shell)

    out = fenced_rx.sub(fenced_repl, out)
    return out


def _glob_match(pattern: str, path: Path, base: Path) -> bool:
    try:
        rel = str(path.relative_to(base))
    except ValueError:
        rel = str(path)
    return fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(path.name, pattern)


def skill_matches_paths(skill: Skill, cwd: Path) -> bool:
    """True when the skill's `paths` globs match anything under cwd, or when
    no paths are configured (skill always eligible)."""
    if not skill.paths:
        return True
    if not cwd.exists():
        return False
    # Bounded scan: stop after _SKILL_SCAN_LIMIT files so a huge repo does not
    # stall skill discovery on every prompt.
    scanned = 0
    for p in cwd.rglob("*"):
        scanned += 1
        if scanned > _SKILL_SCAN_LIMIT:
            break
        if any(_glob_match(pattern, p, cwd) for pattern in skill.paths):
            return True
    return False


class SkillRegistry:
    """Discovers and loads skills from filesystem locations.

    Search order (highest priority first): enterprise, personal, project,
    then added directories and plugins. Project skills walk up from cwd to
    the repository root.
    """

    def __init__(self, cwd: Path, home: Path | None = None):
        self.cwd = Path(cwd).resolve()
        self.home = Path(home or Path.home()).resolve()
        self._skills: dict[str, Skill] = {}
        self._sources: dict[str, str] = {}  # name -> scope label

    # --- discovery ---------------------------------------------------------

    def discover(self) -> None:
        """Load all skills from known locations."""
        self._skills.clear()
        self._sources.clear()

        # Enterprise (managed) — highest priority
        for skill in self._scan(self._enterprise_dir(), "enterprise"):
            self._register(skill, "enterprise")

        # Personal — overrides project
        for skill in self._scan(self._personal_dir(), "personal"):
            self._register(skill, "personal")

        # Project — walks up from cwd to root
        for d in [self.cwd, *self.cwd.parents]:
            if d == self.home:
                break
            skills_dir = d / ".claude" / "skills"
            for skill in self._scan(skills_dir, "project"):
                self._register(skill, "project")

    def _register(self, skill: Skill, scope: str) -> None:
        """Register a skill; higher-priority scopes win on name conflicts."""
        if skill.name in self._skills:
            return  # already registered by a higher-priority scope
        self._skills[skill.name] = skill
        self._sources[skill.name] = scope

    def _enterprise_dir(self) -> Path:
        # Enterprise/managed settings live in a system directory, separate
        # from the personal ~/.claude/skills directory.
        env_dir = os.getenv("CLAUDE_CONFIG_DIR")
        if env_dir:
            return Path(env_dir) / "skills"
        return Path("/etc/claude-code/.claude/skills")

    def _personal_dir(self) -> Path:
        return self.home / ".claude" / "skills"

    def _scan(self, skills_dir: Path, scope: str) -> list[Skill]:
        skills: list[Skill] = []
        if not skills_dir.is_dir():
            return skills
        for entry in sorted(skills_dir.iterdir()):
            if not entry.is_dir():
                continue
            skill_md = entry / "SKILL.md"
            if not skill_md.is_file():
                continue
            try:
                text = skill_md.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            data, body = _parse_frontmatter(text)
            name = data.get("name") or entry.name
            if not name or name.startswith("-") or ":" in name or len(name) > 256:
                continue
            # Require valid frontmatter (opening --- must be the first line)
            if not text.startswith("---\n"):
                continue
            if not data.get("description") and not body.strip():
                continue
            skill = Skill(
                name=name,
                description=str(data.get("description", "")),
                when_to_use=str(data.get("when_to_use", "")),
                argument_hint=data.get("argument-hint"),
                arguments=_parse_list(data.get("arguments")),
                disable_model_invocation=_parse_bool(data.get("disable-model-invocation", False)),
                user_invocable=_parse_bool(data.get("user-invocable", True)),
                allowed_tools=_parse_list(data.get("allowed-tools")),
                disallowed_tools=_parse_list(data.get("disallowed-tools")),
                model=str(data.get("model", "inherit")),
                effort=str(data.get("effort", "inherit")),
                context=str(data.get("context", "inline")),
                agent=data.get("agent"),
                background=_parse_bool(data.get("background", True)),
                hooks=data.get("hooks", []) if isinstance(data.get("hooks"), list) else [],
                paths=_parse_list(data.get("paths")),
                shell=str(data.get("shell", "bash")),
                metadata=data.get("metadata", {}) if isinstance(data.get("metadata"), dict) else {},
                license=data.get("license"),
                compatibility=data.get("compatibility"),
                body=body,
                source=str(skill_md),
                scope=scope,
            )
            skills.append(skill)
        return skills

    # --- access ------------------------------------------------------------

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def list_all(self) -> dict[str, Skill]:
        return dict(self._skills)

    def eligible_for_context(self, cwd: Path | None = None) -> dict[str, Skill]:
        """Skills that may auto-activate in the current directory (paths match)."""
        cwd = cwd or self.cwd
        return {
            name: skill
            for name, skill in self._skills.items()
            if not skill.disable_model_invocation and skill_matches_paths(skill, cwd)
        }

    def reload(self) -> None:
        self.discover()


def _expand_substitutions(text: str, args: list[str], cwd: Path) -> str:
    """Replace $name with positional argument values and ${CLAUDE_PROJECT_DIR}."""
    out = text
    for i, arg in enumerate(args, start=1):
        out = out.replace(f"${i}", arg)
    out = out.replace("${CLAUDE_PROJECT_DIR}", str(cwd))
    out = out.replace("${CLAUDE_SESSION_ID}", "")
    return out


def render_skill(skill: Skill, args: list[str] | None = None, cwd: Path | None = None) -> str:
    """Render a skill's body with dynamic context injected and argument
    substitutions applied. Returns the full text Claude should see."""
    cwd = cwd or Path.cwd()
    body = inject_dynamic_context(skill.body, cwd, skill.shell)
    args = args or []
    body = _expand_substitutions(body, args, cwd)
    header = f"# Skill: {skill.name}"
    if skill.description:
        header += f"\n{skill.description}"
    if args:
        header += f"\nArguments: {', '.join(args)}"
    return f"{header}\n\n{body}"
