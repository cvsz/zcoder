from __future__ import annotations

import os
import sqlite3
import stat
import uuid

import pytest

from zgpu.integrations.local_knowledge import LocalKnowledgeError, LocalKnowledgeStore


class _SemanticEmbeddingStub:
    model = "local-test-embeddings"

    def embed(self, text: str) -> list[float]:
        lowered = text.casefold()
        return [1.0, 0.0] if "cat" in lowered or "feline" in lowered else [0.0, 1.0]


def test_local_knowledge_persists_searchable_sources_and_deletes(tmp_path):
    database = tmp_path / "private" / "knowledge.sqlite3"
    store = LocalKnowledgeStore(database)
    saved = store.add_document(
        "Kernel guide", "The tensor core uses four by four tiles for matrix operations."
    )

    assert saved["title"] == "Kernel guide"
    assert len(saved["sha256"]) == 64
    if os.name == "posix":
        assert stat.S_IMODE(database.stat().st_mode) == 0o600
    assert store.list_documents()[0]["id"] == saved["id"]
    assert "content" not in store.list_documents()[0]

    restarted = LocalKnowledgeStore(database)
    results = restarted.search("tensor core")
    assert len(results) == 1
    assert results[0]["id"] == saved["id"]
    assert "tensor core" in results[0]["excerpt"]

    assert restarted.delete_document(saved["id"]) is True
    assert restarted.delete_document(saved["id"]) is False
    assert restarted.search("tensor core") == []


def test_search_excerpt_selects_the_most_relevant_passage(tmp_path):
    store = LocalKnowledgeStore(tmp_path / "knowledge.sqlite3")
    filler = "Background notes without useful detail. " * 18
    relevant = "The cache and tokens are stored together for incremental decoding."
    store.add_document("Runtime notes", f"Cache appears in this introduction. {filler}{relevant}")

    results = store.search("cache tokens")

    assert len(results) == 1
    assert relevant in results[0]["excerpt"]


def test_best_excerpt_tracks_unicode_casefold_offsets():
    text = "Prefix " + ("unrelated words " * 25) + "Straße matching should remain aligned."

    excerpt = LocalKnowledgeStore._best_excerpt(text, ["strasse", "matching"])

    assert "Straße matching" in excerpt


def test_local_knowledge_rejects_invalid_inputs_and_enforces_limits(tmp_path):
    store = LocalKnowledgeStore(tmp_path / "knowledge.sqlite3")
    with pytest.raises(LocalKnowledgeError):
        store.add_document(" ", "some content")
    with pytest.raises(LocalKnowledgeError):
        store.add_document("title", " \n ")
    with pytest.raises(LocalKnowledgeError, match="valid Unicode"):
        store.add_document("bad\ud800title", "content")
    with pytest.raises(LocalKnowledgeError) as oversized:
        store.add_document("title", "x" * (store.MAX_CONTENT_BYTES + 1))
    assert oversized.value.status == 413
    with pytest.raises(LocalKnowledgeError):
        store.search(" ")
    with pytest.raises(LocalKnowledgeError, match="valid Unicode"):
        store.search("bad\ud800query")
    with pytest.raises(LocalKnowledgeError):
        store.delete_document("../database")

    store.MAX_DOCUMENTS = 1
    store.add_document("one", "one document")
    with pytest.raises(LocalKnowledgeError) as full:
        store.add_document("two", "another document")
    assert full.value.status == 409


def test_local_knowledge_enforces_total_content_quota(tmp_path):
    store = LocalKnowledgeStore(tmp_path / "knowledge.sqlite3")
    store.MAX_TOTAL_CONTENT_BYTES = 5
    store.add_document("one", "12345")
    with pytest.raises(LocalKnowledgeError) as full:
        store.add_document("two", "6")
    assert full.value.status == 413


def test_local_knowledge_counts_utf8_bytes_for_storage_quotas(tmp_path):
    store = LocalKnowledgeStore(tmp_path / "knowledge.sqlite3")
    store.MAX_TOTAL_CONTENT_BYTES = 3
    saved = store.add_document("一", "你")

    assert saved["content_bytes"] == 3
    assert store.list_documents()[0]["content_bytes"] == 3
    with pytest.raises(LocalKnowledgeError) as full:
        store.add_document("二", "好")
    assert full.value.status == 413


