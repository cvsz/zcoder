"""production_config.py — Formalized production configuration schema and validation for ZCoder.

Provides:
  • Typed, validated configuration for all subsystems
  • Config precedence: defaults → config file → environment → secret provider → CLI
  • Deployment profiles: local, development, production
  • Config dump with secret redaction
  • Config validation and unknown-key warnings
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Sub-configuration sections
# ---------------------------------------------------------------------------


@dataclass
class DatabaseConfig:
    """PostgreSQL / SQLite database settings."""

    url: str = ""  # e.g. postgresql://user:pass@host/db
    sqlite_path: str = ""  # local-mode fallback
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: float = 30.0
    pool_recycle: int = 1800
    connect_timeout: int = 10
    statement_timeout_ms: int = 30000
    mode: str = "sqlite"  # sqlite | postgres


@dataclass
class AuthConfig:
    """OIDC / authentication settings."""

    enabled: bool = False
    oidc_issuer: str = ""
    oidc_audience: str = ""
    oidc_jwks_uri: str = ""
    oidc_client_id: str = ""
    # Role mapping claim name in JWT
    role_claim: str = "zcoder_role"
    # Default role for authenticated users without explicit mapping
    default_role: str = "VIEWER"
    # Session
    session_max_age_seconds: int = 3600
    session_cookie_secure: bool = True
    session_cookie_same_site: str = "strict"
    csrf_protection: bool = True


@dataclass
class GitHubAppConfig:
    """GitHub App credentials."""

    app_id: str = ""
    private_key_path: str = ""  # Path to PEM file; NOT inline key
    private_key_env: str = ""  # Env var name containing PEM content
    webhook_secret_env: str = "GITHUB_WEBHOOK_SECRET"
    installation_id: int | None = None


@dataclass
class AnthropicConfig:
    """Anthropic API credentials and limits."""

    api_key_env: str = "ANTHROPIC_API_KEY"
    default_model: str = "claude-sonnet-5"
    max_tokens: int = 8192
    timeout_seconds: float = 600.0
    max_retries: int = 3
    retry_backoff_base: float = 2.0


@dataclass
class WorkerConfig:
    """Worker pool settings."""

    concurrency: int = 2
    lease_duration_seconds: float = 120.0
    heartbeat_interval_seconds: float = 30.0
    shutdown_timeout_seconds: float = 60.0
    max_job_attempts: int = 3
    pool_type: str = "standard"  # standard | sandbox | trusted | high-isolation


@dataclass
class TelemetryConfig:
    """OpenTelemetry / observability settings."""

    enabled: bool = False
    otel_endpoint: str = ""
    service_name: str = "zcoder"
    service_version: str = ""
    metrics_port: int = 9090
    metrics_path: str = "/metrics"
    log_format: str = "json"  # json | text
    log_level: str = "INFO"
    trace_sampling_ratio: float = 0.1


@dataclass
class BackupConfig:
    """Backup and PITR settings."""

    enabled: bool = False
    strategy: str = "pg_dump"  # pg_dump | wal_archive | pitr
    schedule_cron: str = "0 2 * * *"  # daily at 02:00 UTC
    retention_days_daily: int = 7
    retention_days_weekly: int = 30
    destination: str = ""  # s3://bucket/prefix or /local/path
    encryption_key_env: str = "BACKUP_ENCRYPTION_KEY"
    wal_archive_command: str = ""
    # Freshness alert thresholds
    max_backup_age_hours: float = 26.0
    max_restore_drill_age_days: int = 30


@dataclass
class SecurityConfig:
    """Security hardening settings."""

    rate_limit_enabled: bool = True
    rate_limit_login_per_minute: int = 10
    rate_limit_webhook_per_minute: int = 100
    rate_limit_job_submit_per_minute: int = 30
    max_webhook_payload_bytes: int = 10 * 1024 * 1024  # 10 MB
    max_api_payload_bytes: int = 4 * 1024 * 1024  # 4 MB
    trusted_proxy_cidrs: list[str] = field(default_factory=list)
    content_security_policy: str = "default-src 'self'"
    referrer_policy: str = "strict-origin-when-cross-origin"
    frame_options: str = "DENY"


@dataclass
class ProductionConfig:
    """Top-level ZCoder production configuration."""

    # Deployment profile (local | development | production)
    profile: str = "local"

    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    github: GitHubAppConfig = field(default_factory=GitHubAppConfig)
    anthropic: AnthropicConfig = field(default_factory=AnthropicConfig)
    worker: WorkerConfig = field(default_factory=WorkerConfig)
    telemetry: TelemetryConfig = field(default_factory=TelemetryConfig)
    backup: BackupConfig = field(default_factory=BackupConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)

    # General
    debug: bool = False
    log_level: str = "INFO"


# ---------------------------------------------------------------------------
# Secret redaction helpers
# ---------------------------------------------------------------------------

_SECRET_FIELDS = frozenset(
    {
        "api_key",
        "private_key",
        "webhook_secret",
        "password",
        "encryption_key",
        "token",
        "secret",
    }
)


def _redact_value(key: str, value: Any) -> Any:
    """Return '[REDACTED]' if the key looks like a secret, else return value unchanged.
    Also scrubs passwords embedded in database URLs.
    """
    key_lower = key.lower()
    for s in _SECRET_FIELDS:
        if s in key_lower:
            if isinstance(value, str) and value:
                return "[REDACTED]"
    # Scrub embedded password in database/connection URLs
    if (
        isinstance(value, str)
        and "://" in value
        and "@" in value
        and key_lower in ("url", "dsn", "database_url", "connection_string")
    ):
        import re

        return re.sub(r"(://[^:@]+:)[^@]+(@)", r"\1[REDACTED]\2", value)
    return value


def _redact_dict(d: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, dict):
            result[k] = _redact_dict(v)
        elif isinstance(v, list):
            result[k] = [_redact_dict(i) if isinstance(i, dict) else i for i in v]
        else:
            result[k] = _redact_value(k, v)
    return result


# ---------------------------------------------------------------------------
# Environment resolution helpers
# ---------------------------------------------------------------------------


def _resolve_from_env(cfg: ProductionConfig) -> ProductionConfig:
    """Override config with values from environment variables."""
    profile = os.environ.get("ZCODER_PROFILE", cfg.profile)
    cfg.profile = profile

    db_url = os.environ.get("DATABASE_URL", "")
    if db_url:
        cfg.database.url = db_url
        cfg.database.mode = "postgres"
    elif os.environ.get("ZCODER_DB_PATH", ""):
        cfg.database.sqlite_path = os.environ["ZCODER_DB_PATH"]
        cfg.database.mode = "sqlite"

    if os.environ.get("ZCODER_LOG_LEVEL"):
        cfg.log_level = os.environ["ZCODER_LOG_LEVEL"]
    if os.environ.get("ZCODER_LOG_FORMAT"):
        cfg.telemetry.log_format = os.environ["ZCODER_LOG_FORMAT"]

    if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        cfg.telemetry.otel_endpoint = os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"]
        cfg.telemetry.enabled = True

    if os.environ.get("ZCODER_TELEMETRY_ENABLED", "").lower() in ("1", "true"):
        cfg.telemetry.enabled = True

    if os.environ.get("ZCODER_AUTH_ENABLED", "").lower() in ("1", "true"):
        cfg.auth.enabled = True
        cfg.auth.oidc_issuer = os.environ.get("ZCODER_OIDC_ISSUER", cfg.auth.oidc_issuer)
        cfg.auth.oidc_audience = os.environ.get("ZCODER_OIDC_AUDIENCE", cfg.auth.oidc_audience)
        cfg.auth.oidc_jwks_uri = os.environ.get("ZCODER_OIDC_JWKS_URI", cfg.auth.oidc_jwks_uri)

    if os.environ.get("GITHUB_APP_ID"):
        cfg.github.app_id = os.environ["GITHUB_APP_ID"]

    if os.environ.get("WORKER_CONCURRENCY"):
        try:
            cfg.worker.concurrency = int(os.environ["WORKER_CONCURRENCY"])
        except ValueError:
            pass

    if os.environ.get("ZCODER_BACKUP_ENABLED", "").lower() in ("1", "true"):
        cfg.backup.enabled = True
        cfg.backup.destination = os.environ.get("ZCODER_BACKUP_DEST", cfg.backup.destination)

    return cfg


# ---------------------------------------------------------------------------
# Profile-level validation
# ---------------------------------------------------------------------------


class ConfigValidationError(Exception):
    """Raised when configuration is invalid for the selected profile."""


def validate_config(cfg: ProductionConfig) -> list[str]:
    """Validate configuration for the selected profile. Returns list of warnings/errors."""
    errors: list[str] = []
    warnings: list[str] = []

    if cfg.profile == "production":
        if cfg.debug:
            warnings.append("WARN: debug=true in production profile")
        if cfg.database.mode != "postgres":
            errors.append(
                "ERROR: production profile requires database.mode=postgres (DATABASE_URL must be set)"
            )
        if not cfg.auth.enabled:
            errors.append("ERROR: production profile requires auth.enabled=true")
        if not cfg.auth.oidc_issuer:
            errors.append("ERROR: production profile requires auth.oidc_issuer")
        if not cfg.auth.oidc_audience:
            errors.append("ERROR: production profile requires auth.oidc_audience")
        if cfg.log_level == "DEBUG":
            warnings.append("WARN: LOG_LEVEL=DEBUG in production — may expose sensitive data")
        if not cfg.telemetry.enabled:
            warnings.append("WARN: telemetry not enabled in production profile")
        if not cfg.backup.enabled:
            warnings.append("WARN: backup not enabled in production profile")

    elif cfg.profile == "development":
        if cfg.database.mode == "sqlite":
            warnings.append("INFO: development profile using SQLite — not suitable for multi-process testing")

    elif cfg.profile == "local":
        pass  # SQLite + local mode is expected

    return errors + warnings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG: ProductionConfig | None = None


def load_config(config_file: str | None = None) -> ProductionConfig:
    """Load configuration with full precedence chain."""
    cfg = ProductionConfig()  # start with defaults

    if config_file and Path(config_file).exists():
        try:
            with open(config_file) as f:
                data = json.load(f)
            # Shallow merge (nested sections)
            for section, values in data.items():
                if hasattr(cfg, section) and isinstance(values, dict):
                    section_obj = getattr(cfg, section)
                    for k, v in values.items():
                        if hasattr(section_obj, k):
                            setattr(section_obj, k, v)
                        else:
                            print(f"WARN: unknown config key '{section}.{k}'")
                elif hasattr(cfg, section):
                    setattr(cfg, section, values)
                else:
                    print(f"WARN: unknown top-level config section '{section}'")
        except Exception as e:
            print(f"WARN: failed to load config file {config_file}: {e}")

    cfg = _resolve_from_env(cfg)
    validation = validate_config(cfg)
    errors = [issue for issue in validation if issue.startswith("ERROR:")]
    if errors:
        raise ConfigValidationError("Configuration validation failed: " + "; ".join(errors))
    return cfg


def get_config() -> ProductionConfig:
    """Return cached global config (call load_config first)."""
    global _DEFAULT_CONFIG
    if _DEFAULT_CONFIG is None:
        _DEFAULT_CONFIG = load_config(os.environ.get("ZCODER_CONFIG_FILE"))
    return _DEFAULT_CONFIG


def show_effective_config(cfg: ProductionConfig | None = None) -> str:
    """Return the effective configuration as a redacted JSON string."""
    if cfg is None:
        cfg = get_config()
    raw = asdict(cfg)
    redacted = _redact_dict(raw)
    return json.dumps(redacted, indent=2)
