import os
import sqlite3
import stat

import pytest

from zgpu.integrations.notes import WorkspaceNotes, WorkspaceNotesError


def test_workspace_notes_crud_search_and_private_database(tmp_path):
    store = WorkspaceNotes(tmp_path / "private" / "notes.sqlite3")
    created = store.create(
        "zISA release checks", "Always verify the 32-bit zISA encoding and run the simulator."
    )

    assert created["title"] == "zISA release checks"
    assert store.list()[0]["id"] == created["id"]
    assert store.get(created["id"])["content"].startswith("Always verify")
    matches = store.search("zISA encoding")
    assert len(matches) == 1
    assert matches[0]["id"] == created["id"]
    assert "32-bit" in matches[0]["excerpt"]
    assert store.update(
        created["id"], "Release checklist", "Review the exact PR head and required CI checks."
    )["title"] == ("Release checklist")
    assert store.delete(created["id"])
    assert store.list() == []
    if os.name == "posix":
        assert stat.S_IMODE(store.database_path.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    ("title", "content"),
    [
        ("", "content"),
        ("x" * 121, "content"),
        ("valid", "  \n"),
        ("valid", "x" * 20_001),
        ("bad\ud800", "content"),
    ],
)
def test_workspace_notes_reject_invalid_content(tmp_path, title, content):
    with pytest.raises(WorkspaceNotesError):
        WorkspaceNotes(tmp_path / "notes.sqlite3").create(title, content)


def test_workspace_notes_rejects_invalid_ids_searches_and_private_modes(tmp_path):
    path = tmp_path / "notes.sqlite3"
    store = WorkspaceNotes(path)
    store.create("Architecture", "The software simulator uses 32-thread warps.")
    with pytest.raises(WorkspaceNotesError):
        store.get("../notes")
    with pytest.raises(WorkspaceNotesError):
        store.search(" ")
    with pytest.raises(WorkspaceNotesError):
        store.create("Invalid scope", "Note content", False)
    if os.name == "posix":
        path.chmod(0o644)
        with pytest.raises(WorkspaceNotesError, match="private"):
            store.list()


def test_project_scoped_search_includes_general_notes_and_detaches_on_deletion(tmp_path):
    store = WorkspaceNotes(tmp_path / "notes.sqlite3")
    project_id = "a" * 32
    general = store.create("Shared rules", "Preserve zISA encoding compatibility.")
    project = store.create("Kernel task", "Review the zISA kernel launch contract.", project_id)

    assert [item["id"] for item in store.search("zISA")] == [general["id"]]
    scoped = store.search("zISA", project_id=project_id)
    assert {item["id"] for item in scoped} == {general["id"], project["id"]}
    assert store.detach_project(project_id) == 1
    assert store.get(project["id"])["project_id"] is None


def test_workspace_notes_migrates_legacy_table_without_losing_notes(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    note_id = "b" * 32
    with sqlite3.connect(path) as connection:
        connection.execute("""CREATE TABLE workspace_notes (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, content TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )""")
        connection.execute(
            "INSERT INTO workspace_notes VALUES (?, ?, ?, ?, ?)",
            (
                note_id,
                "Legacy",
                "Existing user note",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )
    if os.name == "posix":
        path.chmod(0o600)

    store = WorkspaceNotes(path)
    migrated = store.get(note_id)

    assert migrated["content"] == "Existing user note"
    assert migrated["project_id"] is None
