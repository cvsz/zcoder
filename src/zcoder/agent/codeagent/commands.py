"""Slash commands shared by every front end. Pure logic; returns data, never renders."""

from __future__ import annotations

import subprocess  # nosec B404 - fixed read-only git invocations
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from zcoder.agent.codeagent.llm import LLMError
from zcoder.agent.codeagent.loop import CodeAgent
from zcoder.agent.codeagent.permissions import Mode
from zcoder.agent.codeagent.workspace import ToolError


@dataclass
class CommandResult:
    output: str = ""
    action: str | None = None  # clear | exit | prompt | resumed | mode
    prompt: str | None = None  # text to send to the model when action == "prompt"
    is_error: bool = False


@dataclass
class Command:
    name: str
    help: str
    run: Callable[[CodeAgent, str], Awaitable[CommandResult]]
    usage: str = ""


_REGISTRY: dict[str, Command] = {}
_ALIASES = {
    "new": "clear",
    "reset": "clear",
    "quit": "exit",
    "q": "exit",
    "h": "help",
    "?": "help",
    "rewind": "undo",
}


def command(name: str, help_text: str, usage: str = ""):
    def deco(fn):
        _REGISTRY[name] = Command(name, help_text, fn, usage)
        return fn

    return deco


def list_commands() -> list[Command]:
    return sorted(_REGISTRY.values(), key=lambda c: c.name)


def command_names() -> list[str]:
    return [f"/{c.name}" for c in list_commands()]


async def dispatch(agent: CodeAgent, line: str) -> CommandResult:
    name, _, arg = line.strip().lstrip("/").partition(" ")
    name = _ALIASES.get(name.lower(), name.lower())
    cmd = _REGISTRY.get(name)
    if cmd is None:
        return CommandResult(f"Unknown command /{name}. Type /help.", is_error=True)
    return await cmd.run(agent, arg.strip())


def _git(agent: CodeAgent, *args: str) -> str:
    try:
        r = subprocess.run(
            ["git", *args], cwd=agent.ws.root, capture_output=True, text=True, timeout=10, check=False
        )  # nosec B603 B607
    except (OSError, subprocess.SubprocessError) as exc:
        return f"git failed: {exc}"
    return (r.stdout or r.stderr).strip()


@command("help", "Show available commands")
async def _help(agent, arg):
    rows = [f"/{c.name}{(' ' + c.usage) if c.usage else ''} — {c.help}" for c in list_commands()]
    return CommandResult(
        "\n".join(rows) + "\n\n@path attaches a file · Shift+Tab cycles permission mode · Esc interrupts"
    )


@command("clear", "Start a new conversation (aliases: /new, /reset)")
async def _clear(agent, arg):
    agent.clear()
    return CommandResult("New conversation started.", action="clear")


@command("compact", "Summarize history to free context", "[focus]")
async def _compact(agent, arg):
    try:
        before = agent.estimate_tokens()
        await agent.compact(arg)
        return CommandResult(f"Compacted: ~{before} → ~{agent.estimate_tokens()} tokens.")
    except LLMError as exc:
        return CommandResult(str(exc), is_error=True)


@command("mode", "Show or set permission mode", "[default|acceptEdits|plan|bypass]")
async def _mode(agent, arg):
    if not arg:
        return CommandResult(f"Mode: {agent.mode.value}")
    try:
        agent.policy.set_mode(
            Mode(
                arg
                if arg in {m.value for m in Mode}
                else {"accept": "acceptEdits", "acceptedits": "acceptEdits"}.get(arg.lower(), arg)
            )
        )
    except (ValueError, ToolError) as exc:
        return CommandResult(f"{exc}", is_error=True)
    return CommandResult(f"Mode set to {agent.mode.value}.", action="mode")


@command("plan", "Toggle plan mode (read-only research, then approve a plan)")
async def _plan(agent, arg):
    agent.policy.set_mode(Mode.DEFAULT if agent.mode == Mode.PLAN else Mode.PLAN)
    return CommandResult(f"Mode set to {agent.mode.value}.", action="mode")


@command("model", "Show the loaded model")
async def _model(agent, arg):
    return CommandResult(f"Model: {agent.llm.model} (llama-server serves one GGUF; restart it to switch).")


