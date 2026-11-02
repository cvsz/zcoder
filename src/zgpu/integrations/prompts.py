"""Private local storage for reusable zGPU prompt templates."""

from __future__ import annotations

import os
import re
import sqlite3
import stat
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class PromptLibraryError(ValueError):
    """Invalid prompt input or unavailable local prompt storage."""

    def __init__(self, message: str, status: int = 400):
        self.status = status
        super().__init__(message)


class PromptLibrary:
    """Store reusable prompts in a bounded, private SQLite database."""

    MAX_PROMPTS = 200
    MAX_TITLE_CHARS = 120
    MAX_CONTENT_CHARS = 4_000
    MAX_TOTAL_CONTENT_BYTES = 10_485_760

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path).expanduser()

    def list(self, *, limit: int = 200) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= self.MAX_PROMPTS:
            raise PromptLibraryError(f"limit must be between 1 and {self.MAX_PROMPTS}")
        try:
            with self._connection() as connection:
                rows = connection.execute(
                    """SELECT id, title, created_at, updated_at FROM prompts
                       ORDER BY updated_at DESC, id LIMIT ?""",
                    (limit,),
                ).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as exc:
            raise PromptLibraryError("prompt storage is unavailable", status=503) from exc

    def get(self, prompt_id: str) -> dict[str, Any]:
        self._validate_id(prompt_id)
        try:
            with self._connection() as connection:
                row = connection.execute(
                    "SELECT id, title, content, created_at, updated_at FROM prompts WHERE id = ?",
                    (prompt_id,),
                ).fetchone()
            if row is None:
                raise PromptLibraryError("prompt not found", status=404)
            return dict(row)
        except sqlite3.Error as exc:
            raise PromptLibraryError("prompt storage is unavailable", status=503) from exc

    def create(self, title: str, content: str) -> dict[str, Any]:
        title, content = self._validate_prompt(title, content)
        now = datetime.now(UTC).isoformat()
        prompt_id = uuid.uuid4().hex
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                count, size = connection.execute(
                    "SELECT count(*), COALESCE(sum(length(CAST(content AS BLOB))), 0) FROM prompts"
                ).fetchone()
                if count >= self.MAX_PROMPTS:
                    raise PromptLibraryError("prompt library limit reached", status=409)
                if size + len(content.encode("utf-8")) > self.MAX_TOTAL_CONTENT_BYTES:
                    raise PromptLibraryError("prompt library storage quota would be exceeded", status=413)
                connection.execute(
                    "INSERT INTO prompts (id, title, content, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (prompt_id, title, content, now, now),
                )
                connection.commit()
        except sqlite3.Error as exc:
            raise PromptLibraryError("prompt storage is unavailable", status=503) from exc
        return self.get(prompt_id)

    def update(self, prompt_id: str, title: str, content: str) -> dict[str, Any]:
        self._validate_id(prompt_id)
        title, content = self._validate_prompt(title, content)
        now = datetime.now(UTC).isoformat()
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT created_at FROM prompts WHERE id = ?", (prompt_id,)
                ).fetchone()
                if row is None:
                    raise PromptLibraryError("prompt not found", status=404)
                size = connection.execute(
                    "SELECT COALESCE(sum(length(CAST(content AS BLOB))), 0) FROM prompts WHERE id != ?",
                    (prompt_id,),
                ).fetchone()[0]
                if size + len(content.encode("utf-8")) > self.MAX_TOTAL_CONTENT_BYTES:
                    raise PromptLibraryError("prompt library storage quota would be exceeded", status=413)
                connection.execute(
                    "UPDATE prompts SET title = ?, content = ?, updated_at = ? WHERE id = ?",
                    (title, content, now, prompt_id),
                )
                connection.commit()
        except sqlite3.Error as exc:
            raise PromptLibraryError("prompt storage is unavailable", status=503) from exc
        return self.get(prompt_id)

    def delete(self, prompt_id: str) -> bool:
        self._validate_id(prompt_id)
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute("DELETE FROM prompts WHERE id = ?", (prompt_id,))
                connection.commit()
                return cursor.rowcount == 1
        except sqlite3.Error as exc:
            raise PromptLibraryError("prompt storage is unavailable", status=503) from exc

    @classmethod
    def _validate_prompt(cls, title: Any, content: Any) -> tuple[str, str]:
        if not isinstance(title, str) or not title.strip() or len(title.strip()) > cls.MAX_TITLE_CHARS:
            raise PromptLibraryError(f"title must contain 1 to {cls.MAX_TITLE_CHARS} characters")
        if not isinstance(content, str) or not content.strip() or len(content) > cls.MAX_CONTENT_CHARS:
            raise PromptLibraryError(f"content must contain 1 to {cls.MAX_CONTENT_CHARS} characters")
        try:
            title.strip().encode("utf-8")
            content.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise PromptLibraryError("title and content must be valid Unicode text") from exc
        return title.strip(), content

    @staticmethod
    def _validate_id(prompt_id: str) -> None:
        if not isinstance(prompt_id, str) or not re.fullmatch(r"[a-f0-9]{32}", prompt_id):
            raise PromptLibraryError("invalid prompt identifier")

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = None
        try:
            self.database_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            try:
                descriptor = os.open(self.database_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                info = self.database_path.stat(follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode) or (
                    os.name == "posix" and stat.S_IMODE(info.st_mode) & 0o077
                ):
                    raise PromptLibraryError(
                        "prompt database must be a private regular file", status=503
                    ) from None
            else:
                os.close(descriptor)
            connection = sqlite3.connect(self.database_path, timeout=5.0)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute("""CREATE TABLE IF NOT EXISTS prompts (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, content TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                )""")
            yield connection
        except OSError as exc:
            raise PromptLibraryError("prompt storage path is unavailable", status=503) from exc
        except sqlite3.Error as exc:
            raise PromptLibraryError("prompt storage is unavailable", status=503) from exc
        finally:
            if connection is not None:
                connection.close()
