"""tests/test_production_config.py — Tests for production configuration schema."""

import json

from production_config import (
    ProductionConfig,
    _redact_dict,
    load_config,
    show_effective_config,
    validate_config,
)


class TestRedaction:
    def test_redacts_api_key_fields(self):
        d = {"api_key": "sk-secret-value", "name": "test"}
        result = _redact_dict(d)
        assert result["api_key"] == "[REDACTED]"
        assert result["name"] == "test"

    def test_redacts_password_fields(self):
        d = {"database_password": "supersecret"}
        result = _redact_dict(d)
        assert result["database_password"] == "[REDACTED]"

    def test_does_not_redact_empty_strings(self):
        d = {"api_key": "", "name": "test"}
        result = _redact_dict(d)
        # Empty string — nothing to redact
        assert result["api_key"] == ""

    def test_redacts_nested_secrets(self):
        d = {"auth": {"oidc_client_id": "client-123", "webhook_secret": "wh-secret"}}
        result = _redact_dict(d)
        assert result["auth"]["oidc_client_id"] == "client-123"
        assert result["auth"]["webhook_secret"] == "[REDACTED]"


class TestLoadConfig:
    def test_default_profile_is_local(self):
        cfg = load_config()
        assert cfg.profile == "local"

    def test_env_var_overrides_profile(self, monkeypatch):
        monkeypatch.setenv("ZCODER_PROFILE", "development")
        cfg = load_config()
        assert cfg.profile == "development"

    def test_database_url_sets_postgres_mode(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/testdb")
        cfg = load_config()
        assert cfg.database.mode == "postgres"
        assert "postgresql://" in cfg.database.url

    def test_load_config_from_file(self, tmp_path):
        config_data = {
            "profile": "development",
            "database": {"pool_size": 10, "mode": "postgres"},
        }
        config_file = tmp_path / "zcoder.json"
        config_file.write_text(json.dumps(config_data))
        cfg = load_config(str(config_file))
        assert cfg.profile == "development"
        assert cfg.database.pool_size == 10

    def test_unknown_config_key_does_not_crash(self, tmp_path, capsys):
        config_data = {"unknown_top_level_section": {"foo": "bar"}}
        config_file = tmp_path / "zcoder.json"
        config_file.write_text(json.dumps(config_data))
        cfg = load_config(str(config_file))
        out, _ = capsys.readouterr()
        assert "unknown" in out.lower() or cfg is not None  # Should warn, not crash

    def test_telemetry_enabled_by_env(self, monkeypatch):
        monkeypatch.setenv("ZCODER_TELEMETRY_ENABLED", "1")
        cfg = load_config()
        assert cfg.telemetry.enabled is True

    def test_auth_enabled_by_env(self, monkeypatch):
        monkeypatch.setenv("ZCODER_AUTH_ENABLED", "true")
        monkeypatch.setenv("ZCODER_OIDC_ISSUER", "https://issuer.example.com")
        monkeypatch.setenv("ZCODER_OIDC_AUDIENCE", "zcoder-prod")
        cfg = load_config()
        assert cfg.auth.enabled is True
        assert cfg.auth.oidc_issuer == "https://issuer.example.com"
        assert cfg.auth.oidc_audience == "zcoder-prod"


class TestValidateConfig:
    def test_local_profile_no_errors(self):
        cfg = ProductionConfig(profile="local")
        results = validate_config(cfg)
        errors = [r for r in results if r.startswith("ERROR")]
        assert not errors

    def test_production_without_postgres_is_error(self):
        cfg = ProductionConfig(profile="production")
        cfg.auth.enabled = True
        cfg.auth.oidc_issuer = "https://issuer.example.com"
        cfg.auth.oidc_audience = "zcoder"
        results = validate_config(cfg)
        errors = [r for r in results if "postgres" in r.lower() or "database" in r.lower()]
        assert errors

    def test_production_without_auth_is_error(self):
        cfg = ProductionConfig(profile="production")
        cfg.database.mode = "postgres"
        cfg.database.url = "postgresql://localhost/zcoder"
        cfg.auth.enabled = False
        results = validate_config(cfg)
        errors = [r for r in results if "auth" in r.lower()]
        assert errors

    def test_production_with_debug_is_warning(self):
        cfg = ProductionConfig(profile="production")
        cfg.debug = True
        cfg.database.mode = "postgres"
        cfg.database.url = "postgresql://localhost/zcoder"
        cfg.auth.enabled = True
        cfg.auth.oidc_issuer = "https://issuer.example.com"
        cfg.auth.oidc_audience = "zcoder"
        results = validate_config(cfg)
        warnings = [r for r in results if "warn" in r.lower() and "debug" in r.lower()]
        assert warnings


class TestShowEffectiveConfig:
    def test_output_is_valid_json(self):
        cfg = ProductionConfig()
        output = show_effective_config(cfg)
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_secrets_are_redacted_in_output(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:supersecret@localhost/db")
        cfg = load_config()
        output = show_effective_config(cfg)
        assert "supersecret" not in output

    def test_profile_present_in_output(self):
        cfg = ProductionConfig(profile="development")
        output = show_effective_config(cfg)
        parsed = json.loads(output)
        assert parsed["profile"] == "development"
