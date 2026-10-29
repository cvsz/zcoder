"""Permission modes, allow/deny rules and the always-on hard-deny list."""

from __future__ import annotations

import fnmatch
import re
import shlex
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from zcoder.agent.codeagent.tools import Tool
from zcoder.agent.codeagent.workspace import ToolError, Workspace


class Mode(StrEnum):
    DEFAULT = "default"  # ask before edits and commands
    ACCEPT_EDITS = "acceptEdits"  # edits auto-approved, commands still ask
    PLAN = "plan"  # read-only; finish with ExitPlanMode
    BYPASS = "bypass"  # everything except the hard-deny list; opt-in only

    @property
    def label(self) -> str:
        return {"default": "default", "acceptEdits": "accept edits", "plan": "plan mode", "bypass": "bypass"}[
            self.value
        ]


MODE_CYCLE = (Mode.DEFAULT, Mode.ACCEPT_EDITS, Mode.PLAN)


@dataclass
class Verdict:
    action: str  # allow | ask | deny
    reason: str = ""


# Denied in EVERY mode, including bypass.
_HARD_DENY = [
    (
        re.compile(r"\brm\s+(?:-\S+\s+)*(?:--no-preserve-root|/\*?|~/?\*?|\$HOME/?\*?)(?:\s|$)"),
        "recursive delete of / or home",
    ),
    (re.compile(r"\bsudo\b|\bsu\s+-?\w*\s*$|\bdoas\b"), "privilege escalation"),
    (re.compile(r"\bmkfs(?:\.\w+)?\b|\bdd\b[^\n;|&]*\bof=/dev/"), "disk-destroying command"),
    (re.compile(r">\s*/dev/(?:sd|nvme|hd|disk)"), "write to a block device"),
    (re.compile(r":\(\)\s*\{.*\};\s*:"), "fork bomb"),
    (
        re.compile(r"\b(?:curl|wget)\b[^\n]*\|\s*(?:sudo\s+)?(?:ba|z|da)?sh\b"),
        "piping a download into a shell",
    ),
    (re.compile(r"\bchmod\s+-R\s+0?777\s+/(?:\s|$)"), "recursive chmod on /"),
    (re.compile(r"\b(?:shutdown|reboot|halt|poweroff)\b"), "system power command"),
    (
        re.compile(r"\bgit\s+push\b[^\n]*--force(?!-with-lease)[^\n]*\b(?:main|master)\b"),
        "force-push to main",
    ),
]

_SHELL_WRAPPERS = {
    "bash",
    "sh",
    "zsh",
    "eval",
    "exec",
    "env",
    "xargs",
    "sudo",
    "ssh",
    "nohup",
    "time",
    "watch",
    "python",
    "python3",
    "node",
    "perl",
    "ruby",
}
_TWO_WORD = {
    "git",
    "npm",
    "pnpm",
    "yarn",
    "pip",
    "pip3",
    "cargo",
    "make",
    "docker",
    "kubectl",
    "uv",
    "go",
    "pytest",
    "npx",
}
_READONLY_CMDS = {
    "ls",
    "pwd",
    "cat",
    "head",
    "tail",
    "wc",
    "echo",
    "which",
    "whoami",
    "date",
    "uname",
    "grep",
    "rg",
    "file",
    "stat",
    "du",
    "df",
    "basename",
    "dirname",
    "uniq",
    "true",
    "id",
}
_GIT_READONLY = {
    "status",
    "log",
    "show",
    "rev-parse",
    "ls-files",
    "blame",
    "describe",
    "shortlog",
    "ls-tree",
    "remote",
}
_COMPOUND = re.compile(r"&&|\|\||;|\||\n")
_UNSAFE_SHELL = re.compile(r"\$|`|>|<\(|<<|(?<!&)&(?!&)")


def hard_deny_reason(command: str) -> str | None:
    for rx, why in _HARD_DENY:
        if rx.search(command):
            return why
    return None


def split_command(command: str) -> list[str] | None:
    """Split a compound command; None if it uses constructs we refuse to reason about."""
    if _UNSAFE_SHELL.search(command):
        return None
    parts = [p.strip() for p in _COMPOUND.split(command)]
    return [p for p in parts if p] or None


def _tokens(segment: str) -> list[str] | None:
    try:
        return shlex.split(segment)
    except ValueError:
        return None


def _contains_git_diff(command: str) -> bool:
    """Identify git diff commands that may invoke repository-configured external helpers."""
    segments = split_command(command)
    if not segments:
        return False
    for segment in segments:
        toks = _tokens(segment)
        if toks and toks[0] == "git" and len(toks) > 1 and toks[1] == "diff":
            return True
    return False


def _escapes_workspace(token: str) -> bool:
    return token.startswith(("/", "~")) or ".." in token.split("/")


