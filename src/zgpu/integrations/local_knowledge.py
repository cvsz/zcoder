"""Persistent local text knowledge library with bounded lexical retrieval."""

from __future__ import annotations

import hashlib
import json
import math
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

from zgpu.integrations.lexical_retrieval import bm25_scores


class LocalKnowledgeError(ValueError):
    """Invalid local knowledge input or unavailable local storage."""

    def __init__(self, message: str, status: int = 400):
        self.status = status
        super().__init__(message)


class LocalKnowledgeStore:
    """Store local text and Markdown documents in SQLite and search with FTS5."""

    MAX_TITLE_CHARS = 200
    MAX_CONTENT_BYTES = 262_144
    MAX_DOCUMENTS = 500
    MAX_TOTAL_CONTENT_BYTES = 52_428_800
    MAX_QUERY_CHARS = 256
    MAX_QUERY_TERMS = 12
    MAX_REINDEX_BATCH = 5

    def __init__(self, database_path: str | Path, *, embedding_provider: Any | None = None):
        self.database_path = Path(database_path).expanduser()
        self.embedding_provider = embedding_provider

    @property
    def retrieval_mode(self) -> str:
        return self.retrieval_status()["retrieval"]

    def retrieval_status(self, *, project_id: str | None = "*") -> dict[str, Any]:
        scope_sql, scope_params = self._project_scope(project_id)
        provider = self.embedding_provider
        try:
            with self._connection() as connection:
                total = connection.execute(
                    f"SELECT count(*) FROM documents d WHERE {scope_sql}", scope_params  # nosec B608
                ).fetchone()[0]
                indexed = 0
                if provider is not None:
                    indexed = connection.execute(
                        f"SELECT count(*) FROM documents d WHERE {scope_sql} AND d.embedding_model = ? AND d.embedding_json IS NOT NULL",  # nosec B608
                        (*scope_params, provider.model),
                    ).fetchone()[0]
        except sqlite3.Error as exc:
            raise LocalKnowledgeError("local knowledge status is unavailable", status=503) from exc
        return {
            "retrieval": "hybrid" if indexed and provider is not None else "lexical",
            "embedding_configured": provider is not None,
            "embedding_model": provider.model if provider is not None else None,
            "indexed_document_count": indexed,
            "pending_document_count": total - indexed,
            "total_document_count": total,
        }

    def reindex_missing(self, *, limit: int = 5, project_id: str | None = "*") -> dict[str, Any]:
        provider = self.embedding_provider
        if provider is None:
            raise LocalKnowledgeError(
                "semantic indexing requires a configured embedding provider", status=503
            )
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= self.MAX_REINDEX_BATCH:
            raise LocalKnowledgeError(f"reindex limit must be between 1 and {self.MAX_REINDEX_BATCH}")
        scope_sql, scope_params = self._project_scope(project_id)
        try:
            with self._connection() as connection:
                pending = connection.execute(
                    f"""SELECT d.id, d.content FROM documents d
                        WHERE {scope_sql} AND (d.embedding_json IS NULL OR d.embedding_model IS NULL OR d.embedding_model != ?)
                        ORDER BY d.created_at, d.id LIMIT ?""",  # nosec B608
                    (*scope_params, provider.model, limit),
                ).fetchall()
        except sqlite3.Error as exc:
            raise LocalKnowledgeError("local knowledge index is unavailable", status=503) from exc

        indexed_count = 0
        failed_count = 0
        failure = None
        for document in pending:
            try:
                vector = self._create_embedding(document["content"])
                encoded_vector = json.dumps(vector, separators=(",", ":"), allow_nan=False)
                with self._connection() as connection:
                    connection.execute("BEGIN IMMEDIATE")
                    self._validate_embedding_dimensions(connection, provider.model, vector)
                    cursor = connection.execute(
                        """UPDATE documents SET embedding_json = ?, embedding_model = ?
                           WHERE id = ? AND (embedding_json IS NULL OR embedding_model IS NULL OR embedding_model != ?)""",
                        (encoded_vector, provider.model, document["id"], provider.model),
                    )
                    connection.commit()
                    indexed_count += cursor.rowcount
            except LocalKnowledgeError as exc:
                failed_count += 1
                failure = str(exc)
                break
            except sqlite3.Error:
                failed_count += 1
                failure = "local knowledge index is unavailable"
                break

        status = self.retrieval_status(project_id=project_id)
        return {
            "model": provider.model,
            "selected_count": len(pending),
            "indexed_count": indexed_count,
            "failed_count": failed_count,
            "pending_document_count": status["pending_document_count"],
            "complete": status["pending_document_count"] == 0,
            "error": failure,
        }

    def list_documents(self, *, limit: int = 100, project_id: str | None = "*") -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise LocalKnowledgeError("limit must be between 1 and 100")
        scope_sql, scope_params = self._project_scope(project_id)
        with self._connection() as connection:
            rows = connection.execute(
                f"""SELECT id, title, sha256, project_id, length(CAST(content AS BLOB)) AS content_bytes,
                           created_at, updated_at FROM documents d
                     WHERE {scope_sql} ORDER BY updated_at DESC, id LIMIT ?""",  # nosec B608
            ).fetchall()
        return [dict(row) for row in rows]

    def add_document(self, title: str, content: str, *, project_id: str | None = None) -> dict[str, Any]:
        if not isinstance(title, str) or not title.strip() or len(title.strip()) > self.MAX_TITLE_CHARS:
            raise LocalKnowledgeError(f"title must contain 1 to {self.MAX_TITLE_CHARS} characters")
        if not isinstance(content, str) or not content.strip():
            raise LocalKnowledgeError("content must contain non-whitespace text")
        try:
            title.strip().encode("utf-8")
            content_bytes = content.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise LocalKnowledgeError("title and content must be valid Unicode text") from exc
        if project_id is not None and (
            not isinstance(project_id, str) or not re.fullmatch(r"[a-f0-9]{32}", project_id)
        ):
            raise LocalKnowledgeError("invalid project identifier")
        if len(content_bytes) > self.MAX_CONTENT_BYTES:
            raise LocalKnowledgeError(
                f"content must be at most {self.MAX_CONTENT_BYTES} UTF-8 bytes", status=413
            )

        now = datetime.now(UTC).isoformat()
        document_id = uuid.uuid4().hex
        digest = hashlib.sha256(content_bytes).hexdigest()
        embedding = self._create_embedding(content) if self.embedding_provider is not None else None
        embedding_json = json.dumps(embedding, separators=(",", ":"), allow_nan=False) if embedding else None
        embedding_model = self.embedding_provider.model if embedding is not None else None
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                count, current_bytes = connection.execute(
                    "SELECT count(*), COALESCE(sum(length(CAST(content AS BLOB))), 0) FROM documents"
                ).fetchone()
                if count >= self.MAX_DOCUMENTS:
                    raise LocalKnowledgeError(
                        f"local library is limited to {self.MAX_DOCUMENTS} documents", status=409
                    )
                if current_bytes + len(content_bytes) > self.MAX_TOTAL_CONTENT_BYTES:
                    raise LocalKnowledgeError("local library content quota would be exceeded", status=413)
                if embedding is not None:
                    self._validate_embedding_dimensions(connection, embedding_model, embedding)
                has_fts = self._has_fts(connection)
                cursor = connection.execute(
                    """INSERT INTO documents (
                           id, title, content, sha256, project_id, created_at, updated_at, embedding_json, embedding_model
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        document_id,
                        title.strip(),
                        content,
                        digest,
                        project_id,
                        now,
                        now,
                        embedding_json,
                        embedding_model,
                    ),
                )
                if has_fts:
                    connection.execute(
                        "INSERT INTO documents_fts (rowid, title, content) VALUES (?, ?, ?)",
                        (cursor.lastrowid, title.strip(), content),
                    )
                connection.commit()
        except sqlite3.Error as exc:
            raise LocalKnowledgeError("local knowledge storage is unavailable", status=503) from exc
        return {
            "id": document_id,
            "title": title.strip(),
            "sha256": digest,
            "project_id": project_id,
            "content_bytes": len(content_bytes),
            "created_at": now,
            "updated_at": now,
            "embedding_model": embedding_model,
        }

    def delete_document(self, document_id: str) -> bool:
        if not isinstance(document_id, str) or not re.fullmatch(r"[a-f0-9]{32}", document_id):
            raise LocalKnowledgeError("invalid document identifier")
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT rowid FROM documents WHERE id = ?", (document_id,)
                ).fetchone()
                if row is None:
                    connection.rollback()
                    return False
                if self._has_fts(connection):
                    connection.execute("DELETE FROM documents_fts WHERE rowid = ?", (row["rowid"],))
                connection.execute("DELETE FROM documents WHERE id = ?", (document_id,))
                connection.commit()
                return True
        except sqlite3.Error as exc:
            raise LocalKnowledgeError("local knowledge storage is unavailable") from exc

    def search(self, query: str, *, limit: int = 10, project_id: str | None = None) -> list[dict[str, Any]]:
        if not isinstance(query, str) or not query.strip() or len(query) > self.MAX_QUERY_CHARS:
            raise LocalKnowledgeError(f"query must contain 1 to {self.MAX_QUERY_CHARS} characters")
        try:
            query.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise LocalKnowledgeError("query must be valid Unicode text") from exc
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
            raise LocalKnowledgeError("limit must be between 1 and 20")
        scope_sql, scope_params = self._project_scope(project_id)
        terms = re.findall(r"[^\W_]+", query.casefold(), flags=re.UNICODE)[: self.MAX_QUERY_TERMS]
        if not terms:
            raise LocalKnowledgeError("query must contain searchable text")
        query_embedding = self._create_embedding(query) if self.embedding_provider is not None else None

        try:
            with self._connection() as connection:
                if self._has_fts(connection):
                    expression = " AND ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms)
                    lexical_rows = connection.execute(
                        """SELECT d.id, d.title, d.content, d.sha256, d.project_id, d.updated_at
                           FROM documents_fts f JOIN documents d ON d.rowid = f.rowid
                           WHERE documents_fts MATCH ? AND """  # nosec B608
                        + scope_sql
                        + " ORDER BY bm25(documents_fts) LIMIT ?",
                        (expression, *scope_params, limit),
                    ).fetchall()
                else:
                    candidates = connection.execute(
                        f"""SELECT d.id, d.title, d.content, d.sha256, d.project_id, d.updated_at
                            FROM documents d WHERE {scope_sql} ORDER BY d.updated_at DESC, d.id""",  # nosec B608
                        scope_params,
                    ).fetchall()
                    matching_rows = [
                        row
                        for row in candidates
                        if all(term in f"{row['title']}\n{row['content']}".casefold() for term in terms)
                    ]
                    scores = bm25_scores(
                        terms,
                        [f"{row['title']}\n{row['content']}" for row in matching_rows],
                    )
                    lexical_rows = [
                        row
                        for _, row in sorted(
                            zip(scores, matching_rows, strict=True),
                            key=lambda item: (item[0], item[1]["updated_at"], item[1]["id"]),
                            reverse=True,
                        )[:limit]
                    ]

                semantic_rows = []
                if query_embedding is not None:
                    semantic_candidates = connection.execute(
                        f"""SELECT d.id, d.title, d.content, d.sha256, d.project_id, d.updated_at,
                                   d.embedding_json, d.embedding_model
                            FROM documents d WHERE {scope_sql} ORDER BY d.updated_at DESC, d.id""",  # nosec B608
                        scope_params,
                    ).fetchall()
                    semantic_scores = []
                    for candidate in semantic_candidates:
                        if (
                            candidate["embedding_model"] != self.embedding_provider.model
                            or not candidate["embedding_json"]
                        ):
                            continue
                        try:
                            vector = json.loads(candidate["embedding_json"])
                            similarity = self._cosine_similarity(query_embedding, vector)
                        except (TypeError, ValueError, json.JSONDecodeError):
                            continue
                        if similarity >= 0.1:
                            semantic_scores.append((similarity, candidate))
                    semantic_rows = [
                        candidate
                        for _, candidate in sorted(
                            semantic_scores,
                            key=lambda item: (item[0], item[1]["updated_at"], item[1]["id"]),
                            reverse=True,
                        )[:limit]
                    ]

                if query_embedding is None:
                    rows = lexical_rows
                else:
                    fused: dict[str, tuple[float, Any]] = {}
                    for ranked_rows in (lexical_rows, semantic_rows):
                        for rank, candidate in enumerate(ranked_rows, start=1):
                            document_id = candidate["id"]
                            score, _ = fused.get(document_id, (0.0, candidate))
                            fused[document_id] = (score + 1.0 / (60 + rank), candidate)
                    rows = [
                        candidate
                        for _, candidate in sorted(
                            fused.values(),
                            key=lambda item: (item[0], item[1]["updated_at"], item[1]["id"]),
                            reverse=True,
                        )[:limit]
                    ]
        except sqlite3.Error as exc:
            raise LocalKnowledgeError("local knowledge search is unavailable", status=503) from exc

        results = []
        for row in rows:
            content = row["content"]
            excerpt = self._best_excerpt(content, terms)
            results.append(
                {
                    "id": row["id"],
                    "title": row["title"],
                    "excerpt": excerpt,
                    "sha256": row["sha256"],
                    "project_id": row["project_id"],
                    "updated_at": row["updated_at"],
                }
            )
        return results

    def _create_embedding(self, text: str) -> list[float]:
        try:
            vector = self.embedding_provider.embed(text)
        except Exception as exc:
            if isinstance(exc, LocalKnowledgeError):
                raise
            raise LocalKnowledgeError("configured embedding provider is unavailable", status=503) from exc
        if not isinstance(vector, list) or not vector or len(vector) > 4096:
            raise LocalKnowledgeError("embedding provider returned an invalid vector", status=502)
        normalized = []
        try:
            for value in vector:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise LocalKnowledgeError("embedding provider returned an invalid vector", status=502)
                numeric = float(value)
                if not math.isfinite(numeric) or abs(numeric) > 1_000_000:
                    raise LocalKnowledgeError("embedding provider returned an invalid vector", status=502)
                normalized.append(numeric)
        except OverflowError as exc:
            raise LocalKnowledgeError("embedding provider returned an invalid vector", status=502) from exc
        if not any(normalized):
            raise LocalKnowledgeError("embedding provider returned a zero vector", status=502)
        return normalized

    @staticmethod
    def _validate_embedding_dimensions(
        connection: sqlite3.Connection, model: str, vector: list[float]
    ) -> None:
        existing = connection.execute(
            "SELECT embedding_json FROM documents WHERE embedding_model = ? AND embedding_json IS NOT NULL LIMIT 1",
            (model,),
        ).fetchone()
        if existing is None:
            return
        try:
            existing_vector = json.loads(existing["embedding_json"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise LocalKnowledgeError("stored embedding metadata is corrupt", status=503) from exc
        if not isinstance(existing_vector, list) or len(existing_vector) != len(vector):
            raise LocalKnowledgeError("embedding provider returned an inconsistent vector size", status=502)

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        if not isinstance(right, list) or len(left) != len(right) or not right:
            raise ValueError("embedding dimensions do not match")
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in right):
            raise ValueError("stored embedding is invalid")
        try:
            right = [float(value) for value in right]
        except (OverflowError, TypeError, ValueError) as exc:
            raise ValueError("stored embedding is invalid") from exc
        if any(not math.isfinite(value) or abs(value) > 1_000_000 for value in right):
            raise ValueError("stored embedding is invalid")
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm == 0 or right_norm == 0:
            raise ValueError("zero embedding")
        return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)

    @staticmethod
    def _best_excerpt(content: str, terms: list[str], *, excerpt_chars: int = 300) -> str:
        """Choose a bounded passage containing the densest set of query terms."""
        if len(content) <= excerpt_chars:
            return content.strip()

        folded_parts = []
        source_offsets = []
        for source_offset, character in enumerate(content):
            folded_character = character.casefold()
            folded_parts.append(folded_character)
            source_offsets.extend([source_offset] * len(folded_character))
        folded_content = "".join(folded_parts)
        max_start = len(content) - excerpt_chars
        candidates = {0, max_start}
        unique_terms = tuple(dict.fromkeys(terms))

        for term in unique_terms:
            position = folded_content.find(term)
            while position >= 0:
                source_offset = source_offsets[position]
                candidate = max(0, min(source_offset - 100, max_start))
                candidates.add(min(((candidate + 12) // 24) * 24, max_start))
                position = folded_content.find(term, position + max(1, len(term)))

        best_start = 0
        best_score = (-1, -1, 0, 0)
        for start in candidates:
            excerpt = content[start : start + excerpt_chars]
            folded_excerpt = excerpt.casefold()
            distinct_matches = sum(term in folded_excerpt for term in unique_terms)
            total_matches = sum(folded_excerpt.count(term) for term in unique_terms)
            first_positions = [folded_excerpt.find(term) for term in unique_terms if term in folded_excerpt]
            term_span = max(first_positions) - min(first_positions) if first_positions else 0
            score = (distinct_matches, total_matches, -term_span, -start)
            if score > best_score:
                best_start = start
                best_score = score

        return content[best_start : best_start + excerpt_chars].strip()

    def detach_project(self, project_id: str) -> int:
        if not isinstance(project_id, str) or not re.fullmatch(r"[a-f0-9]{32}", project_id):
            raise LocalKnowledgeError("invalid project identifier")
        try:
            with self._connection() as connection:
                cursor = connection.execute(
                    "UPDATE documents SET project_id = NULL, updated_at = ? WHERE project_id = ?",
                    (datetime.now(UTC).isoformat(), project_id),
                )
                connection.commit()
                return cursor.rowcount
        except sqlite3.Error as exc:
            raise LocalKnowledgeError("local knowledge storage is unavailable", status=503) from exc

    @staticmethod
    def _project_scope(project_id: str | None) -> tuple[str, tuple[str, ...]]:
        if project_id == "*":
            return "1 = 1", ()
        if project_id is None:
            return "d.project_id IS NULL", ()
        if not isinstance(project_id, str) or not re.fullmatch(r"[a-f0-9]{32}", project_id):
            raise LocalKnowledgeError("invalid project identifier")
        return "(d.project_id IS NULL OR d.project_id = ?)", (project_id,)

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
                    raise LocalKnowledgeError(
                        "knowledge database must be a private regular file", status=503
                    ) from None
            else:
                os.close(descriptor)
            connection = sqlite3.connect(self.database_path, timeout=5.0)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute("""CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    project_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    embedding_json TEXT,
                    embedding_model TEXT
                )""")
            document_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(documents)").fetchall()
            }
            if "project_id" not in document_columns:
                connection.execute("ALTER TABLE documents ADD COLUMN project_id TEXT")
            if "embedding_json" not in document_columns:
                connection.execute("ALTER TABLE documents ADD COLUMN embedding_json TEXT")
            if "embedding_model" not in document_columns:
                connection.execute("ALTER TABLE documents ADD COLUMN embedding_model TEXT")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_documents_project ON documents(project_id)")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_documents_embedding_model ON documents(embedding_model)"
            )
            yield connection
        except OSError as exc:
            raise LocalKnowledgeError("local knowledge storage path is unavailable", status=503) from exc
        except sqlite3.Error as exc:
            raise LocalKnowledgeError("local knowledge storage is unavailable", status=503) from exc
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _has_fts(connection: sqlite3.Connection) -> bool:
        try:
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'documents_fts'"
            ).fetchone()
            if exists is None:
                connection.execute("CREATE VIRTUAL TABLE documents_fts USING fts5(title, content)")
                connection.execute(
                    "INSERT INTO documents_fts (rowid, title, content) SELECT rowid, title, content FROM documents"
                )
            return True
        except sqlite3.OperationalError:
            return False
