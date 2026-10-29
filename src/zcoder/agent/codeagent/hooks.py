"""PreToolUse / PostToolUse command hooks.

A hook is a shell command that receives a JSON description of the tool call on stdin.
Exit 0 = continue; exit 2 = block (stderr is shown to the model); anything else = warning only.
Hooks run with a scrubbed environment and a hard timeout.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess  # nosec B404 - user/org-configured hook commands
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SAFE_ENV = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "USER", "SHELL")


@dataclass
class HookResult:
    blocked: bool = False
    message: str = ""
    warnings: tuple[str, ...] = ()


class Hooks:
    def __init__(
        self, config: dict[str, list[dict[str, Any]]] | None, cwd: Path, session_id: str = ""
    ) -> None:
        self.config = config or {}
        self.cwd = Path(cwd)
        self.session_id = session_id

    @property
    def active(self) -> bool:
        return any(self.config.values())

    def _matching(self, event: str, tool: str) -> list[dict[str, Any]]:
        out = []
        for h in self.config.get(event, []):
            m = h.get("matcher", "*")
            try:
                if m in {"*", ""} or re.fullmatch(m, tool):
                    out.append(h)
            except re.error:
                continue
        return out

    def _run(self, hook: dict[str, Any], payload: dict[str, Any]) -> tuple[int, str, str]:
        env = {k: os.environ[k] for k in _SAFE_ENV if k in os.environ}
        env["ZCODER_PROJECT_DIR"] = str(self.cwd)
        try:
            r = subprocess.run(  # noqa: S602  # nosec B602 - hook commands are configured by the user/org, not the model
                hook["command"],
                shell=True,
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                cwd=self.cwd,
                env=env,
                timeout=max(1, min(int(hook.get("timeout", 30)), 300)),
                check=False,
            )
        except subprocess.TimeoutExpired:
            return -1, "", f"hook timed out: {hook['command'][:80]}"
        except OSError as exc:
            return -1, "", f"hook failed to start: {exc}"
        return r.returncode, r.stdout, r.stderr

    async def _fire(self, event: str, tool: str, args: dict[str, Any], extra: dict[str, Any]) -> HookResult:
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
            if code != 0:
                warnings.append((err.strip() or f"hook exited with {code}")[:300])
        return HookResult(False, "", tuple(warnings))

    async def pre_tool(self, tool: str, args: dict[str, Any]) -> HookResult:
        return await self._fire("PreToolUse", tool, args, {}) if self.active else HookResult()

    async def post_tool(self, tool: str, args: dict[str, Any], output: str, is_error: bool) -> HookResult:
        if not self.active:
            return HookResult()
        return await self._fire("PostToolUse", tool, args, {"output": output[:4000], "is_error": is_error})
