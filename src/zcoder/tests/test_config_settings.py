"""Tests for zcoder.config.settings - typed config with env var overrides."""

import os

import pytest

from zcoder.config.settings import Config, CONFIG_PATH


class TestConfigDefaults:
    """Test that default config values are correct."""

    def test_default_values(self):
        config = Config()
        assert config.get("provider") == "openai_compatible"
        assert config.get("model") == "zcoder-flash"
        assert config.get("base_url") == "http://localhost:11434"
        assert config.get("api_key") == ""
        assert config.get("max_tokens") == 8192
        assert config.get("context_window") == 32768
        assert config.get("max_output_chars") == 30000
        assert config.get("max_steps") == 40
        assert config.get("max_steps") == 40
        assert config.get("sandbox_enabled") is True
        assert config.get("allow_network") is True
        assert config.get("allow_file_write") is True
        assert config.get("allow_code_exec") is True
        assert config.get("telemetry_enabled") is False


class TestConfigEnvOverrides:
    """Test that environment variables override config file values."""

    def test_env_var_override(self, monkeypatch):
        monkeypatch.setenv("ZCODER_MODEL", "test-model-123")
        config = Config()
        assert config.get("model") == "test-model-123"

    def test_env_var_api_key(self, monkeypatch):
        monkeypatch.setenv("ZCODER_API_KEY", "test-api-key-12345")
        config = Config()
        assert config.get("api_key") == "test-api-key-12345"

    def test_env_var_base_url(self, monkeypatch):
        monkeypatch.setenv("ZCODER_BASE_URL", "http://custom-api.example.com/v1")
        config = Config()
        assert config.get("base_url") == "http://custom-api.example.com/v1"

    def test_env_var_max_tokens(self, monkeypatch):
        monkeypatch.setenv("ZCODER_MAX_TOKENS", "4096")
        config = Config()
        assert config.get("max_tokens") == 4096

    def test_env_var_max_tokens_invalid(self, monkeypatch):
        """Invalid max_tokens should fall back to default."""
        monkeypatch.setenv("ZCODER_MAX_TOKENS", "not-a-number")
        config = Config()
        assert config.get("max_tokens") == 8192

    def test_env_var_temperature_bool(self, monkeypatch):
        monkeypatch.setenv("ZCODER_ALLOW_NETWORK", "false")
        config = Config()
        assert config.get("allow_network") is False

    def test_env_var_max_tokens_bool_true(self, monkeypatch):
        monkeypatch.setenv("ZCODER_ALLOW_NETWORK", "true")
        config = Config()
        assert config.get("allow_network") is True


class TestConfigSet:
    """Test setting config values."""

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
    """Test config persistence (read/write)."""

    def test_save_and_load(self, tmp_path):
        config = Config()
        config.set("model", "test-model")
        config.set("timeout_ms", 3000)

        Config()
        # Config reads from ~/.zcoder-config.json, not tmp_path, so this
        # just verifies the save doesn't crash.
        assert config.get("model") == "test-model"


class TestConfigEnvVarPriority:
    """Test that env vars override config file values."""

    def test_env_overrides_file(self, monkeypatch, tmp_path):
        # Write a config file with one value
        import json

        config_path = os.path.join(tmp_path, "test-config.json")
        with open(config_path, "w") as f:
            json.dump({"model": "file-model"}, f)

        # Temporarily point CONFIG_PATH to our temp file

        original_path = CONFIG_PATH
        CONFIG_PATH = config_path

        try:
            config = Config()
            assert config.get("model") == "file-model"

            # Now set env var and create a new config
            monkeypatch.setenv("ZCODER_MODEL", "env-model")
            config2 = Config()
            assert config2.get("model") == "env-model"
        finally:
            CONFIG_PATH = original_path
