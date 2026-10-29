"""Private storage and built-in instruction profiles for the zGPU workspace."""

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

BUILTIN_ASSISTANTS: tuple[dict[str, str], ...] = (
    {
        "id": "builtin_precise",
        "name": "Precise",
        "description": "Concise, technical, and precise responses.",
        "system_prompt": "Be concise, technical, and precise. Avoid fluff.",
    },
    {
        "id": "builtin_teaching",
        "name": "Teaching",
        "description": "Explain concepts step by step for a learner.",
        "system_prompt": "Explain concepts clearly, step by step, as if teaching a beginner.",
    },
    {
        "id": "builtin_creative",
        "name": "Creative",
        "description": "Explore inventive alternatives and approaches.",
        "system_prompt": "Be inventive and think outside the box.",
    },
    {
        "id": "builtin_socratic",
        "name": "Socratic",
        "description": "Guide reasoning with focused questions.",
        "system_prompt": "Ask probing questions and guide the user to discover answers.",
    },
    {
        "id": "builtin_pragmatic",
        "name": "Pragmatic",
        "description": "Prioritize practical working outcomes.",
        "system_prompt": "Focus on practical, working solutions over theory.",
    },
    {
        "id": "builtin_code_generator",
        "name": "Code Generator",
        "description": "Produce complete, runnable code for a request.",
        "system_prompt": "You are a full-project code generation agent. Produce complete, runnable code for the request, not a partial sketch.",
    },
    {
        "id": "builtin_code_reviewer",
        "name": "Code Reviewer",
        "description": "Review code for concrete correctness and maintainability issues.",
        "system_prompt": "You are a code review agent. Focus on correctness, readability, and maintainability; call out concrete issues with line-level detail.",
    },
    {
        "id": "builtin_testing_agent",
        "name": "Test Engineer",
        "description": "Design tests that include edge cases and failure modes.",
        "system_prompt": "You are a testing agent. Produce comprehensive test suites, covering edge cases and failure modes, not just the happy path.",
    },
    {
        "id": "builtin_documentation_agent",
        "name": "Documentation Writer",
        "description": "Write clear documentation for new readers.",
        "system_prompt": "You are a documentation agent. Write clear docs, READMEs, and API references aimed at a reader new to this codebase.",
    },
    {
        "id": "builtin_optimizer",
        "name": "Performance Analyst",
        "description": "Find bottlenecks and suggest measurable improvements.",
        "system_prompt": "You are a performance optimization agent. Identify concrete bottlenecks and propose measurable improvements.",
    },
    {
        "id": "builtin_security_auditor",
        "name": "Security Auditor",
        "description": "Review security boundaries and rate concrete findings.",
        "system_prompt": "You are a security audit agent. Review for vulnerabilities (injection, auth, secrets handling, unsafe deserialization, etc.) and rate severity for each finding.",
    },
    {
        "id": "builtin_full_stack",
        "name": "Full Stack Engineer",
        "description": "Consider frontend, backend, and data layers together.",
        "system_prompt": "You are a full-stack engineering agent. Consider frontend, backend, and data-layer concerns together when responding.",
    },
)
_BUILTIN_BY_ID = {profile["id"]: profile for profile in BUILTIN_ASSISTANTS}


class AssistantProfileError(ValueError):
    """Invalid assistant profile input or unavailable local storage."""

    def __init__(self, message: str, status: int = 400):
        self.status = status
        super().__init__(message)


