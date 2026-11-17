"""tests/test_config.py"""

import json
import os
import stat

import pytest

from zcoder.config.settings import DEFAULT_CONFIG, Config
from zcoder.core.exceptions import ConfigError


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
    cfg.set("model", "v")
    snapshot = cfg.all()
    snapshot["model"] = "mutated"
    assert cfg.get("model") == "v"


def test_unknown_key_is_rejected(isolated_config):
    with pytest.raises(ConfigError):
        Config().set("k", "v")


def test_corrupt_config_file_does_not_crash(isolated_config, monkeypatch):
    for name in list(os.environ):
        if name.startswith("ZCODER_"):
            monkeypatch.delenv(name)
    isolated_config.write_text("{not valid json")
    cfg = Config()
    assert cfg.all() == DEFAULT_CONFIG


def test_env_secret_is_never_persisted(isolated_config, monkeypatch):
    """ZCODER_API_KEY comes from the environment; writing another key must not copy it to disk."""
    monkeypatch.setenv("ZCODER_API_KEY", "sk-from-env-only")
    cfg = Config()
    assert cfg.get("api_key") == "sk-from-env-only"
    cfg.set("model", "zcoder-pro")
    assert json.loads(isolated_config.read_text()) == {"model": "zcoder-pro"}
    assert cfg.get("api_key") == "sk-from-env-only"


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
    assert [p for p in isolated_config.parent.glob(".zcoder-config.*") if p != isolated_config] == []


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
    assert cfg.get("model") == "existing"
    assert [p for p in isolated_config.parent.glob(".zcoder-config.*") if p != isolated_config] == []
