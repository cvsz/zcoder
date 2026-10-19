"""tests/test_config.py"""

import json
import os
import stat

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