class AssistantProfiles:
    """Store user-created assistants and combine them with fixed built-ins."""

    MAX_CUSTOM_PROFILES = 50
    MAX_NAME_CHARS = 120
    MAX_DESCRIPTION_CHARS = 240
    MAX_PROMPT_CHARS = 8_000
    MAX_TOTAL_PROMPT_BYTES = 1_048_576

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path).expanduser()

    def list(self) -> list[dict[str, Any]]:
        try:
            with self._connection() as connection:
                rows = connection.execute(
                    """SELECT id, name, description, system_prompt, created_at, updated_at
                       FROM assistant_profiles ORDER BY name COLLATE NOCASE, id"""
                ).fetchall()
            return [dict(profile, builtin=True) for profile in BUILTIN_ASSISTANTS] + [
                dict(row, builtin=False) for row in rows
            ]
        except sqlite3.Error as exc:
            raise AssistantProfileError("assistant profile storage is unavailable", status=503) from exc

    def get(self, profile_id: str) -> dict[str, Any]:
        if not isinstance(profile_id, str):
            raise AssistantProfileError("invalid assistant profile identifier")
        builtin = _BUILTIN_BY_ID.get(profile_id)
        if builtin is not None:
            return dict(builtin, builtin=True)
        self._validate_custom_id(profile_id)
        try:
            with self._connection() as connection:
                row = connection.execute(
                    """SELECT id, name, description, system_prompt, created_at, updated_at
                       FROM assistant_profiles WHERE id = ?""",
                    (profile_id,),
                ).fetchone()
            if row is None:
                raise AssistantProfileError("assistant profile not found", status=404)
            return dict(row, builtin=False)
        except sqlite3.Error as exc:
            raise AssistantProfileError("assistant profile storage is unavailable", status=503) from exc

    def create(self, name: str, description: str, system_prompt: str) -> dict[str, Any]:
        name, description, system_prompt = self._validate_profile(name, description, system_prompt)
        profile_id = uuid.uuid4().hex
        now = datetime.now(UTC).isoformat()
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                count, total = connection.execute(
                    "SELECT count(*), COALESCE(sum(length(CAST(system_prompt AS BLOB))), 0) FROM assistant_profiles"
                ).fetchone()
                if count >= self.MAX_CUSTOM_PROFILES:
                    raise AssistantProfileError("custom assistant profile limit reached", status=409)
                if total + len(system_prompt.encode("utf-8")) > self.MAX_TOTAL_PROMPT_BYTES:
                    raise AssistantProfileError(
                        "assistant profile storage quota would be exceeded", status=413
                    )
                connection.execute(
                    """INSERT INTO assistant_profiles
                       (id, name, description, system_prompt, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)""",
                    (profile_id, name, description, system_prompt, now, now),
                )
                connection.commit()
        except sqlite3.Error as exc:
            raise AssistantProfileError("assistant profile storage is unavailable", status=503) from exc
        return self.get(profile_id)

    def update(self, profile_id: str, name: str, description: str, system_prompt: str) -> dict[str, Any]:
        self._validate_custom_id(profile_id)
        name, description, system_prompt = self._validate_profile(name, description, system_prompt)
        now = datetime.now(UTC).isoformat()
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                exists = connection.execute(
                    "SELECT 1 FROM assistant_profiles WHERE id = ?", (profile_id,)
                ).fetchone()
                if exists is None:
                    raise AssistantProfileError("assistant profile not found", status=404)
                total = connection.execute(
                    """SELECT COALESCE(sum(length(CAST(system_prompt AS BLOB))), 0)
                       FROM assistant_profiles WHERE id != ?""",
                    (profile_id,),
                ).fetchone()[0]
                if total + len(system_prompt.encode("utf-8")) > self.MAX_TOTAL_PROMPT_BYTES:
                    raise AssistantProfileError(
                        "assistant profile storage quota would be exceeded", status=413
                    )
                connection.execute(
                    """UPDATE assistant_profiles SET name = ?, description = ?, system_prompt = ?, updated_at = ?
                       WHERE id = ?""",
                    (name, description, system_prompt, now, profile_id),
                )
                connection.commit()
        except sqlite3.Error as exc:
            raise AssistantProfileError("assistant profile storage is unavailable", status=503) from exc
        return self.get(profile_id)

    def delete(self, profile_id: str) -> bool:
        self._validate_custom_id(profile_id)
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute("DELETE FROM assistant_profiles WHERE id = ?", (profile_id,))
                connection.commit()
                return cursor.rowcount == 1
        except sqlite3.Error as exc:
            raise AssistantProfileError("assistant profile storage is unavailable", status=503) from exc

    @classmethod
    def _validate_profile(cls, name: Any, description: Any, system_prompt: Any) -> tuple[str, str, str]:
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > cls.MAX_NAME_CHARS:
            raise AssistantProfileError(f"name must contain 1 to {cls.MAX_NAME_CHARS} characters")
        if not isinstance(description, str) or len(description) > cls.MAX_DESCRIPTION_CHARS:
            raise AssistantProfileError(
                f"description must contain at most {cls.MAX_DESCRIPTION_CHARS} characters"
            )
        if (
            not isinstance(system_prompt, str)
            or not system_prompt.strip()
            or len(system_prompt) > cls.MAX_PROMPT_CHARS
        ):
            raise AssistantProfileError(f"system_prompt must contain 1 to {cls.MAX_PROMPT_CHARS} characters")
        try:
            name.strip().encode("utf-8")
            description.encode("utf-8")
            system_prompt.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise AssistantProfileError("assistant profile fields must be valid Unicode text") from exc
        return name.strip(), description.strip(), system_prompt

    @staticmethod
    def _validate_custom_id(profile_id: str) -> None:
        if not isinstance(profile_id, str) or not re.fullmatch(r"[a-f0-9]{32}", profile_id):
            raise AssistantProfileError("built-in assistant profiles cannot be changed")

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
                    raise AssistantProfileError(
                        "assistant profile database must be a private regular file", status=503
                    ) from None
            else:
                os.close(descriptor)
            connection = sqlite3.connect(self.database_path, timeout=5.0)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute("""CREATE TABLE IF NOT EXISTS assistant_profiles (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL, system_prompt TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                )""")
            yield connection
        except OSError as exc:
            raise AssistantProfileError("assistant profile storage path is unavailable", status=503) from exc
        except sqlite3.Error as exc:
            raise AssistantProfileError("assistant profile storage is unavailable", status=503) from exc
        finally:
            if connection is not None:
                connection.close()
