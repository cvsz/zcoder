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

@pytest.mark.skipif(os.name != "posix", reason="POSIX file permissions only")
def test_set_creates_owner_only_config(isolated_config):
    Config().set("api_key", "sk-ant-test-value")
    assert stat.S_IMODE(isolated_config.stat().st_mode) == 0o600


@pytest.mark.skipif(os.name != "posix", reason="POSIX file permissions only")
def test_set_replaces_permissive_config_with_private_file(isolated_config):
    isolated_config.write_text('{"api_key": "old"}')
    isolated_config.chmod(0o644)

    cfg = Config()
    cfg.set("api_key", "new")

    assert stat.S_IMODE(isolated_config.stat().st_mode) == 0o600
    assert json.loads(isolated_config.read_text()) == {"api_key": "new"}


def test_failed_replace_keeps_previous_config_and_memory(isolated_config, monkeypatch):
    cfg = Config()
    cfg.set("api_key", "old")
    original = isolated_config.read_bytes()

    with monkeypatch.context() as patch:
        def fail_replace(*_args):
            raise OSError("simulated replace failure")

        patch.setattr("zcoder.config.settings.os.replace", fail_replace)
        with pytest.raises(OSError, match="simulated replace failure"):
            cfg.set("api_key", "new")

    assert isolated_config.read_bytes() == original
    assert cfg.get("api_key") == "old"
    assert list(isolated_config.parent.glob(".zcoder-config-*")) == []


def test_failed_serialization_keeps_previous_config_and_memory(isolated_config):
    cfg = Config()
    cfg.set("model", "existing")
    original = isolated_config.read_bytes()

    with pytest.raises(TypeError):
        cfg.set("invalid", object())

    assert isolated_config.read_bytes() == original
    assert cfg.all() == {"model": "existing"}
    assert list(isolated_config.parent.glob(".zcoder-config-*")) == []