def is_readonly_command(command: str) -> bool:
    segments = split_command(command)
    if not segments:
        return False
    for seg in segments:
        toks = _tokens(seg)
        if not toks:
            return False
        head = toks[0]
        if any(_escapes_workspace(t) or t.startswith(("--output", "--pre", "-o")) for t in toks[1:]):
            return False
        if head in _READONLY_CMDS:
            continue
        if head == "find":
            if any(
                t
                in {
                    "-exec",
                    "-execdir",
                    "-delete",
                    "-fprint",
                    "-fprint0",
                    "-fprintf",
                    "-fls",
                    "-ok",
                    "-okdir",
                }
                for t in toks
            ):
                return False
            continue
        if head == "git" and len(toks) > 1:
            sub = toks[1]
            if sub in _GIT_READONLY:
                if sub == "remote" and len(toks) > 2 and toks[2] not in {"-v", "show", "get-url"}:
                    return False
                continue
            if sub == "branch" and all(
                t.startswith("-") and t in {"-a", "-r", "-v", "-vv", "--list", "--show-current"}
                for t in toks[2:]
            ):
                continue
        return False
    return True


def rule_for(tool: Tool, args: dict[str, Any], ws: Workspace | None = None) -> str | None:
    """The session-allow rule created by 'always allow', or None when it would be too broad."""
    if tool.category == "exec":
        segments = split_command(str(args.get("command", "")))
        if not segments or len(segments) != 1:
            return None
        toks = _tokens(segments[0])
        if not toks or toks[0] in _SHELL_WRAPPERS:
            return None
        prefix = (
            " ".join(toks[:2])
            if toks[0] in _TWO_WORD and len(toks) > 1 and not toks[1].startswith("-")
            else toks[0]
        )
        return f"Bash({prefix}:*)"
    if tool.category == "edit":
        return tool.name
    return None


def _matches(rule: str, tool: Tool, args: dict[str, Any]) -> bool:
    m = re.fullmatch(r"(\w+)(?:\((.*)\))?", rule.strip())
    if not m or m.group(1) != tool.name:
        return False
    pattern = m.group(2)
    if pattern is None:
        return True
    if tool.category == "exec":
        segments = split_command(str(args.get("command", "")))
        if not segments:
            return False
        prefix = pattern[:-2] if pattern.endswith(":*") else pattern
        exact = not pattern.endswith(":*")
        return all((s == prefix) if exact else (s == prefix or s.startswith(prefix + " ")) for s in segments)
    return fnmatch.fnmatch(str(args.get("path", "")), pattern)


@dataclass
class PermissionPolicy:
    mode: Mode = Mode.DEFAULT
    allow_rules: list[str] = field(default_factory=list)
    deny_rules: list[str] = field(default_factory=list)
    allow_bypass: bool = False
    workspace: Workspace | None = None

    def set_mode(self, mode: Mode) -> None:
        if mode == Mode.BYPASS and not self.allow_bypass:
            raise ToolError("bypass mode is disabled (start with --dangerously-skip-permissions to enable)")
        self.mode = mode

    def cycle_mode(self) -> Mode:
        order = list(MODE_CYCLE)
        nxt = order[(order.index(self.mode) + 1) % len(order)] if self.mode in order else Mode.DEFAULT
        self.mode = nxt
        return nxt

    def remember(self, tool: Tool, args: dict[str, Any]) -> str | None:
        rule = rule_for(tool, args)
        if rule and rule not in self.allow_rules:
            self.allow_rules.append(rule)
        return rule

    def check(self, tool: Tool, args: dict[str, Any]) -> Verdict:
        if tool.category == "exec":
            why = hard_deny_reason(str(args.get("command", "")))
            if why:
                return Verdict("deny", f"Blocked: {why}. This is never allowed.")
        if any(_matches(r, tool, args) for r in self.deny_rules):
            return Verdict("deny", "Blocked by a deny rule.")
        if tool.category == "plan":
            return Verdict("ask") if self.mode == Mode.PLAN else Verdict("deny", "Not in plan mode.")
        if self.mode == Mode.PLAN:
            if tool.category in {"read", "meta"}:
                return Verdict("allow")
            if tool.category == "exec" and is_readonly_command(str(args.get("command", ""))):
                return Verdict("allow")
            return Verdict(
                "deny",
                "Plan mode is read-only. Research with Read/Grep/Glob, then call ExitPlanMode with your plan.",
            )
        if tool.category in {"read", "meta"}:
            return Verdict("allow")
        if self.mode == Mode.BYPASS and self.allow_bypass:
            return Verdict("allow")
        if tool.category == "exec" and _contains_git_diff(str(args.get("command", ""))):
            return Verdict("ask", "Git diff may invoke configured external helpers; approve each invocation.")
        sensitive = False
        if tool.category == "edit" and self.workspace is not None:
            try:
                sensitive = Workspace.is_sensitive(self.workspace.resolve(str(args.get("path", ""))))
            except ToolError:
                sensitive = False
        if sensitive:
            return Verdict("ask", "Sensitive file")
        if any(_matches(r, tool, args) for r in self.allow_rules):
            return Verdict("allow")
        if tool.category == "edit" and self.mode == Mode.ACCEPT_EDITS:
            return Verdict("allow")
        if tool.category == "exec" and is_readonly_command(str(args.get("command", ""))):
            return Verdict("allow")
        return Verdict("ask")
