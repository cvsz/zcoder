"""zcoder.config.settings.py — Configuration management"""

import json
import os
import tempfile
from typing import Any, TypedDict, cast

from zcoder.core.exceptions import ConfigError

CONFIG_PATH = os.path.expanduser("~/.zcoder-config.json")
LEGACY_CONFIG_PATH = os.path.expanduser("~/.ai-coder-config.json")


class ConfigFields(TypedDict, total=False):
    """Typed config fields for zcoder configuration.

    All fields are optional; missing fields fall back to defaults.
    Credential-related fields (api keys, tokens, passwords) are stored
    with 0600 permissions and never logged.
    """

    # LLM provider selection
    provider: str
    model: str
    base_url: str
    api_key: str

    # Reasoning / thinking controls
    reasoning_effort: str  # "low", "medium", "high"
    max_tokens: int
    context_window: int

    # Tool execution
    max_output_chars: int
    max_read_bytes: int
    max_line_chars: int
    timeout_ms: int

    # Session behavior
    max_steps: int
    context_window_percentage: float

    # UI / display
    theme: str
    show_timestamps: bool
    show_usage: bool

    # Safety / security
    sandbox_enabled: bool
    allow_network: bool
    allow_file_write: bool
    allow_code_exec: bool

    # Telemetry / observability
    telemetry_enabled: bool
    observability_endpoint: str


# Default values for all config fields. These are the defaults used when
# a field is not present in the stored config file.
DEFAULT_CONFIG: ConfigFields = {
    "provider": "ollama",
    "model": "zcoder-flash",
    "base_url": "http://localhost:11434",
    "api_key": "",
    "reasoning_effort": "medium",
    "max_tokens": 8192,
    "context_window": 32768,
    "max_output_chars": 30_000,
    "max_read_bytes": 2_000_000,
    "max_line_chars": 2_000,
    "timeout_ms": 60_000,
    "max_steps": 40,
    "context_window_percentage": 0.8,
    "theme": "default",
    "show_timestamps": False,
    "show_usage": True,
    "sandbox_enabled": True,
    "allow_network": True,
    "allow_file_write": True,
    "allow_code_exec": True,
    "telemetry_enabled": False,
    "observability_endpoint": "",
}