def test_local_knowledge_uses_sql_fallback_without_fts5(tmp_path, monkeypatch):
    monkeypatch.setattr(LocalKnowledgeStore, "_has_fts", staticmethod(lambda _connection: False))
    store = LocalKnowledgeStore(tmp_path / "knowledge.sqlite3")
    saved = store.add_document("Scheduling notes", "The state machine advances each warp by one cycle.")
    store.add_document("Warp notes", "A warp contains thirty-two lanes.")
    unicode_source = store.add_document("ΆΛΦΑ", "ΒΉΤΑ")

    results = store.search("state machine")

    assert [result["id"] for result in results] == [saved["id"]]
    assert [result["id"] for result in store.search("state warp")] == [saved["id"]]
    assert [result["id"] for result in store.search("άλφα βήτα")] == [unicode_source["id"]]


def test_sql_fallback_ranks_better_bm25_matches_first(tmp_path, monkeypatch):
    monkeypatch.setattr(LocalKnowledgeStore, "_has_fts", staticmethod(lambda _connection: False))
    store = LocalKnowledgeStore(tmp_path / "knowledge.sqlite3")
    long_document = store.add_document("Long reference", "state machine " + "unrelated configuration " * 80)
    concise_document = store.add_document("Scheduler", "state machine controls warp scheduling")

    results = store.search("state machine")

    assert [result["id"] for result in results] == [concise_document["id"], long_document["id"]]


def test_local_knowledge_scopes_search_and_listing_to_project_with_global_sources(tmp_path):
    store = LocalKnowledgeStore(tmp_path / "knowledge.sqlite3")
    project_one = uuid.uuid4().hex
    project_two = uuid.uuid4().hex
    general = store.add_document("General setup", "SIMT setup uses a shared base configuration.")
    first = store.add_document(
        "Kernel notes", "SIMT kernels use project one launch parameters.", project_id=project_one
    )
    second = store.add_document(
        "Worker notes", "SIMT workers use project two host configuration.", project_id=project_two
    )

    assert {item["id"] for item in store.search("SIMT", project_id=project_one)} == {
        general["id"],
        first["id"],
    }
    assert {item["id"] for item in store.search("SIMT")} == {general["id"]}
    assert {item["id"] for item in store.search("SIMT", project_id="*")} == {
        general["id"],
        first["id"],
        second["id"],
    }
    assert {item["id"] for item in store.list_documents(project_id=project_one)} == {
        general["id"],
        first["id"],
    }
    assert store.detach_project(project_one) == 1
    assert {item["id"] for item in store.search("SIMT")} == {general["id"], first["id"]}


def test_local_knowledge_migrates_existing_documents_without_changing_them(tmp_path):
    database = tmp_path / "existing.sqlite3"
    document_id = uuid.uuid4().hex
    with sqlite3.connect(database) as connection:
        connection.execute("""CREATE TABLE documents (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, content TEXT NOT NULL,
                sha256 TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )""")
        connection.execute(
            "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?)",
            (document_id, "Old note", "SIMT records are preserved", "a" * 64, "2026-01-01", "2026-01-01"),
        )
    database.chmod(0o600)

    store = LocalKnowledgeStore(database)
    document = store.list_documents()[0]
    assert document["id"] == document_id
    assert document["project_id"] is None
    assert store.search("SIMT")[0]["id"] == document_id
    with store._connection() as connection:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(documents)")}
    assert {"embedding_json", "embedding_model"} <= columns


def test_hybrid_search_adds_semantic_matches_and_persists_vectors(tmp_path):
    store = LocalKnowledgeStore(tmp_path / "knowledge.sqlite3", embedding_provider=_SemanticEmbeddingStub())
    semantic = store.add_document("Cat care", "A cat enjoys a warm resting place.")
    lexical = store.add_document("Feline companion notes", "Vehicle engineering terminology.")

    results = store.search("feline companion", limit=5)

    assert {result["id"] for result in results} == {semantic["id"], lexical["id"]}
    assert store.retrieval_status() == {
        "retrieval": "hybrid",
        "embedding_configured": True,
        "embedding_model": "local-test-embeddings",
        "indexed_document_count": 2,
        "pending_document_count": 0,
        "total_document_count": 2,
    }
    with store._connection() as connection:
        rows = connection.execute("SELECT embedding_json, embedding_model FROM documents").fetchall()
    assert all(row["embedding_json"] and row["embedding_model"] == "local-test-embeddings" for row in rows)


def test_hybrid_search_preserves_project_scope_and_legacy_documents(tmp_path):
    database = tmp_path / "knowledge.sqlite3"
    project = uuid.uuid4().hex
    other_project = uuid.uuid4().hex
    legacy_store = LocalKnowledgeStore(database)
    legacy = legacy_store.add_document("Old cat source", "A cat sleeps.")
    store = LocalKnowledgeStore(database, embedding_provider=_SemanticEmbeddingStub())
    general = store.add_document("General cat", "A cat is a companion animal.")
    scoped = store.add_document("Project cat", "Cat-based test fixtures.", project_id=project)
    store.add_document("Other project cat", "Cat data belongs elsewhere.", project_id=other_project)

    results = store.search("feline companion", project_id=project)

    assert {result["id"] for result in results} == {general["id"], scoped["id"]}
    assert [result["id"] for result in store.search("sleeps", project_id=project)] == [legacy["id"]]
    assert legacy_store.retrieval_status()["retrieval"] == "lexical"


