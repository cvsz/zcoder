"""Regression tests for durable local zGPU conversation history."""

from __future__ import annotations

import os

import pytest

from zgpu.integrations.conversations import ConversationError, ConversationStore


def test_conversation_store_persists_messages_and_updates_title(tmp_path):
    path = tmp_path / "data" / "conversations.sqlite3"
    store = ConversationStore(path)
    created = store.create()
    assert created["title"] == "New chat"
    assert created["messages"] == []

    saved = store.append_messages(
        created["id"],
        [
            {"role": "user", "content": "Help me inspect this kernel\nwith bounds checks"},
            {
                "role": "assistant",
                "content": "The kernel needs a bounds check.",
                "citations": [
                    {
                        "number": 1,
                        "title": "Kernel guide",
                        "url": "https://docs.example/kernel",
                        "source": "connected",
                    },
                    {"number": 2, "title": "Local zGPU notes"},
                ],
            },
        ],
        model="zgpu-thai",
    )
    reopened = ConversationStore(path).get(created["id"])
    assert reopened == saved
    assert saved["title"] == "Help me inspect this kernel"
    assert saved["model"] == "zgpu-thai"
    assert saved["messages"][1]["citations"][0]["url"] == "https://docs.example/kernel"
    assert saved["messages"][1]["citations"][0]["source"] == "connected"
    assert saved["messages"][1]["citations"][1] == {"number": 2, "title": "Local zGPU notes", "url": None}
    assert ConversationStore(path).list()[0]["message_count"] == 2
    if os.name == "posix":
        assert path.stat().st_mode & 0o077 == 0


def test_conversation_store_validates_limits_ids_and_citation_urls(tmp_path):
    store = ConversationStore(tmp_path / "conversations.sqlite3")
    created = store.create()
    with pytest.raises(ConversationError):
        store.get("../outside")
    with pytest.raises(ConversationError):
        store.create("x" * 121)
    with pytest.raises(ConversationError):
        store.append_messages(created["id"], [{"role": "tool", "content": "run"}])
    with pytest.raises(ConversationError):
        store.append_messages(created["id"], [{"role": [], "content": "run"}])
    with pytest.raises(ConversationError):
        store.append_messages(created["id"], [{"role": "user", "content": "\ud800"}])
    with pytest.raises(ConversationError):
        store.append_messages(
            created["id"],
            [
                {
                    "role": "assistant",
                    "content": "answer",
                    "citations": [{"number": 1, "title": "unsafe", "url": "javascript:alert(1)"}],
                }
            ],
        )
    with pytest.raises(ConversationError):
        store.list(limit=201)
    with pytest.raises(ConversationError):
        store.append_messages(
            created["id"],
            [
                {
                    "role": "assistant",
                    "content": "answer",
                    "citations": [{"number": 1, "title": "source", "source": "other"}],
                }
            ],
        )


def test_conversation_store_private_mode_and_delete(tmp_path):
    path = tmp_path / "conversations.sqlite3"
    store = ConversationStore(path)
    created = store.create()
    store.append_messages(created["id"], [{"role": "user", "content": "remember this"}])
    assert store.delete(created["id"]) is True
    assert store.delete(created["id"]) is False
    with pytest.raises(ConversationError) as error:
        store.get(created["id"])
    assert error.value.status == 404
    insecure = tmp_path / "insecure.sqlite3"
    insecure.touch(mode=0o644)
    insecure.chmod(0o644)
    with pytest.raises(ConversationError, match="private regular file"):
        ConversationStore(insecure).list()


def test_conversation_store_renames_without_changing_messages(tmp_path):
    store = ConversationStore(tmp_path / "conversations.sqlite3")
    created = store.create()
    store.append_messages(created["id"], [{"role": "user", "content": "Review kernel safety"}])

    renamed = store.rename(created["id"], "  Kernel safety review  ")
    assert renamed["title"] == "Kernel safety review"
    assert renamed["messages"][0]["content"] == "Review kernel safety"

    for title in ("", "  ", "x" * 121):
        with pytest.raises(ConversationError):
            store.rename(created["id"], title)
    with pytest.raises(ConversationError) as error:
        store.rename("0" * 32, "missing")
    assert error.value.status == 404


def test_conversation_store_searches_titles_and_messages_with_bounded_literal_query(tmp_path):
    store = ConversationStore(tmp_path / "conversations.sqlite3")
    titled = store.create("zGPU simulator overview")
    store.append_messages(titled["id"], [{"role": "user", "content": "Review dynamic warp scheduling"}])
    other = store.create("Hardware notes")

    assert [item["id"] for item in store.list(search="SIMULATOR")] == [titled["id"]]
    assert [item["id"] for item in store.list(search="dynamic warp")] == [titled["id"]]
    assert [item["id"] for item in store.list(search="Hardware")] == [other["id"]]
    assert store.list(search="%_") == []
    with pytest.raises(ConversationError):
        store.list(search="x" * 257)
    with pytest.raises(ConversationError):
        store.list(search=None)


def test_workspace_projects_organize_conversations_and_detach_on_delete(tmp_path):
    store = ConversationStore(tmp_path / "conversations.sqlite3")
    project = store.create_project("GPU kernels")
    conversation = store.create("Kernel review", "zgpu-code", project["id"])
    store.append_messages(conversation["id"], [{"role": "user", "content": "Check bounds"}])

    assert store.get(conversation["id"])["project_id"] == project["id"]
    assert store.list(project_id=project["id"])[0]["id"] == conversation["id"]
    assert store.list_projects()[0]["conversation_count"] == 1
    with pytest.raises(ConversationError) as duplicate:
        store.create_project("gpu KERNELS")
    assert duplicate.value.status == 409

    renamed = store.rename_project(project["id"], "zGPU kernels")
    assert renamed["name"] == "zGPU kernels"
    assert store.delete_project(project["id"]) is True
    assert store.delete_project(project["id"]) is False
    assert store.get(conversation["id"])["project_id"] is None
    assert store.list(project_id=None)[0]["id"] == conversation["id"]


def test_conversation_database_migrates_existing_records_to_project_schema(tmp_path):
    import sqlite3
    import uuid

    path = tmp_path / "existing.sqlite3"
    conversation_id = uuid.uuid4().hex
    with sqlite3.connect(path) as connection:
        connection.executescript("""CREATE TABLE conversations (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, model TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE conversation_messages (
                id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
                sequence INTEGER NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL,
                citations TEXT NOT NULL, created_at TEXT NOT NULL,
                UNIQUE(conversation_id, sequence)
            );""")
        connection.execute(
            "INSERT INTO conversations VALUES (?, ?, ?, ?, ?)",
            (
                conversation_id,
                "Existing chat",
                "zgpu-small",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )
    path.chmod(0o600)

    conversation = ConversationStore(path).get(conversation_id)
    assert conversation["title"] == "Existing chat"
    assert conversation["project_id"] is None


def test_conversation_store_enforces_total_text_quota(tmp_path, monkeypatch):
    store = ConversationStore(tmp_path / "conversations.sqlite3")
    created = store.create()
    monkeypatch.setattr(store, "MAX_TOTAL_CONTENT_BYTES", 4)
    with pytest.raises(ConversationError) as error:
        store.append_messages(created["id"], [{"role": "user", "content": "12345"}])
    assert error.value.status == 413
    assert store.get(created["id"])["messages"] == []