class Config:
    """Typed configuration for zcoder.

    Reads configuration from ``~/.zcoder-config.json`` (or the legacy
    ``~/.ai-coder-config.json``) on first access and persists changes
    atomically with owner-only permissions.

    All config fields are typed via :class:`ConfigFields`. Unknown keys
    in the stored config are preserved but ignored unless they match a
    known field.
    """

    def __init__(self) -> None:
        self._data: ConfigFields = cast(ConfigFields, dict(DEFAULT_CONFIG))
        read_path = CONFIG_PATH if os.path.exists(CONFIG_PATH) else LEGACY_CONFIG_PATH
        if os.path.exists(read_path):
            try:
                with open(read_path) as f:
                    raw = json.load(f)
                if not isinstance(raw, dict):
                    raise ConfigError(
                        f"Config file {read_path} does not contain a JSON object",
                        details={"path": read_path},
                    )
                coerced = self._validate_and_coerce(raw)
                self._data.update(coerced)
            except ConfigError:
                raise
            except Exception:  # nosec
                # Config file may be missing or unreadable; use defaults.
                pass
        # Env vars override file values; they are the highest precedence layer.
        self._apply_env_overrides()

    def _validate_and_coerce(self, raw: dict[str, Any]) -> ConfigFields:
        """Validate and coerce raw config dict into typed ConfigFields.

        Unknown keys are preserved but ignored. Values are type-coerced
        where possible (e.g. string "42" -> int 42). Invalid values are
        dropped with a warning rather than crashing the load.
        """
        coerced: dict[str, Any] = {}
        for key, value in raw.items():
            if key not in ConfigFields.__annotations__:
                # Unknown key — preserve but ignore
                coerced[key] = value
                continue
            try:
                coerced[key] = self._coerce_value(key, value)
            except (TypeError, ValueError) as exc:
                # Invalid value — drop it but keep going
                import logging

                logging.getLogger(__name__).warning("Ignoring invalid config value for %s: %s", key, exc)
        return coerced  # type: ignore[return-value]

    def _coerce_value(self, key: str, value: Any) -> Any:
        """Coerce a raw config value to the expected type for the given key."""
        expected_type = ConfigFields.__annotations__.get(key)
        if expected_type is None or expected_type == Any:
            return value
        if isinstance(value, expected_type):
            return value
        # Try common coercions
        if expected_type is str and isinstance(value, (int, float)):
            return str(value)
        if expected_type is int and isinstance(value, str):
            try:
                return int(value)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Cannot coerce {key}={value!r} to int: {exc}") from exc
        if expected_type is bool and isinstance(value, str):
            if value.lower() in ("true", "1", "yes", "on"):
                return True
            if value.lower() in ("false", "0", "no", "off"):
                return False
            raise ValueError(f"Cannot coerce {key}={value!r} to bool")
        if expected_type is float and isinstance(value, (int, str)):
            try:
                return float(value)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Cannot coerce {key}={value!r} to float: {exc}") from exc
        return value

    def _apply_env_overrides(self) -> None:
        """Apply environment variables as the highest precedence config layer.

        Reads ZCODER_* prefixed environment variables and maps them to
        config field names. E.g. ZCODER_MODEL -> model, ZCODER_API_KEY ->
        api_key, ZCODER_BASE_URL -> base_url.
        """

        prefix = "ZCODER_"
        for env_name, value in os.environ.items():
            if not env_name.startswith(prefix):
                continue
            # Strip prefix and convert to snake_case key name
            key_name = env_name[len(prefix) :].lower()
            # Map known env var names to config field names
            env_to_field = {
                "api_key": "api_key",
                "base_url": "base_url",
                "model": "model",
                "provider": "provider",
                "reasoning_effort": "reasoning_effort",
                "max_tokens": "max_tokens",
                "context_window": "context_window",
                "max_output_chars": "max_output_chars",
                "max_read_bytes": "max_read_bytes",
                "max_line_chars": "max_line_chars",
                "max_steps": "max_steps",
                "context_window_percentage": "context_window_percentage",
                "theme": "theme",
                "show_timestamps": "show_timestamps",
                "show_usage": "show_usage",
                "sandbox_enabled": "sandbox_enabled",
                "allow_network": "allow_network",
                "allow_file_write": "allow_file_write",
                "allow_code_exec": "allow_code_exec",
                "telemetry_enabled": "telemetry_enabled",
                "observability_endpoint": "observability_endpoint",
            }
            field_name = env_to_field.get(key_name)
            if field_name is None:
                # Unknown env var — skip silently
                continue
            try:
                self._data[field_name] = self._coerce_value(field_name, value)  # type: ignore[literal-required]
            except (TypeError, ValueError) as exc:
                import logging

                logging.getLogger(__name__).warning(
                    "Ignoring invalid env var %s=%s: %s", env_name, value, exc
                )

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        if key not in ConfigFields.__annotations__:
            raise ConfigError(
                f"Unknown config key: {key}",
                details={"key": key, "valid_keys": sorted(ConfigFields.__annotations__.keys())},
            )
        updated = dict(self._data)
        updated[key] = value
        self._write_config(updated)

    def _write_config(self, updated: dict[str, Any]):
        """Persist settings atomically with owner-only permissions.

        The config file can carry provider API keys, so the file must be
        readable/writable only by the owner (0600) and never observed in a
        half-written state by a crash or concurrent reader.

        Failure semantics: if serialization, fsync, or the final rename
        fails, both the on-disk file and the in-memory state keep the
        previous values, and no temporary artifact is left behind.
        """
        directory = os.path.dirname(CONFIG_PATH) or "."
        os.makedirs(directory, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix=".zcoder-config.", dir=directory)
        try:
            with os.fdopen(fd, "w") as stream:
                if os.name == "posix":
                    # Restrict permissions before any secret bytes are written.
                    os.fchmod(stream.fileno(), 0o600)
                json.dump(updated, stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, CONFIG_PATH)
        except Exception:
            try:
                os.unlink(temp_path)
            except OSError:
                # Temp file cleanup may fail; safe to ignore.
                pass
            raise
        try:
            # Cover upgrades from a legacy config file that was created
            # with a permissive umask before this hardening existed.
            os.chmod(CONFIG_PATH, 0o600)
        except OSError:
            # chmod may fail on some filesystems; safe to ignore.
            pass
        # Only publish the new state after the durable write succeeded.
        self._data = cast(ConfigFields, updated)

    def all(self):
        return dict(self._data)