def test_reindex_missing_embeddings_is_bounded_resumable_and_scoped(tmp_path):
    database = tmp_path / "knowledge.sqlite3"
    legacy_store = LocalKnowledgeStore(database)
    project = uuid.uuid4().hex
    other_project = uuid.uuid4().hex
    scoped = [
        legacy_store.add_document(
            f"Project {index}", f"A legacy project source number {index}.", project_id=project
        )
        for index in range(7)
    ]
    legacy_store.add_document("Other project", "A source outside this project.", project_id=other_project)
    store = LocalKnowledgeStore(database, embedding_provider=_SemanticEmbeddingStub())

    first = store.reindex_missing(project_id=project)
    second = store.reindex_missing(project_id=project)

    assert first["selected_count"] == 5
    assert first["indexed_count"] == 5
    assert first["pending_document_count"] == 2
    assert first["complete"] is False
    assert second["selected_count"] == 2
    assert second["indexed_count"] == 2
    assert second["pending_document_count"] == 0
    assert second["complete"] is True
    assert store.retrieval_status(project_id=project)["total_document_count"] == 7
    assert store.retrieval_status(project_id="*")["pending_document_count"] == 1
    with store._connection() as connection:
        indexed_ids = {
            row["id"]
            for row in connection.execute(
                "SELECT id FROM documents WHERE embedding_model = ?", (_SemanticEmbeddingStub.model,)
            )
        }
    assert indexed_ids == {document["id"] for document in scoped}


def test_reindex_stops_on_provider_failure_and_can_resume(tmp_path):
    class FlakyProvider(_SemanticEmbeddingStub):
        fail = True

        def embed(self, text):
            if self.fail:
                raise RuntimeError("provider unavailable")
            return super().embed(text)

    database = tmp_path / "knowledge.sqlite3"
    legacy = LocalKnowledgeStore(database)
    legacy.add_document("Legacy source", "A cat is a companion animal.")
    provider = FlakyProvider()
    store = LocalKnowledgeStore(database, embedding_provider=provider)

    failed = store.reindex_missing()
    assert failed["indexed_count"] == 0
    assert failed["failed_count"] == 1
    assert failed["pending_document_count"] == 1
    assert failed["error"] == "configured embedding provider is unavailable"
    provider.fail = False
    retried = store.reindex_missing()
    assert retried["indexed_count"] == 1
    assert retried["complete"] is True


def test_reindex_requires_provider_and_enforces_batch_bound(tmp_path):
    store = LocalKnowledgeStore(tmp_path / "knowledge.sqlite3")
    with pytest.raises(LocalKnowledgeError) as unavailable:
        store.reindex_missing()
    assert unavailable.value.status == 503
    configured = LocalKnowledgeStore(
        tmp_path / "configured.sqlite3", embedding_provider=_SemanticEmbeddingStub()
    )
    with pytest.raises(LocalKnowledgeError, match="between 1 and 5"):
        configured.reindex_missing(limit=6)


def test_reindex_repairs_incomplete_embedding_metadata(tmp_path):
    database = tmp_path / "knowledge.sqlite3"
    legacy = LocalKnowledgeStore(database)
    saved = legacy.add_document("Legacy source", "A cat is a companion animal.")
    with legacy._connection() as connection:
        connection.execute("UPDATE documents SET embedding_json = '[1,0]' WHERE id = ?", (saved["id"],))
        connection.commit()
    store = LocalKnowledgeStore(database, embedding_provider=_SemanticEmbeddingStub())

    result = store.reindex_missing()

    assert result["indexed_count"] == 1
    assert result["complete"] is True
    with store._connection() as connection:
        row = connection.execute(
            "SELECT embedding_json, embedding_model FROM documents WHERE id = ?", (saved["id"],)
        ).fetchone()
    assert row["embedding_model"] == _SemanticEmbeddingStub.model
    assert row["embedding_json"] == "[1.0,0.0]"


def test_local_knowledge_rejects_non_private_existing_database(tmp_path):
    database = tmp_path / "knowledge.sqlite3"
    database.touch(mode=0o666)
    database.chmod(0o644)
    store = LocalKnowledgeStore(database)
    with pytest.raises(LocalKnowledgeError, match="private regular file") as raised:
        store.list_documents()
    assert raised.value.status == 503
