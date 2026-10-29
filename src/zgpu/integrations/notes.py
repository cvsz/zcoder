"""Private, bounded local storage for user-managed zGPU workspace notes."""

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


class WorkspaceNotesError(ValueError):
    """Invalid workspace note or unavailable note storage."""

    def __init__(self, message: str, status: int = 400):
        self.status = status
        super().__init__(message)


class WorkspaceNotes:
    """Store editable single-user notes with bounded retrieval for chat context."""

    MAX_NOTES = 100
    MAX_TITLE_CHARS = 120
    MAX_CONTENT_CHARS = 20_000
    MAX_TOTAL_CONTENT_BYTES = 2_097_152
    MAX_SEARCH_CHARS = 4_000
    MAX_EXCERPT_CHARS = 1_600

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path).expanduser()

    def list(self, *, limit: int = MAX_NOTES) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= self.MAX_NOTES:
            raise WorkspaceNotesError(f"limit must be between 1 and {self.MAX_NOTES}")
        try:
            with self._connection() as connection:
                rows = connection.execute(
                    """SELECT id, title, project_id, length(content) AS content_chars, created_at, updated_at
                       FROM workspace_notes ORDER BY updated_at DESC, id LIMIT ?""",
                    (limit,),
                ).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as exc:
            raise WorkspaceNotesError("workspace note storage is unavailable", status=503) from exc

    def get(self, note_id: str) -> dict[str, Any]:
        self._validate_id(note_id)
        try:
            with self._connection() as connection:
                row = connection.execute(
                    "SELECT id, title, content, project_id, created_at, updated_at FROM workspace_notes WHERE id = ?",
                    (note_id,),
                ).fetchone()
            if row is None:
                raise WorkspaceNotesError("workspace note not found", status=404)
            return dict(row)
        except sqlite3.Error as exc:
            raise WorkspaceNotesError("workspace note storage is unavailable", status=503) from exc

    def create(self, title: str, content: str, project_id: str | None = None) -> dict[str, Any]:
        title, content = self._validate_note(title, content)
        self._validate_project_id(project_id)
        note_id = uuid.uuid4().hex
        now = datetime.now(UTC).isoformat()
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                count, total_bytes = connection.execute(
                    "SELECT count(*), COALESCE(sum(length(CAST(content AS BLOB))), 0) FROM workspace_notes"
                ).fetchone()
                if count >= self.MAX_NOTES:
                    raise WorkspaceNotesError("workspace note limit reached", status=409)
                if total_bytes + len(content.encode("utf-8")) > self.MAX_TOTAL_CONTENT_BYTES:
                    raise WorkspaceNotesError("workspace note storage quota would be exceeded", status=413)
                connection.execute(
                    """INSERT INTO workspace_notes
                       (id, title, content, project_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)""",
                    (note_id, title, content, project_id, now, now),
                )
                connection.commit()
        except sqlite3.Error as exc:
            raise WorkspaceNotesError("workspace note storage is unavailable", status=503) from exc
        return self.get(note_id)

    def update(self, note_id: str, title: str, content: str, project_id: str | None = None) -> dict[str, Any]:
        self._validate_id(note_id)
        title, content = self._validate_note(title, content)
        self._validate_project_id(project_id)
        now = datetime.now(UTC).isoformat()
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                exists = connection.execute(
                    "SELECT 1 FROM workspace_notes WHERE id = ?", (note_id,)
                ).fetchone()
                if exists is None:
                    raise WorkspaceNotesError("workspace note not found", status=404)
                other_bytes = connection.execute(
                    "SELECT COALESCE(sum(length(CAST(content AS BLOB))), 0) FROM workspace_notes WHERE id != ?",
                    (note_id,),
                ).fetchone()[0]
                if other_bytes + len(content.encode("utf-8")) > self.MAX_TOTAL_CONTENT_BYTES:
                    raise WorkspaceNotesError("workspace note storage quota would be exceeded", status=413)
                connection.execute(
                    "UPDATE workspace_notes SET title = ?, content = ?, project_id = ?, updated_at = ? WHERE id = ?",
                    (title, content, project_id, now, note_id),
                )
                connection.commit()
        except sqlite3.Error as exc:
            raise WorkspaceNotesError("workspace note storage is unavailable", status=503) from exc
        return self.get(note_id)

    def delete(self, note_id: str) -> bool:
        self._validate_id(note_id)
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute("DELETE FROM workspace_notes WHERE id = ?", (note_id,))
                connection.commit()
                return cursor.rowcount == 1
        except sqlite3.Error as exc:
            raise WorkspaceNotesError("workspace note storage is unavailable", status=503) from exc

    def search(self, query: str, *, project_id: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
        if not isinstance(query, str) or not query.strip() or len(query) > self.MAX_SEARCH_CHARS:
            raise WorkspaceNotesError(f"query must contain 1 to {self.MAX_SEARCH_CHARS} characters")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 5:
            raise WorkspaceNotesError("limit must be between 1 and 5")
        self._validate_project_id(project_id)
        terms = list(dict.fromkeys(re.findall(r"[\w-]{2,}", query.casefold())))[:32]
        if not terms:
            return []
        try:
            with self._connection() as connection:
                if project_id is None:
                    rows = connection.execute("""SELECT id, title, content, updated_at FROM workspace_notes
                           WHERE project_id IS NULL ORDER BY updated_at DESC, id""").fetchall()
                else:
                    rows = connection.execute(
                        """SELECT id, title, content, updated_at FROM workspace_notes
                           WHERE project_id IS NULL OR project_id = ? ORDER BY updated_at DESC, id""",
                        (project_id,),
                    ).fetchall()
        except sqlite3.Error as exc:
            raise WorkspaceNotesError("workspace note storage is unavailable", status=503) from exc
        matches = []
        for row in rows:
            title, content = row["title"], row["content"]
            folded_title, folded_content = title.casefold(), content.casefold()
            score = sum(folded_title.count(term) * 3 + folded_content.count(term) for term in terms)
            if score == 0:
                continue
            first_position = min(
                (folded_content.find(term) for term in terms if folded_content.find(term) >= 0),
                default=0,
            )
            start = max(0, first_position - self.MAX_EXCERPT_CHARS // 3)
            excerpt = content[start : start + self.MAX_EXCERPT_CHARS]
            if start:
                excerpt = "…" + excerpt
            if start + len(excerpt) < len(content):
                excerpt += "…"
            matches.append(
                {
                    "id": row["id"],
                    "title": title,
                    "excerpt": excerpt,
                    "updated_at": row["updated_at"],
                    "score": score,
                }
            )
        matches.sort(key=lambda item: (-item["score"], item["title"].casefold(), item["id"]))
        return [{key: value for key, value in match.items() if key != "score"} for match in matches[:limit]]

    def detach_project(self, project_id: str) -> int:
        self._validate_project_id(project_id)
        if project_id is None:
            raise WorkspaceNotesError("project_id is required")
        try:
            with self._connection() as connection:
                cursor = connection.execute(
                    "UPDATE workspace_notes SET project_id = NULL, updated_at = ? WHERE project_id = ?",
                    (datetime.now(UTC).isoformat(), project_id),
                )
                connection.commit()
                return cursor.rowcount
        except sqlite3.Error as exc:
            raise WorkspaceNotesError("workspace note storage is unavailable", status=503) from exc

    @classmethod
    def _validate_note(cls, title: Any, content: Any) -> tuple[str, str]:
        if not isinstance(title, str) or not title.strip() or len(title.strip()) > cls.MAX_TITLE_CHARS:
            raise WorkspaceNotesError(f"title must contain 1 to {cls.MAX_TITLE_CHARS} characters")
        if not isinstance(content, str) or not content.strip() or len(content) > cls.MAX_CONTENT_CHARS:
            raise WorkspaceNotesError(f"content must contain 1 to {cls.MAX_CONTENT_CHARS} characters")
        try:
            title.strip().encode("utf-8")
            content.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise WorkspaceNotesError("title and content must be valid Unicode text") from exc
        return title.strip(), content

    @staticmethod
    def _validate_id(note_id: str) -> None:
        if not isinstance(note_id, str) or not re.fullmatch(r"[a-f0-9]{32}", note_id):
            raise WorkspaceNotesError("invalid workspace note identifier")

    @staticmethod
    def _validate_project_id(project_id: str | None) -> None:
        if project_id is not None and (
            not isinstance(project_id, str) or not re.fullmatch(r"[a-f0-9]{32}", project_id)
        ):
            raise WorkspaceNotesError("invalid workspace project identifier")

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
                    raise WorkspaceNotesError(
                        "workspace note database must be a private regular file", status=503
                    ) from None
            else:
                os.close(descriptor)
            connection = sqlite3.connect(self.database_path, timeout=5.0)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute("""CREATE TABLE IF NOT EXISTS workspace_notes (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, content TEXT NOT NULL,
                    project_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                )""")
            columns = {row[1] for row in connection.execute("PRAGMA table_info(workspace_notes)")}
            if "project_id" not in columns:
                connection.execute("ALTER TABLE workspace_notes ADD COLUMN project_id TEXT")
            yield connection
        except OSError as exc:
            raise WorkspaceNotesError("workspace note storage path is unavailable", status=503) from exc
        except sqlite3.Error as exc:
            raise WorkspaceNotesError("workspace note storage is unavailable", status=503) from exc
        finally:
            if connection is not None:
                connection.close()
