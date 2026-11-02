"""Regression tests for the local zGPU prompt library."""

from __future__ import annotations

import os

import pytest

from zgpu.integrations.prompts import PromptLibrary, PromptLibraryError


def test_prompt_library_crud_persistence_and_ordering(tmp_path):
    path = tmp_path / "data" / "prompts.sqlite3"
    library = PromptLibrary(path)
    first = library.create("Code review", "Review this change:\n\n{{input}}")
    assert first["content"].endswith("{{input}}")
    assert PromptLibrary(path).get(first["id"]) == first
    assert library.list()[0]["id"] == first["id"]

    updated = library.update(first["id"], "Security review", "Check trust boundaries and input validation.")
    assert updated["title"] == "Security review"
    assert updated["content"].startswith("Check trust")
    assert library.delete(first["id"]) is True
    assert library.delete(first["id"]) is False
    if os.name == "posix":
        assert path.stat().st_mode & 0o077 == 0


def test_prompt_library_rejects_invalid_content_ids_and_limits(tmp_path, monkeypatch):
    library = PromptLibrary(tmp_path / "prompts.sqlite3")
    with pytest.raises(PromptLibraryError):
        library.create("", "body")
    with pytest.raises(PromptLibraryError):
        library.create("title", "\ud800")
    with pytest.raises(PromptLibraryError):
        library.get("../escape")

    prompt = library.create("Title", "Body")
    with pytest.raises(PromptLibraryError) as missing:
        library.update("f" * 32, "Title", "Body")
    assert missing.value.status == 404

    monkeypatch.setattr(library, "MAX_TOTAL_CONTENT_BYTES", 3)
    with pytest.raises(PromptLibraryError) as quota:
        library.create("Large", "four")
    assert quota.value.status == 413
    assert library.get(prompt["id"])["content"] == "Body"


def test_prompt_library_refuses_insecure_existing_database(tmp_path):
    path = tmp_path / "prompts.sqlite3"
    path.touch(mode=0o644)
    path.chmod(0o644)
    with pytest.raises(PromptLibraryError, match="private regular file"):
        PromptLibrary(path).list()
