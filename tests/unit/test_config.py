"""tests/test_config.py"""

import json
import os
import stat

import pytest

from zcoder.config.settings import Config


def test_get_default_when_missing():
    cfg = Config()
    assert cfg.get("nonexistent", "fallback") == "fallback"


def test_set_and_get_roundtrip(isolated_config):
    cfg = Config()
    cfg.set("api_key", "sk-ant-test-value")
    assert cfg.get("api_key") == "sk-ant-test-value"


def test_set_persists_to_disk(isolated_config):
    cfg = Config()
    cfg.set("model", "claude-sonnet-5")
    on_disk = json.loads(isolated_config.read_text())
    assert on_disk["model"] == "claude-sonnet-5"


def test_new_instance_reads_persisted_value(isolated_config):
    Config().set("model", "claude-opus-4-8")
    fresh = Config()
    assert fresh.get("model") == "claude-opus-4-8"


def test_all_returns_copy_not_reference(isolated_config):
    cfg = Config()
    cfg.set("k", "v")
    snapshot = cfg.all()
    snapshot["k"] = "mutated"
    assert cfg.get("k") == "v"


def test_corrupt_config_file_does_not_crash(isolated_config):
    isolated_config.write_text("{not valid json")
    cfg = Config()
    assert cfg.all() == {}


def test_set_writes_config_with_owner_only_permissions(isolated_config):
    """The config file can carry provider API keys; it must never be
    group/world readable, whatever the process umask was."""
    old_umask = os.umask(0o027)
    try:
        cfg = Config()
        cfg.set("api_key", "sk-ant-test-value")
    finally:
        os.umask(old_umask)
    mode = stat.S_IMODE(isolated_config.stat().st_mode)
    assert mode == 0o600, f"expected 0o600 config permissions, got {oct(mode)}"


def test_set_persists_atomically_without_temp_artifacts(isolated_config):
    cfg = Config()
    cfg.set("model", "claude-opus-4-8")
    directory = isolated_config.parent
    leftovers = [p.name for p in directory.iterdir() if p.name.startswith(".zcoder-config.")]
    assert leftovers == [isolated_config.name], f"temp artifacts left behind: {leftovers}"


@pytest.mark.skipif(os.name != "posix", reason="POSIX file permissions only")
def test_set_replaces_permissive_config_with_private_file(isolated_config):
    """A legacy config written before hardening may be group/world readable;
    any subsequent write must leave it owner-only."""
    isolated_config.write_text(json.dumps({"api_key": "legacy"}))
    isolated_config.chmod(0o644)
    cfg = Config()
    cfg.set("api_key", "new")
    assert stat.S_IMODE(isolated_config.stat().st_mode) == 0o600
    assert json.loads(isolated_config.read_text()) == {"api_key": "new"}


def test_failed_replace_keeps_previous_config_and_memory(isolated_config, monkeypatch):
    """If the final rename fails, both disk and in-memory state keep the
    previous values and no temp artifact is left behind."""
    cfg = Config()
    cfg.set("api_key", "old")
    original = isolated_config.read_bytes()

    def failing_replace(src, dst):
        raise OSError("simulated rename failure")

    monkeypatch.setattr(os, "replace", failing_replace)
    with pytest.raises(OSError):
        cfg.set("api_key", "new")

    assert isolated_config.read_bytes() == original
    assert cfg.get("api_key") == "old"
    assert list(isolated_config.parent.glob(".zcoder-config-*")) == []


def test_failed_serialization_keeps_previous_config_and_memory(isolated_config, monkeypatch):
    """If serialization fails, nothing is written and no state changes."""
    cfg = Config()
    cfg.set("model", "existing")
    original = isolated_config.read_bytes()

    def failing_dump(obj, stream, **kwargs):
        raise TypeError("simulated serialization failure")

    monkeypatch.setattr(json, "dump", failing_dump)
    with pytest.raises(TypeError):
        cfg.set("model", "changed")

    assert isolated_config.read_bytes() == original
    assert cfg.all() == {"model": "existing"}
    assert list(isolated_config.parent.glob(".zcoder-config-*")) == []
