"""Persistent single-user conversation storage for the local zGPU workspace."""

from __future__ import annotations

import json
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
from urllib.parse import urlsplit


class ConversationError(ValueError):
    """Invalid conversation input or unavailable local storage."""

    def __init__(self, message: str, status: int = 400):
        self.status = status
        super().__init__(message)


class ConversationStore:
    """Persist bounded conversation history in a private local SQLite database."""

    MAX_CONVERSATIONS = 200
    MAX_MESSAGES_PER_CONVERSATION = 500
    MAX_CONTENT_CHARS = 32_000
    MAX_TOTAL_CONTENT_BYTES = 104_857_600
    MAX_CITATIONS = 32
    MAX_SEARCH_CHARS = 256
    MAX_PROJECTS = 100

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path).expanduser()

    def create(
        self,
        title: str = "New chat",
        model: str = "",
        project_id: str | None = None,
        assistant_id: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(title, str) or not title.strip() or len(title.strip()) > 120:
            raise ConversationError("title must contain 1 to 120 characters")
        if not isinstance(model, str) or len(model) > 256:
            raise ConversationError("model must contain at most 256 characters")
        if project_id is not None:
            self._validate_project_id(project_id)
        if assistant_id is not None:
            self._validate_assistant_id(assistant_id)
        now = datetime.now(UTC).isoformat()
        conversation_id = uuid.uuid4().hex
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                count = connection.execute("SELECT count(*) FROM conversations").fetchone()[0]
                if count >= self.MAX_CONVERSATIONS:
                    raise ConversationError("conversation limit reached", status=409)
                if (
                    project_id is not None
                    and not connection.execute(
                        "SELECT 1 FROM workspace_projects WHERE id = ?", (project_id,)
                    ).fetchone()
                ):
                    raise ConversationError("project not found", status=404)
                connection.execute(
                    """INSERT INTO conversations (id, title, model, project_id, assistant_id, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (conversation_id, title.strip(), model.strip(), project_id, assistant_id, now, now),
                )
                connection.commit()
        except sqlite3.Error as exc:
            raise ConversationError("conversation storage is unavailable", status=503) from exc
        return self.get(conversation_id)

    def list(
        self, *, limit: int = 200, search: str = "", project_id: str | None = None
    ) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= self.MAX_CONVERSATIONS:
            raise ConversationError(f"limit must be between 1 and {self.MAX_CONVERSATIONS}")
        if not isinstance(search, str) or len(search) > self.MAX_SEARCH_CHARS:
            raise ConversationError(f"search must contain at most {self.MAX_SEARCH_CHARS} characters")
        try:
            search = search.strip()
            search.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ConversationError("search must be valid Unicode text") from exc
        if project_id is not None:
            self._validate_project_id(project_id)
        try:
            with self._connection() as connection:
                if (
                    project_id is not None
                    and not connection.execute(
                        "SELECT 1 FROM workspace_projects WHERE id = ?", (project_id,)
                    ).fetchone()
                ):
                    raise ConversationError("project not found", status=404)
                rows = connection.execute(
                    """SELECT c.id, c.title, c.model, c.project_id, c.assistant_id, c.created_at, c.updated_at,
                              count(m.id) AS message_count
                       FROM conversations c LEFT JOIN conversation_messages m ON m.conversation_id = c.id
                       WHERE (? IS NULL OR c.project_id = ?)
                         AND (? = '' OR instr(lower(c.title), lower(?)) > 0 OR EXISTS (
                           SELECT 1 FROM conversation_messages matched
                           WHERE matched.conversation_id = c.id
                             AND instr(lower(matched.content), lower(?)) > 0
                       ))
                       GROUP BY c.id ORDER BY c.updated_at DESC, c.id LIMIT ?""",
                    (project_id, project_id, search, search, search, limit),
                ).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as exc:
            raise ConversationError("conversation storage is unavailable", status=503) from exc

    def create_project(self, name: str) -> dict[str, Any]:
        normalized_name = self._validate_project_name(name)
        now = datetime.now(UTC).isoformat()
        project_id = uuid.uuid4().hex
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                count = connection.execute("SELECT count(*) FROM workspace_projects").fetchone()[0]
                if count >= self.MAX_PROJECTS:
                    raise ConversationError("project limit reached", status=409)
                if connection.execute(
                    "SELECT 1 FROM workspace_projects WHERE name = ? COLLATE NOCASE", (normalized_name,)
                ).fetchone():
                    raise ConversationError("a project with this name already exists", status=409)
                connection.execute(
                    "INSERT INTO workspace_projects (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (project_id, normalized_name, now, now),
                )
                connection.commit()
        except sqlite3.Error as exc:
            raise ConversationError("project storage is unavailable", status=503) from exc
        return next(project for project in self.list_projects() if project["id"] == project_id)

    def list_projects(self) -> list[dict[str, Any]]:
        try:
            with self._connection() as connection:
                rows = connection.execute(
                    """SELECT p.id, p.name, p.created_at, p.updated_at, count(c.id) AS conversation_count
                       FROM workspace_projects p LEFT JOIN conversations c ON c.project_id = p.id
                       GROUP BY p.id ORDER BY p.name COLLATE NOCASE, p.id LIMIT ?""",
                    (self.MAX_PROJECTS,),
                ).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as exc:
            raise ConversationError("project storage is unavailable", status=503) from exc

    def rename_project(self, project_id: str, name: str) -> dict[str, Any]:
        self._validate_project_id(project_id)
        normalized_name = self._validate_project_name(name)
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                if not connection.execute(
                    "SELECT 1 FROM workspace_projects WHERE id = ?", (project_id,)
                ).fetchone():
                    raise ConversationError("project not found", status=404)
                if connection.execute(
                    "SELECT 1 FROM workspace_projects WHERE name = ? COLLATE NOCASE AND id <> ?",
                    (normalized_name, project_id),
                ).fetchone():
                    raise ConversationError("a project with this name already exists", status=409)
                cursor = connection.execute(
                    "UPDATE workspace_projects SET name = ?, updated_at = ? WHERE id = ?",
                    (normalized_name, datetime.now(UTC).isoformat(), project_id),
                )
                if cursor.rowcount != 1:
                    raise ConversationError("project not found", status=404)
                connection.commit()
        except sqlite3.Error as exc:
            raise ConversationError("project storage is unavailable", status=503) from exc
        return next(project for project in self.list_projects() if project["id"] == project_id)

    def delete_project(self, project_id: str) -> bool:
        self._validate_project_id(project_id)
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute("DELETE FROM workspace_projects WHERE id = ?", (project_id,))
                connection.commit()
                return cursor.rowcount == 1
        except sqlite3.Error as exc:
            raise ConversationError("project storage is unavailable", status=503) from exc

    def assign_project(self, conversation_id: str, project_id: str | None) -> dict[str, Any]:
        self._validate_id(conversation_id)
        if project_id is not None:
            self._validate_project_id(project_id)
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                if (
                    project_id is not None
                    and not connection.execute(
                        "SELECT 1 FROM workspace_projects WHERE id = ?", (project_id,)
                    ).fetchone()
                ):
                    raise ConversationError("project not found", status=404)
                cursor = connection.execute(
                    "UPDATE conversations SET project_id = ?, updated_at = ? WHERE id = ?",
                    (project_id, datetime.now(UTC).isoformat(), conversation_id),
                )
                if cursor.rowcount != 1:
                    raise ConversationError("conversation not found", status=404)
                connection.commit()
        except sqlite3.Error as exc:
            raise ConversationError("conversation storage is unavailable", status=503) from exc
        return self.get(conversation_id)

    def assign_assistant(self, conversation_id: str, assistant_id: str | None) -> dict[str, Any]:
        self._validate_id(conversation_id)
        if assistant_id is not None:
            self._validate_assistant_id(assistant_id)
        try:
            with self._connection() as connection:
                cursor = connection.execute(
                    "UPDATE conversations SET assistant_id = ?, updated_at = ? WHERE id = ?",
                    (assistant_id, datetime.now(UTC).isoformat(), conversation_id),
                )
                if cursor.rowcount != 1:
                    raise ConversationError("conversation not found", status=404)
                connection.commit()
        except sqlite3.Error as exc:
            raise ConversationError("conversation storage is unavailable", status=503) from exc
        return self.get(conversation_id)

    def detach_assistant(self, assistant_id: str) -> int:
        self._validate_assistant_id(assistant_id)
        try:
            with self._connection() as connection:
                cursor = connection.execute(
                    "UPDATE conversations SET assistant_id = NULL, updated_at = ? WHERE assistant_id = ?",
                    (datetime.now(UTC).isoformat(), assistant_id),
                )
                connection.commit()
                return cursor.rowcount
        except sqlite3.Error as exc:
            raise ConversationError("conversation storage is unavailable", status=503) from exc

    def get(self, conversation_id: str) -> dict[str, Any]:
        self._validate_id(conversation_id)
        try:
            with self._connection() as connection:
                conversation = connection.execute(
                    """SELECT id, title, model, project_id, assistant_id, created_at, updated_at
                       FROM conversations WHERE id = ?""",
                    (conversation_id,),
                ).fetchone()
                if conversation is None:
                    raise ConversationError("conversation not found", status=404)
                messages = connection.execute(
                    """SELECT id, role, content, citations, created_at FROM conversation_messages
                       WHERE conversation_id = ? ORDER BY sequence""",
                    (conversation_id,),
                ).fetchall()
            result = dict(conversation)
            result["messages"] = [
                {
                    "id": row["id"],
                    "role": row["role"],
                    "content": row["content"],
                    "citations": json.loads(row["citations"]),
                    "created_at": row["created_at"],
                }
                for row in messages
            ]
            return result
        except sqlite3.Error as exc:
            raise ConversationError("conversation storage is unavailable", status=503) from exc

    def append_messages(
        self, conversation_id: str, messages: list[dict[str, Any]], *, model: str | None = None
    ) -> dict[str, Any]:
        self._validate_id(conversation_id)
        if not isinstance(messages, list) or not 1 <= len(messages) <= 20:
            raise ConversationError("messages must contain 1 to 20 entries")
        if model is not None and (not isinstance(model, str) or len(model) > 256):
            raise ConversationError("model must contain at most 256 characters")
        normalized = [self._normalize_message(message) for message in messages]
        now = datetime.now(UTC).isoformat()
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT title, model FROM conversations WHERE id = ?", (conversation_id,)
                ).fetchone()
                if row is None:
                    raise ConversationError("conversation not found", status=404)
                count = connection.execute(
                    "SELECT count(*) FROM conversation_messages WHERE conversation_id = ?", (conversation_id,)
                ).fetchone()[0]
                if count + len(normalized) > self.MAX_MESSAGES_PER_CONVERSATION:
                    raise ConversationError("conversation message limit reached", status=409)
                stored_bytes = connection.execute(
                    "SELECT COALESCE(sum(length(CAST(content AS BLOB))), 0) FROM conversation_messages"
                ).fetchone()[0]
                incoming_bytes = sum(len(message["content"].encode("utf-8")) for message in normalized)
                if stored_bytes + incoming_bytes > self.MAX_TOTAL_CONTENT_BYTES:
                    raise ConversationError("conversation storage quota would be exceeded", status=413)
                for offset, message in enumerate(normalized, start=count):
                    connection.execute(
                        """INSERT INTO conversation_messages
                           (id, conversation_id, sequence, role, content, citations, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (
                            uuid.uuid4().hex,
                            conversation_id,
                            offset,
                            message["role"],
                            message["content"],
                            json.dumps(message["citations"], separators=(",", ":")),
                            now,
                        ),
                    )
                first_user = connection.execute(
                    "SELECT content FROM conversation_messages WHERE conversation_id = ? AND role = 'user' ORDER BY sequence LIMIT 1",
                    (conversation_id,),
                ).fetchone()
                title = str(row["title"])
                if title == "New chat" and first_user is not None:
                    title = first_user["content"].strip().splitlines()[0][:120] or "New chat"
                connection.execute(
                    "UPDATE conversations SET title = ?, model = ?, updated_at = ? WHERE id = ?",
                    (title, model.strip() if model is not None else row["model"], now, conversation_id),
                )
                connection.commit()
        except sqlite3.Error as exc:
            raise ConversationError("conversation storage is unavailable", status=503) from exc
        return self.get(conversation_id)

    def delete(self, conversation_id: str) -> bool:
        self._validate_id(conversation_id)
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
                connection.commit()
                return cursor.rowcount == 1
        except sqlite3.Error as exc:
            raise ConversationError("conversation storage is unavailable", status=503) from exc

    def rename(self, conversation_id: str, title: str) -> dict[str, Any]:
        self._validate_id(conversation_id)
        if not isinstance(title, str) or not title.strip() or len(title.strip()) > 120:
            raise ConversationError("title must contain 1 to 120 characters")
        now = datetime.now(UTC).isoformat()
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                    (title.strip(), now, conversation_id),
                )
                if cursor.rowcount != 1:
                    raise ConversationError("conversation not found", status=404)
                connection.commit()
        except sqlite3.Error as exc:
            raise ConversationError("conversation storage is unavailable", status=503) from exc
        return self.get(conversation_id)

    @classmethod
    def _normalize_message(cls, message: Any) -> dict[str, Any]:
        if not isinstance(message, dict) or set(message) - {"role", "content", "citations"}:
            raise ConversationError("each message must include only role, content, and citations")
        role = message.get("role")
        content = message.get("content")
        if not isinstance(role, str) or role not in {"user", "assistant"}:
            raise ConversationError("message role must be user or assistant")
        if not isinstance(content, str) or not content.strip() or len(content) > cls.MAX_CONTENT_CHARS:
            raise ConversationError(f"message content must contain 1 to {cls.MAX_CONTENT_CHARS} characters")
        try:
            content.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ConversationError("message content must be valid Unicode text") from exc
        citations = message.get("citations", [])
        if role != "assistant" and citations != []:
            raise ConversationError("only assistant messages may include citations")
        if not isinstance(citations, list) or len(citations) > cls.MAX_CITATIONS:
            raise ConversationError(f"citations must contain at most {cls.MAX_CITATIONS} entries")
        safe_citations = []
        for citation in citations:
            if not isinstance(citation, dict) or set(citation) - {"number", "title", "url", "source"}:
                raise ConversationError("citation entries contain unsupported fields")
            number, title, url = citation.get("number"), citation.get("title"), citation.get("url")
            source = citation.get("source")
            if source is not None and source not in {"local", "connected"}:
                raise ConversationError("citation source must be local or connected")
            if isinstance(number, bool) or not isinstance(number, int) or number < 1:
                raise ConversationError("citation number must be a positive integer")
            if not isinstance(title, str) or not title.strip() or len(title) > 300:
                raise ConversationError("citation title must contain 1 to 300 characters")
            safe_url = None
            if url is not None:
                if not isinstance(url, str) or len(url) > 2048:
                    raise ConversationError("citation URL is invalid")
                try:
                    parsed = urlsplit(url)
                    port = parsed.port
                except ValueError as exc:
                    raise ConversationError("citation URL is invalid") from exc
                if port == 0:
                    raise ConversationError("citation URL is invalid")
                if (
                    parsed.scheme not in {"http", "https"}
                    or not parsed.hostname
                    or parsed.username
                    or parsed.password
                ):
                    raise ConversationError("citation URL must be an HTTP(S) URL without credentials")
                safe_url = url
            safe_citation = {"number": number, "title": title.strip(), "url": safe_url}
            if source is not None:
                safe_citation["source"] = source
            safe_citations.append(safe_citation)
        return {"role": role, "content": content, "citations": safe_citations}

    @staticmethod
    def _validate_id(conversation_id: str) -> None:
        if not isinstance(conversation_id, str) or not re.fullmatch(r"[a-f0-9]{32}", conversation_id):
            raise ConversationError("invalid conversation identifier")

    @staticmethod
    def _validate_project_id(project_id: str) -> None:
        if not isinstance(project_id, str) or not re.fullmatch(r"[a-f0-9]{32}", project_id):
            raise ConversationError("invalid project identifier")

    @staticmethod
    def _validate_assistant_id(assistant_id: str) -> None:
        if not isinstance(assistant_id, str) or not re.fullmatch(
            r"(?:builtin_[a-z0-9_]{1,64}|[a-f0-9]{32})", assistant_id
        ):
            raise ConversationError("invalid assistant profile identifier")

    @classmethod
    def _validate_project_name(cls, name: Any) -> str:
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
            raise ConversationError("project name must contain 1 to 120 characters")
        try:
            name = name.strip()
            name.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ConversationError("project name must be valid Unicode text") from exc
        return name

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = None
        try:
            self.database_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            try:
                descriptor = os.open(self.database_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                file_info = self.database_path.stat(follow_symlinks=False)
                if not stat.S_ISREG(file_info.st_mode) or (
                    os.name == "posix" and stat.S_IMODE(file_info.st_mode) & 0o077
                ):
                    raise ConversationError(
                        "conversation database must be a private regular file", status=503
                    ) from None
            else:
                os.close(descriptor)
            connection = sqlite3.connect(self.database_path, timeout=5.0)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("""CREATE TABLE IF NOT EXISTS workspace_projects (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                )""")
            connection.execute("""CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, model TEXT NOT NULL,
                    project_id TEXT REFERENCES workspace_projects(id) ON DELETE SET NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                )""")
            conversation_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(conversations)").fetchall()
            }
            if "project_id" not in conversation_columns:
                connection.execute(
                    "ALTER TABLE conversations ADD COLUMN project_id TEXT REFERENCES workspace_projects(id) ON DELETE SET NULL"
                )
            if "assistant_id" not in conversation_columns:
                connection.execute("ALTER TABLE conversations ADD COLUMN assistant_id TEXT")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_conversations_project ON conversations(project_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_conversations_assistant ON conversations(assistant_id)"
            )
            connection.execute("""CREATE TABLE IF NOT EXISTS conversation_messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    sequence INTEGER NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL,
                    citations TEXT NOT NULL, created_at TEXT NOT NULL,
                    UNIQUE(conversation_id, sequence)
                )""")
            yield connection
        except OSError as exc:
            raise ConversationError("conversation storage path is unavailable", status=503) from exc
        except sqlite3.Error as exc:
            raise ConversationError("conversation storage is unavailable", status=503) from exc
        finally:
            if connection is not None:
                connection.close()
