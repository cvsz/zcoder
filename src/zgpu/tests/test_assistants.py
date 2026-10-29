"""Regression coverage for private local assistant profiles."""

from __future__ import annotations

import pytest

from zgpu.integrations.assistants import BUILTIN_ASSISTANTS, AssistantProfileError, AssistantProfiles


def test_builtin_profiles_are_available_and_immutable(tmp_path):
    profiles = AssistantProfiles(tmp_path / "assistants.sqlite3")
    assert profiles.list()[0]["id"] == BUILTIN_ASSISTANTS[0]["id"]
    assert profiles.get("builtin_precise")["system_prompt"]
    with pytest.raises(AssistantProfileError):
        profiles.update("builtin_precise", "Changed", "", "prompt")
    with pytest.raises(AssistantProfileError):
        profiles.delete("builtin_precise")


def test_custom_profiles_persist_update_and_delete(tmp_path):
    path = tmp_path / "private" / "assistants.sqlite3"
    profiles = AssistantProfiles(path)
    created = profiles.create("  Kernel reviewer  ", "Review zISA kernels", "Check bounds and alignment.")
    assert created["name"] == "Kernel reviewer"
    assert created["builtin"] is False
    assert profiles.get(created["id"])["system_prompt"] == "Check bounds and alignment."
    updated = profiles.update(created["id"], "Reviewer", "Review safely", "Check invalid operands.")
    assert updated["system_prompt"] == "Check invalid operands."
    assert any(item["id"] == created["id"] for item in profiles.list())
    assert profiles.delete(created["id"])
    with pytest.raises(AssistantProfileError) as error:
        profiles.get(created["id"])
    assert error.value.status == 404
    if path.exists():
        assert path.stat().st_mode & 0o077 == 0


@pytest.mark.parametrize(
    ("name", "description", "system_prompt"),
    [("", "", "prompt"), ("name", "x" * 241, "prompt"), ("name", "", " "), ("name", "", "x" * 8001)],
)
def test_custom_profile_fields_are_bounded(name, description, system_prompt, tmp_path):
    with pytest.raises(AssistantProfileError):
        AssistantProfiles(tmp_path / "assistants.sqlite3").create(name, description, system_prompt)
