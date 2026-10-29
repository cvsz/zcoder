"""Append-only JSONL audit trail of tool calls and permission decisions.

Records *what was done*, never file contents: Write/Edit keep only the path and sizes, and anything that
looks like a credential in a shell command is masked. Auditing must never break a turn, so every failure
is swallowed (and counted in ``dropped``).
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

MAX_BYTES = 10 * 1024 * 1024
KEEP_ROTATED = 3
_SECRET_ASSIGN = re.compile(
    r"(?i)\b([\w.-]*(?:token|secret|passw(?:or)?d|api[_-]?key|credential)[\w.-]*)(=|\s+)(\S+)"
)
_BEARER = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{8,}")
_URL_CREDS = re.compile(r"(://[^/\s:@]+:)[^@\s]+@")


def redact(text: str) -> str:
    text = _URL_CREDS.sub(r"\1***@", text)
    text = _BEARER.sub(r"\1***", text)
    return _SECRET_ASSIGN.sub(lambda m: f"{m.group(1)}{m.group(2)}***", text)


def summarize_args(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    """Audit-safe view of tool arguments."""
    if tool == "Bash":
        return {"command": redact(str(args.get("command", "")))[:500]}
    if tool == "Write":
        return {
            "path": args.get("path"),
            "bytes": len(str(args.get("content", "")).encode("utf-8", "replace")),
        }
    if tool == "Edit":
        return {"path": args.get("path"), "replace_all": bool(args.get("replace_all"))}
    if tool in {"Read", "LS"}:
        return {"path": args.get("path")}
    if tool in {"Glob", "Grep"}:
        return {k: args.get(k) for k in ("pattern", "path", "glob") if args.get(k) is not None}
    if tool == "TodoWrite":
        return {"items": len(args.get("todos") or [])}
    return {"keys": sorted(map(str, args))}


class AuditLog:
    def __init__(self, path: str | Path | None, session_id: str = "", actor: str | None = None) -> None:
        self.path = Path(path).expanduser() if path else None
        self.session_id = session_id
        self.actor = actor or os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"
        self.dropped = 0
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.path is not None

    def record(self, event: str, **fields: Any) -> None:
        if self.path is None:
            return
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "event": event,
            "session": self.session_id,
            "actor": self.actor,
            **fields,
        }
        try:
            line = json.dumps(entry, ensure_ascii=False, default=str) + "\n"
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._rotate_if_needed()
                fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
                with os.fdopen(fd, "a", encoding="utf-8") as fh:
                    fh.write(line)
        except Exception:  # auditing must never break the agent
            self.dropped += 1

    def _rotate_if_needed(self) -> None:
        assert self.path is not None
        try:
            if self.path.stat().st_size < MAX_BYTES:
                return
        except FileNotFoundError:
            return
        for n in range(KEEP_ROTATED - 1, 0, -1):
            src = self.path.with_name(f"{self.path.name}.{n}")
            if src.exists():
                os.replace(src, self.path.with_name(f"{self.path.name}.{n + 1}"))
        os.replace(self.path, self.path.with_name(f"{self.path.name}.1"))
