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

    def _path(self, session_id: str) -> Path:
        if not isinstance(session_id, str) or not _ID.fullmatch(session_id):
            raise ValueError("invalid session id")
        root = self.dir.resolve()
        expected = root / f"{session_id}.json"
        resolved = expected.resolve(strict=False)
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError("session path escapes storage directory") from exc
        if resolved != expected:
            raise ValueError("session path must not resolve through a symlink")
        return resolved

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
        self._path(session_id).unlink(missing_ok=True)
