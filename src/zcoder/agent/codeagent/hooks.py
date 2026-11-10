"""Lifecycle hooks for the agent loop.

Hooks are shell commands that receive a JSON description of the event on stdin.
Exit 0 = continue; exit 2 = block (stderr is shown to the model); anything else = warning only.
Hooks run with a scrubbed environment and a hard timeout.

Supported events (Claude Code-compatible):
  SessionStart      before the first turn of a session
  UserPromptSubmit  before each user prompt reaches the model
  PreToolUse        before a tool call is executed
  PostToolUse       after a tool call completes
  Stop              when a turn ends
  SubagentStart     when a subagent is spawned
  SubagentStop      when a subagent finishes
  Notification      when Claude wants to notify the user
  PreCompact        before context compaction
  PostCompact       after context compaction
  WorktreeCreate    when a git worktree is created
  WorktreeRemove    when a git worktree is removed
  Elicitation       when the model requests user input
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess  # nosec B404  # user/org-configured hook commands
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SAFE_ENV = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "USER", "SHELL")

# All Claude Code hook events, in the order they typically fire.
HOOK_EVENTS = frozenset(
    {
        "SessionStart",
        "UserPromptSubmit",
        "PreToolUse",
        "PostToolUse",
        "Stop",
        "SubagentStart",
        "SubagentStop",
        "Notification",
        "PreCompact",
        "PostCompact",
        "WorktreeCreate",
        "WorktreeRemove",
        "Elicitation",
    }
)

# Events that can block (exit code 2 prevents the action).
_BLOCKING_EVENTS = frozenset({"PreToolUse", "UserPromptSubmit", "Elicitation", "WorktreeCreate"})


@dataclass
class HookResult:
    blocked: bool = False
    message: str = ""
    warnings: tuple[str, ...] = ()


@dataclass
class HookEntry:
    matcher: str
    command: str
    timeout: int = 30


class Hooks:
    def __init__(
        self,
        config: dict[str, list[dict[str, Any]]] | None,
        cwd: Path,
        session_id: str = "",
    ) -> None:
        self.config: dict[str, list[HookEntry]] = {}
        self.cwd = Path(cwd)
        self.session_id = session_id
        if config:
            for event, entries in config.items():
                if event not in HOOK_EVENTS:
                    continue
                self.config[event] = [
                    HookEntry(
                        matcher=str(e.get("matcher", "*")),
                        command=str(e["command"]),
                        timeout=max(1, min(int(e.get("timeout", 30)), 300)),
                    )
                    for e in entries
                    if isinstance(e, dict) and e.get("command")
                ]

    @property
    def active(self) -> bool:
        return any(self.config.values())

    def _matching(self, event: str, tool: str = "") -> list[HookEntry]:
        out: list[HookEntry] = []
        for hook in self.config.get(event, []):
            try:
                if hook.matcher in {"*", ""} or re.fullmatch(hook.matcher, tool):
                    out.append(hook)
            except re.error:
                continue
        return out

    def _run(self, hook: HookEntry, payload: dict[str, Any]) -> tuple[int, str, str]:
        env = {k: os.environ[k] for k in _SAFE_ENV if k in os.environ}
        env["ZCODER_PROJECT_DIR"] = str(self.cwd)
        try:
            r = subprocess.run(  # noqa: S602  # nosec B602  # hook commands are configured by the user/org
                hook.command,
                shell=True,
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                cwd=self.cwd,
                env=env,
                timeout=hook.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return -1, "", f"hook timed out: {hook.command[:80]}"
        except OSError as exc:
            return -1, "", f"hook failed to start: {exc}"
        return r.returncode, r.stdout, r.stderr

    async def _fire(
        self, event: str, tool: str, args: dict[str, Any], extra: dict[str, Any], blocking: bool
    ) -> HookResult:
        warnings: list[str] = []
        for hook in self._matching(event, tool):
            payload = {
                "event": event,
                "tool": tool,
                "args": args,
                "session_id": self.session_id,
                "cwd": str(self.cwd),
                **extra,
            }
            code, _out, err = await asyncio.to_thread(self._run, hook, payload)
            if code == 2:
                return HookResult(True, (err.strip() or "Blocked by hook.")[:2000], tuple(warnings))
            if blocking and code != 0:
                warnings.append((err.strip() or f"hook exited with {code}")[:300])
            elif not blocking and code != 0:
                warnings.append((err.strip() or f"hook exited with {code}")[:300])
        return HookResult(False, "", tuple(warnings))

    # --- event-specific entry points -------------------------------------

    async def session_start(self, cwd: str) -> HookResult:
        return await self._fire("SessionStart", "", {}, {"cwd": cwd}, blocking=False)

    async def user_prompt_submit(self, prompt: str) -> HookResult:
        return await self._fire("UserPromptSubmit", "", {}, {"prompt": prompt}, blocking=True)

    async def pre_tool(self, tool: str, args: dict[str, Any]) -> HookResult:
        return await self._fire("PreToolUse", tool, args, {}, blocking=True)

    async def post_tool(
        self, tool: str, args: dict[str, Any], output: str, is_error: bool
    ) -> HookResult:
        return await self._fire(
            "PostToolUse", tool, args, {"output": output[:4000], "is_error": is_error}, blocking=False
        )

    async def stop(self, stop_reason: str, tool: str = "") -> HookResult:
        return await self._fire(
            "Stop", tool, {}, {"stop_reason": stop_reason}, blocking=False
        )

    async def subagent_start(self, agent_type: str, prompt: str) -> HookResult:
        return await self._fire(
            "SubagentStart", agent_type, {}, {"prompt": prompt[:2000]}, blocking=False
        )

    async def subagent_stop(self, agent_type: str, result_summary: str) -> HookResult:
        return await self._fire(
            "SubagentStop", agent_type, {}, {"result_summary": result_summary[:2000]}, blocking=False
        )

    async def notification(self, message: str) -> HookResult:
        return await self._fire("Notification", "", {}, {"message": message}, blocking=False)

    async def pre_compact(self, reason: str) -> HookResult:
        return await self._fire("PreCompact", "", {}, {"reason": reason}, blocking=False)

    async def post_compact(self, reason: str, summary: str) -> HookResult:
        return await self._fire(
            "PostCompact", "", {}, {"reason": reason, "summary": summary[:2000]}, blocking=False
        )

    async def worktree_create(self, path: str, branch: str) -> HookResult:
        return await self._fire(
            "WorktreeCreate", "", {}, {"path": path, "branch": branch}, blocking=True
        )

    async def worktree_remove(self, path: str) -> HookResult:
        return await self._fire("WorktreeRemove", "", {}, {"path": path}, blocking=False)

    async def elicitation(self, prompt: str) -> HookResult:
        return await self._fire("Elicitation", "", {}, {"prompt": prompt}, blocking=True)
