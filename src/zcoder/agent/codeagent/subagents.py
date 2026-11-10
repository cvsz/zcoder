"""Subagents — isolated agents that run in their own context and return summaries.

Subagents are specialized AI assistants that handle specific tasks in isolation.
They run in their own context window with a custom system prompt, specific tool
access, and independent permissions. When done, they return a summary to the
parent conversation.

Built-in subagents (Claude Code-compatible):
  Explore      — read-only codebase research (no Write/Edit)
  Plan         — read-only research for plan mode
  General      — general-purpose agent with full tool access
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass  # CodeAgent imported lazily at runtime to avoid circular import

from zcoder.agent.codeagent.llm import LLM
from zcoder.agent.codeagent.permissions import Mode, PermissionPolicy
from zcoder.agent.codeagent.sessions import SessionStore
from zcoder.agent.codeagent.workspace import Workspace

_AGENT_FRONTMATTER_RX = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)

# Depth limit: subagents cannot spawn subagents beyond this depth.
SUBAGENT_DEPTH_LIMIT = 5

# Tools removed from every subagent (Claude Code-compatible).
_SUBAGENT_HARD_DENY = frozenset(
    {
        "Agent",
        "AskUserQuestion",
        "EndConversation",
        "EnterPlanMode",
        "ScheduleWakeup",
        "WaitForMcpServers",
        "Workflow",
    }
)

# Tools a background subagent keeps (all others removed).
_BACKGROUND_SUBAGENT_TOOLS = frozenset(
    {
        "Read",
        "Grep",
        "Glob",
        "LSP",
        "Bash",
        "PowerShell",
        "Edit",
        "Write",
        "NotebookEdit",
        "WebFetch",
        "WebSearch",
        "TodoWrite",
        "Skill",
        "ToolSearch",
        "EnterWorktree",
        "ExitWorktree",
        "Monitor",
        "TaskStop",
        "SendMessage",
        "Artifact",
    }
)


@dataclass
class SubagentDef:
    """A subagent definition loaded from .claude/agents/<name>.md."""

    name: str
    description: str
    prompt: str
    tools: list[str] = field(default_factory=list)
    disallowed_tools: list[str] = field(default_factory=list)
    model: str = "inherit"
    permission_mode: str = "default"
    max_turns: int | None = None
    skills: list[str] = field(default_factory=list)
    mcp_servers: list[str] = field(default_factory=list)
    hooks: list[dict[str, Any]] = field(default_factory=list)
    memory: str = "local"
    background: bool = True
    omit_claude_md: bool = False
    effort: str = "inherit"
    isolation: str | None = None
    color: str | None = None
    initial_prompt: str | None = None
    source: str = ""
    scope: str = "project"


@dataclass
class SubagentResult:
    """The result returned by a subagent to its parent."""

    agent_type: str
    summary: str
    success: bool
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tokens_used: int = 0


class SubagentRegistry:
    """Discovers and loads subagent definitions from filesystem locations."""

    def __init__(self, cwd: Path, home: Path | None = None):
        self.cwd = Path(cwd).resolve()
        self.home = Path(home or Path.home()).resolve()
        self._agents: dict[str, SubagentDef] = {}

    def discover(self) -> None:
        self._agents.clear()
        # Project agents walk up from cwd to root
        for d in [self.cwd, *self.cwd.parents]:
            if d == self.home:
                break
            agents_dir = d / ".claude" / "agents"
            for agent in self._scan(agents_dir, "project"):
                self._register(agent, "project")
        # Personal agents
        for agent in self._scan(self.home / ".claude" / "agents", "personal"):
            self._register(agent, "personal")

    def _register(self, agent: SubagentDef, scope: str) -> None:
        if agent.name in self._agents:
            return
        self._agents[agent.name] = agent
        agent.scope = scope

    def _scan(self, agents_dir: Path, scope: str) -> list[SubagentDef]:
        agents: list[SubagentDef] = []
        if not agents_dir.is_dir():
            return agents
        for entry in sorted(agents_dir.iterdir()):
            if not entry.is_file() or entry.suffix != ".md":
                continue
            try:
                text = entry.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            m = _AGENT_FRONTMATTER_RX.match(text)
            if not m:
                continue
            fm_text, body = m.group(1), m.group(2)
            data: dict[str, Any] = {}
            for line in fm_text.splitlines():
                line = line.strip()
                if not line or ":" not in line:
                    continue
                key, _, val = line.partition(":")
                key = key.strip()
                val = val.strip()
                if key in {"tools", "disallowedTools", "skills", "mcpServers", "hooks"}:
                    data[key] = [p.strip() for p in val.split(",") if p.strip()] if val else []
                elif key in {"maxTurns"}:
                    try:
                        data[key] = int(val)
                    except ValueError:
                        pass
                elif key in {"background", "omitClaudeMd"}:
                    data[key] = val.lower() in {"true", "yes", "on", "1"}
                else:
                    data[key] = val
            name = data.get("name") or entry.stem
            if not name or name.startswith("-") or ":" in name or len(name) > 256:
                continue
            if not data.get("description") or not body.strip():
                continue
            agents.append(
                SubagentDef(
                    name=name,
                    description=str(data.get("description", "")),
                    prompt=body.strip(),
                    tools=[t.strip() for t in data.get("tools", []) if t.strip()],
                    disallowed_tools=[t.strip() for t in data.get("disallowedTools", []) if t.strip()],
                    model=str(data.get("model", "inherit")),
                    permission_mode=str(data.get("permissionMode", "default")),
                    max_turns=data.get("maxTurns"),
                    skills=data.get("skills", []),
                    mcp_servers=data.get("mcpServers", []),
                    hooks=data.get("hooks", []),
                    memory=str(data.get("memory", "local")),
                    background=bool(data.get("background", True)),
                    omit_claude_md=bool(data.get("omitClaudeMd", False)),
                    effort=str(data.get("effort", "inherit")),
                    isolation=data.get("isolation"),
                    color=data.get("color"),
                    initial_prompt=data.get("initialPrompt"),
                    source=str(entry),
                    scope=scope,
                )
            )
        return agents

    def get(self, name: str) -> SubagentDef | None:
        return self._agents.get(name)

    def list_all(self) -> dict[str, SubagentDef]:
        return dict(self._agents)


class SubagentRunner:
    """Spawns and runs subagents in isolated context."""

    def __init__(
        self,
        llm: LLM,
        ws: Workspace,
        policy: PermissionPolicy,
        registry: SubagentRegistry,
        depth: int = 0,
    ):
        self.llm = llm
        self.ws = ws
        self.policy = policy
        self.registry = registry
        self.depth = depth

    async def run(
        self,
        agent_type: str,
        prompt: str,
        tools: list[str] | None = None,
        model: str | None = None,
        permission_mode: str | None = None,
        max_turns: int | None = None,
    ) -> SubagentResult:
        """Run a subagent and return its summary."""
        if self.depth >= SUBAGENT_DEPTH_LIMIT:
            return SubagentResult(
                agent_type=agent_type,
                summary="",
                success=False,
            )

        defn = self.registry.get(agent_type)
        if defn is None:
            # Fall back to general-purpose
            defn = SubagentDef(
                name=agent_type,
                description="",
                prompt=prompt,
                tools=tools or [],
                model=model or "inherit",
            )

        # Build isolated workspace (same root, fresh context)
        sub_ws = Workspace(self.ws.root)

        # Determine tool set
        available = list(self.policy.allow_rules) if tools is None else list(tools)
        if defn.tools:
            available = list(defn.tools)
        # Remove hard-denied tools
        available = [t for t in available if t not in _SUBAGENT_HARD_DENY]
        # Remove disallowed
        for d in defn.disallowed_tools:
            available = [t for t in available if t != d]

        # Build permission policy
        sub_policy = PermissionPolicy(workspace=sub_ws)
        sub_policy.mode = Mode(permission_mode or defn.permission_mode or "default")

        # Create isolated agent
        import importlib

        loop_mod = importlib.import_module("zcoder.agent.codeagent.loop")
        CodeAgent = loop_mod.CodeAgent

        agent = CodeAgent(
            self.llm,
            sub_ws,
            policy=sub_policy,
            store=SessionStore(),
            memory=[],
            context_window=32768,
            max_steps=max_turns or defn.max_turns or 10,
        )

        # Fire SubagentStart hook if available
        # (hooks would be passed from parent; omitted here for simplicity)

        full_prompt = f"{defn.initial_prompt + '\n\n' if defn.initial_prompt else ''}{prompt}"

        events = [e async for e in agent.run(full_prompt)]

        # Collect summary from text events
        parts: list[str] = []
        for ev in events:
            text = getattr(ev, "text", None)
            if isinstance(text, str) and text:
                parts.append(text)
        summary = "\n".join(parts).strip() or "Subagent completed with no output."

        return SubagentResult(
            agent_type=agent_type,
            summary=summary,
            success=True,
        )


# --- Built-in subagents ----------------------------------------------------

BUILTIN_SUBAGENTS: dict[str, SubagentDef] = {
    "Explore": SubagentDef(
        name="Explore",
        description="Fast, read-only agent optimized for searching and analyzing codebases",
        prompt="""You are Explore, a fast, read-only codebase research agent. Your job is to search and understand
the codebase without making changes. Use Read, Grep, Glob, and LS to investigate. Return a concise summary
of your findings including relevant file paths and line numbers. Do not attempt any file edits or shell commands
that modify files.""",
        tools=["Read", "Grep", "Glob", "LS"],
        model="inherit",
        permission_mode="default",
        background=True,
    ),
    "Plan": SubagentDef(
        name="Plan",
        description="Research agent used during plan mode to gather context before presenting a plan",
        prompt="""You are Plan, a research agent used during plan mode. Gather context about the codebase
to help the user form a plan. You may only read and search files. Return a concise summary of your findings
with specific file references.""",
        tools=["Read", "Grep", "Glob", "LS"],
        model="inherit",
        permission_mode="plan",
        background=True,
    ),
    "General": SubagentDef(
        name="General",
        description="General-purpose agent for complex multi-step tasks",
        prompt="""You are a general-purpose subagent. Handle the delegated task autonomously using your available
tools. Return a concise summary of what you did and any results.""",
        tools=[],
        model="inherit",
        permission_mode="default",
        background=True,
    ),
}
