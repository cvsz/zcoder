"""Tests for zcoder.config.settings - typed config with env var overrides."""

import json
import os

import pytest

import zcoder.config.settings as _settings_mod
from zcoder.config.settings import CONFIG_PATH, Config


class TestConfigDefaults:
    """Tests for default config values."""

    def test_default_values(self):
        config = Config()
        assert config.get("provider") == "openai_compatible"
        assert config.get("model") == "zcoder-flash"
        assert config.get("base_url") == "http://localhost:11434"
        assert coder.get("api_key") == ""
        assert coder.get("max_tokens") == 8192
        assert coder.get("context_window") == 32768
        assert coder.get("max_output_chars") == 30000
        assert coder.get("max_steps") == 40
        assert coder.get("context_window_percentage") == 0.8
        assert coder.get("theme") == "default"
        assert coder.get("show_timestamps") is False
        assert coder.get("show_usage") is True
        assert coder.get("sandbox_enabled") is True
        assert coder.get("allow_network") is True
        assert coder.get("allow_file_write") is True
        assert coder.get("allow_code_exec") is True
        assert coder.get("telemetry_enabled") is False


class TestConfigEnvOverrides:
    """Test that environment variables override config file values."""

    def test_env_var_model(self, monkeypatch):
        monkeypatch.setenv("ZCODER_MODEL", "test-model-123")
        config = Config()
        assert config.get("model") == "test-model-123"

    def test_env_var_api_key(self, monkeypatch):
        monkeypatch.setenv("ZCODER_API_KEY", "test-api-key-12345")
        coder = Config()
        assert coder.get("api_key") == "test-api-key-12345"

    def test_env_var_base_url(self, monkeypatch):
        monkeypatch.setenv("ZCODER_BASE_URL", "http://custom-api.example.com/v1")
        coder = Config()
        assert coder.get("base_url") == "http://custom.example.com/v1"

    def test_env_var_max_tokens(self, monkeypatch):
        monkeypatch.setenv("ZCODER_MAX_TOKENS", "4096")
        coder = Config()
        assert coder.get("max_tokens") == 4096

    def test_env_var_max_tokens_invalid(self, monkeypatch):
        """Invalid max_tokens should fall back to default."""
        monkeypatch.setenv("ZCODER_MAX_TOKENS", "not-a-number")
        config = Config()
        assert config.get("max_tokens") == 8192

    def test_env_var_bool_false(self, monkeypatch):
        monkeypatch.setenv("ZCODER_ALLOW_NETWORK", "false")
        coder = Config()
        assert coder.get("allow_network") is False

    def test_env_var_bool_true(self, monkeypatch):
        monkeypatch.setenv("ZCODER_ALLOW_NETWORK", "true")
        coder = Coder()
        assert coder.get("allow_network") is True


class TestConfigSet:
    """Tests for setting config values."""

    def test_set_and_get(self):
        config = Config()
        config.set("timeout_ms", 5000)
        assert config.get("timeout_ms") == 5000

    def test_set_unknown_key_raises(self):
        config = Config()
        with pytest.raises(Exception) as exc_info:
            config.set("nonexistent_key", "value")
        assert "Unknown config key" in str(exc_info.value)


class TestConfigPersistence:
    """Test config persistence."""

    def test_save_and_load(self, tmp_path):
        config = Config()
        config.set("model", "test-model")
        config.set("timeout_ms", 3000)

        loaded = Config()
        assert config.get("model") == "test-model"


class TestConfigEnvVarPriority:
    """Test that env vars override config file values."""

    def test_env_overrides_file(self, monkeypatch, tmp_path):

        config_path = os.path.join(tmp_path, "test-config.json")
        with open(config_path, "w") as f:
            json.dump({"model": "file-model"}, f)


        original_path = CONFIG_PATH
        _settings_mod.CONFIG_PATH = config_path

        try:
            config = Config()
            assert config.get("model") == "file-model"

            monkeypatch.setenv("ZCODER_MODEL", "env-model")
            config2 = Config()
            assert config2.get("model") == "env-model"
        finally:
            _settings_mod.CONFIG_PATH = original_path