@command("cost", "Show token usage for this session")
async def _cost(agent, arg):
    u = agent.usage
    return CommandResult(
        f"Requests: {u.requests} · prompt tokens: {u.prompt_tokens} · completion tokens: {u.completion_tokens} · "
        f"context ≈ {agent.estimate_tokens()}/{agent.context_window} · cost: $0.00 (local)"
    )


@command("todos", "Show the current task list")
async def _todos(agent, arg):
    icon = {"pending": "☐", "in_progress": "◐", "completed": "☑"}
    rows = [f"{icon[t['status']]} {t['content']}" for t in agent.todos]
    return CommandResult("\n".join(rows) or "No todos.")


@command("diff", "Show uncommitted git changes")
async def _diff(agent, arg):
    out = _git(agent, "diff", "--stat") + "\n\n" + _git(agent, "diff")[:20_000]
    return CommandResult(out.strip() or "No changes.")


@command("undo", "Revert the file changes from the last turn (alias: /rewind)")
async def _undo(agent, arg):
    done = agent.undo()
    return CommandResult("\n".join(done) if done else "Nothing to undo.")


@command("sessions", "List saved sessions for this directory")
async def _sessions(agent, arg):
    if agent.store is None:
        return CommandResult("Sessions are not enabled.", is_error=True)
    infos = agent.store.list(str(agent.ws.root))[:15]
    rows = [
        f"{i.id}  {time.strftime('%m-%d %H:%M', time.localtime(i.updated))}  {i.turns} turns  {i.title}"
        for i in infos
    ]
    return CommandResult("\n".join(rows) or "No saved sessions here.")


@command("resume", "Resume a saved session (latest if no id)", "[id]")
async def _resume(agent, arg):
    if agent.store is None:
        return CommandResult("Sessions are not enabled.", is_error=True)
    try:
        sid = arg or next(iter(agent.store.list(str(agent.ws.root))), None)
        sid = getattr(sid, "id", sid)
        if not sid:
            return CommandResult("No saved sessions here.", is_error=True)
        turns = agent.load_session(sid)
    except (KeyError, ValueError):
        return CommandResult(f"Session not found: {arg}", is_error=True)
    return CommandResult(f"Resumed {sid} ({turns} turns).", action="resumed")


@command("init", "Analyze the project and write a ZCODER.md memory file")
async def _init(agent, arg):
    return CommandResult(
        action="prompt",
        prompt=(
            "Analyze this codebase and create a ZCODER.md at the project root for future sessions: build/test/lint commands, "
            "architecture overview, code conventions and gotchas. Keep it under 80 lines. Check for existing ZCODER.md/AGENTS.md first."
        ),
    )


@command("memory", "Show loaded project memory files")
async def _memory(agent, arg):
    return CommandResult(
        "\n".join(f"{p} ({len(t)} chars)" for p, t in agent.memory)
        or "No ZCODER.md/AGENTS.md found. Run /init."
    )


@command("tools", "List available tools")
async def _tools(agent, arg):
    return CommandResult(
        "\n".join(f"{t.name} [{t.category}] — {t.description}" for t in agent.tools.values())
    )


@command("permissions", "Show or edit allow/deny rules", "[allow|deny|reset <rule>]")
async def _perms(agent, arg):
    p = agent.policy
    verb, _, rule = arg.partition(" ")
    if verb in {"allow", "deny"} and rule.strip():
        (p.allow_rules if verb == "allow" else p.deny_rules).append(rule.strip())
    elif verb == "reset":
        p.allow_rules.clear()
        return CommandResult(
            "Cleared allow rules; deny rules are preserved.\n"
            f"Mode: {p.mode.value}\nAllow: {', '.join(p.allow_rules) or '—'}\nDeny: {', '.join(p.deny_rules) or '—'}"
        )
    return CommandResult(
        f"Mode: {p.mode.value}\nAllow: {', '.join(p.allow_rules) or '—'}\nDeny: {', '.join(p.deny_rules) or '—'}"
    )


@command("status", "Show session status")
async def _status(agent, arg):
    from zcoder.agent.codeagent.memory import git_branch

    return CommandResult(
        f"Model: {agent.llm.model}\nDirectory: {agent.ws.root}\nBranch: {git_branch(agent.ws.root) or '—'}\n"
        f"Mode: {agent.mode.value}\nSession: {agent.session_id}\nTurns: {sum(m.get('role') == 'user' for m in agent.messages)}"
    )


@command("exit", "Quit (alias: /quit)")
async def _exit(agent, arg):
    return CommandResult(action="exit")
