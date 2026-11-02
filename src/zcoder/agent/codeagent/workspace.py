"""Workspace sandboxing, read-before-edit tracking and undo checkpoints."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

IGNORED_DIRS = frozenset(
    {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        ".web-venv",
        ".build-venv",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        "dist",
        "build",
        ".tox",
        ".next",
        "target",
        ".idea",
        ".vscode",
    }
)


class ToolError(Exception):
    """A tool failed in a way the model should see and react to."""


@dataclass
class Checkpoint:
    turn: int
    path: Path
    previous: bytes | None  # None => file did not exist


@dataclass
class Workspace:
    root: Path
    extra_dirs: tuple[Path, ...] = ()
    read_state: dict[Path, int] = field(default_factory=dict)
    checkpoints: list[Checkpoint] = field(default_factory=list)
    turn: int = 0

    def __post_init__(self) -> None:
        self.root = Path(self.root).expanduser().resolve()
        self.extra_dirs = tuple(Path(p).expanduser().resolve() for p in self.extra_dirs)

    # --- paths -----------------------------------------------------------
    def _allowed_roots(self) -> tuple[Path, ...]:
        return (self.root, *self.extra_dirs)

    def resolve(self, raw: str) -> Path:
        """Resolve ``raw`` (relative to root) and refuse anything outside the workspace."""
        if not isinstance(raw, str) or not raw.strip():
            raise ToolError("path is required")
        if "\x00" in raw:
            raise ToolError("invalid path")
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = self.root / candidate
        resolved = candidate.resolve()  # follows symlinks, so links cannot escape
        if not any(resolved == r or r in resolved.parents for r in self._allowed_roots()):
            raise ToolError(f"path is outside the workspace: {raw}")
        return resolved

    def rel(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.root))
        except ValueError:
            return str(path)

    @staticmethod
    def is_protected(path: Path) -> bool:
        """Paths the agent may never write (VCS internals)."""
        return ".git" in path.parts

    @staticmethod
    def is_sensitive(path: Path) -> bool:
        name = path.name.lower()
        return (
            name.startswith(".env")
            or name.endswith((".pem", ".key", ".p12", ".pfx"))
            or name in {"id_rsa", "id_ed25519", "credentials", ".npmrc", ".pypirc", ".netrc"}
            or ".github" in path.parts
        )

    # --- read tracking ---------------------------------------------------
    def mark_read(self, path: Path) -> None:
        try:
            self.read_state[path] = path.stat().st_mtime_ns
        except OSError:
            pass

    def ensure_fresh(self, path: Path) -> None:
        """Existing files must have been read, and not changed since (like Claude Code)."""
        if path not in self.read_state:
            raise ToolError(f"{self.rel(path)} has not been read yet. Use Read first, then retry.")
        if path.stat().st_mtime_ns != self.read_state[path]:
            raise ToolError(f"{self.rel(path)} changed since it was read. Read it again before editing.")

    # --- checkpoints -----------------------------------------------------
    def begin_turn(self) -> None:
        self.turn += 1

    def write_atomic(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        previous = path.read_bytes() if path.exists() else None
        self.checkpoints.append(Checkpoint(self.turn, path, previous))
        mode = path.stat().st_mode & 0o777 if previous is not None else None
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".zcoder-")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            if mode is not None:
                os.chmod(tmp, mode)
            os.replace(tmp, path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        self.mark_read(path)

    def undo_last_turn(self) -> list[str]:
        """Revert every file change made in the most recent turn that changed files."""
        if not self.checkpoints:
            return []
        turn = self.checkpoints[-1].turn
        restored: list[str] = []
        while self.checkpoints and self.checkpoints[-1].turn == turn:
            cp = self.checkpoints.pop()
            if cp.previous is None:
                if cp.path.exists():
                    cp.path.unlink()
                restored.append(f"deleted {self.rel(cp.path)}")
            else:
                cp.path.write_bytes(cp.previous)
                restored.append(f"restored {self.rel(cp.path)}")
            self.read_state.pop(cp.path, None)
        return restored
