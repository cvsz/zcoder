"""Persisted, resumable conversations (one JSON file per session)."""

from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from zcoder.agent.codeagent.memory import zcoder_home

_ID = re.compile(r"^[0-9]{8}-[0-9]{6}-[0-9a-f]{6}$")


def new_session_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)


@dataclass
class SessionInfo:
    id: str
    title: str
    cwd: str
    updated: float
    turns: int


class SessionStore:
    def __init__(self, directory: Path | None = None):
        self.dir = Path(directory) if directory else zcoder_home() / "sessions"

    def _validate_session_id(self, session_id: str) -> str:
        """Validate and return a sanitized session ID safe for filesystem use.

        Session IDs are strictly formatted (YYYYMMDD-HHMMSS-XXXXXX) with no
        path separators or traversal sequences, so the returned value can be
        embedded directly into a filesystem path without traversal risk.
        """
        if not isinstance(session_id, str):
            raise ValueError("invalid session id")
        if "/" in session_id or "\\" in session_id or ".." in session_id:
            raise ValueError("invalid session id")
        safe_id = os.path.basename(session_id)
        if safe_id != session_id or not _ID.fullmatch(safe_id):
            raise ValueError("invalid session id")
        return safe_id

    def _path(self, session_id: str) -> Path:
        # Validate the ID first (basename + strict pattern allowlist).
        safe_id = self._validate_session_id(session_id)
        root = self.dir.resolve()
        expected = root / f"{safe_id}.json"
        # Normalize the path with os.path.realpath, then prove containment
        # with a prefix check against the storage root before any filesystem
        # access. This blocks both traversal sequences and symlink escapes.
        resolved_path = os.path.realpath(expected)
        if not resolved_path.startswith(str(root) + os.sep):
            raise ValueError("session path escapes storage directory")
        if resolved_path != str(expected):
            raise ValueError("session path must not resolve through a symlink")
        return Path(resolved_path)

    def save(
        self, session_id: str, cwd: str, messages: list[dict[str, Any]], usage: dict[str, int] | None = None
    ) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        title = next(
            (m["content"] for m in messages if m.get("role") == "user" and isinstance(m.get("content"), str)),
            "",
        )
        title = re.sub(r"\s+", " ", title.split("<file path=")[0]).strip()[:80] or "(empty)"
        doc = {
            "id": session_id,
            "cwd": cwd,
            "title": title,
            "updated": time.time(),
            "usage": usage or {},
            "messages": messages,
        }
        fd, tmp = tempfile.mkstemp(dir=self.dir, prefix=".tmp-")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self._path(session_id))

    def load(self, session_id: str) -> dict[str, Any]:
        try:
            return json.loads(self._path(session_id).read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise KeyError(session_id) from exc

    def list(self, cwd: str | None = None) -> list[SessionInfo]:
        infos: list[SessionInfo] = []
        for p in self.dir.glob("*.json") if self.dir.exists() else []:
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                if cwd and d.get("cwd") != cwd:
                    continue
                infos.append(
                    SessionInfo(
                        d["id"],
                        d.get("title", ""),
                        d.get("cwd", ""),
                        d.get("updated", 0.0),
                        sum(m.get("role") == "user" for m in d.get("messages", [])),
                    )
                )
            except (OSError, ValueError, KeyError):
                continue
        return sorted(infos, key=lambda i: i.updated, reverse=True)

    def delete(self, session_id: str) -> None:
        # _path() fully validates session_id before unlink(), so user-provided
        # session_id cannot reach the filesystem sink unsanitized.
        self._path(session_id).unlink(missing_ok=True)

    def fork(self, session_id: str, *, label: str | None = None) -> str:
        """Create a new session that copies the messages from an existing one.

        Returns the new session ID. The forked session shares the same cwd and
        message history, allowing the agent to branch off a previous conversation
        without losing the original.
        """
        original = self.load(session_id)
        new_id = new_session_id()
        messages = list(original.get("messages", []))
        if label:
            messages.append({"role": "user", "content": label})
        self.save(new_id, original.get("cwd", ""), messages, original.get("usage"))
        return new_id
