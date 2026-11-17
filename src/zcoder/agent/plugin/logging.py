"""Logging plugin system for zcoder.

Provides base classes and patterns for logging plugins including
file-based, remote (HTTP), and structured logging. Plugins can hook
into logging events to provide custom log forwarding, filtering,
and enrichment.

Follows the same patterns as the telemetry plugin with HookBus integration.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

from zcoder.agent.plugin.events import HookEvent
from zcoder.agent.plugin.hook_bus import HookBus, HookContext, HookResult
from zcoder.agent.plugin.tier import PluginTier
from zcoder.core.resilience import safe_urlopen

logger = logging.getLogger(__name__)


# ─── Logging event types ─────────────────────────────────────────────────────

# Logging events use existing HookEvent values:
#   UI_LOG        - General log events
#   TELEMETRY_LOG - Telemetry log events
#   TELEMETRY_MARK - Telemetry mark events
# Log level is carried in the LogRecord.level field


# ─── Log record types ────────────────────────────────────────────────────────


@dataclass
class LogRecord:
    """A single log record."""

    level: str  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    message: str
    logger_name: str = "zcoder"
    timestamp: float = field(default_factory=time.time)
    session_id: str = ""
    principal_id: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    exception: str | None = None


@dataclass
class LogDestination:
    """Configuration for a log destination."""

    name: str
    type: str  # file, http, stdout, stderr, syslog
    enabled: bool = True
    min_level: str = "DEBUG"
    config: dict[str, Any] = field(default_factory=dict)


# ─── Logging plugin base class ───────────────────────────────────────────────


class LoggingPlugin:
    """Base class for logging plugins.

    Logging plugins can:
    - Forward logs to external systems (file, HTTP, syslog, etc.)
    - Filter and enrich log records
    - Hook into logging events via the HookBus

    Subclasses should implement the abstract methods and register hook
    handlers via the provided HookBus.
    """

    def __init__(
        self,
        name: str,
        hook_bus: HookBus | None = None,
        enabled: bool = True,
        tier: PluginTier = PluginTier.USER,
        min_level: str = "DEBUG",
    ):
        self.name = name
        self.hook_bus = hook_bus
        self.enabled = enabled
        self.tier = tier
        self.min_level = min_level
        self._destinations: dict[str, LogDestination] = {}
        self._log_count: int = 0
        self._error_count: int = 0

    def _should_log(self, level: str) -> bool:
        """Check if a log record at the given level should be processed."""
        level_order = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
        return level_order.get(level, 0) >= level_order.get(self.min_level, 0)

    def log(self, record: LogRecord) -> None:
        """Process a log record.

        Subclasses should override this method to implement their
        logging logic (e.g., write to file, send to HTTP endpoint, etc.).
        """
        raise NotImplementedError(f"{self.__class__.__name__}.log() not implemented")

    def add_destination(self, destination: LogDestination) -> None:
        """Add a log destination."""
        self._destinations[destination.name] = destination

    def remove_destination(self, name: str) -> bool:
        """Remove a log destination. Returns True if found and removed."""
        if name in self._destinations:
            del self._destinations[name]
            return True
        return False

    def get_destination(self, name: str) -> LogDestination | None:
        """Get a log destination by name."""
        return self._destinations.get(name)

    def list_destinations(self) -> list[str]:
        """List all destination names."""
        return list(self._destinations.keys())

    def register_hooks(self, hook_bus: HookBus) -> None:
        """Register hook handlers for logging events.

        Subclasses should override this to register their hook handlers.
        By default, no hooks are registered.
        """
        pass

    def enable(self):
        """Enable the plugin."""
        self.enabled = True

    def disable(self):
        """Disable the plugin."""
        self.enabled = False

    def get_stats(self) -> dict[str, Any]:
        """Get logging statistics."""
        return {
            "name": self.name,
            "enabled": self.enabled,
            "tier": self.tier.name,
            "min_level": self.min_level,
            "log_count": self._log_count,
            "error_count": self._error_count,
            "destinations": list(self._destinations.keys()),
        }


# ─── Built-in logging hook handlers ──────────────────────────────────────────


class LoggingHooks:
    """Hook handlers for logging events."""

    def __init__(self, plugin: LoggingPlugin, hook_bus: HookBus):
        self.plugin = plugin
        self.hook_bus = hook_bus
        self._register_hooks()

    def _register_hooks(self):
        """Register all logging hooks."""
        self.hook_bus.register(HookEvent.UI_LOG, self._on_log)
        self.hook_bus.register(HookEvent.TELEMETRY_LOG, self._on_log)

    async def _on_log(self, context: HookContext) -> HookResult:
        """Handle general log events."""
        if not self.plugin.enabled:
            return HookResult()

        level = context.args.get("level", "INFO")
        message = context.args.get("message", "")
        logger_name = context.args.get("logger_name", "zcoder")

        record = LogRecord(
            level=level,
            message=message,
            logger_name=logger_name,
            session_id=context.session_id,
            principal_id=context.extra.get("principal_id"),
            context=context.args.get("context", {}),
        )

        self.plugin.log(record)
        return HookResult()


def create_logging_plugin(
    name: str,
    hook_bus: HookBus | None = None,
    enabled: bool = True,
    tier: PluginTier = PluginTier.USER,
    min_level: str = "DEBUG",
) -> LoggingPlugin:
    """Create a basic logging plugin.

    This is a factory function for creating LoggingPlugin instances.
    For custom logging logic, subclass LoggingPlugin instead.
    """
    return LoggingPlugin(
        name=name,
        hook_bus=hook_bus,
        enabled=enabled,
        tier=tier,
        min_level=min_level,
    )


# ─── Built-in logging implementations ────────────────────────────────────────


class FileLoggingPlugin(LoggingPlugin):
    """File-based logging plugin.

    Writes log records to a file in JSON format.
    """

    def __init__(
        self,
        name: str = "file_logging",
        hook_bus: HookBus | None = None,
        log_file: str | None = None,
        **kwargs,
    ):
        super().__init__(name=name, hook_bus=hook_bus, **kwargs)
        # ค่าเริ่มต้นอยู่ใต้ home ของผู้ใช้ ไม่ใช่ /tmp ที่ผู้ใช้อื่นสร้าง symlink ดักไว้ได้
        self.log_file = log_file or os.path.join(os.path.expanduser("~/.zcoder/logs"), f"zcoder_{name}.log")
        self._file_handle = None
        self._open_file()

    def _open_file(self):
        """Open the log file for writing."""
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.log_file)), mode=0o700, exist_ok=True)
            self._file_handle = open(self.log_file, "a", encoding="utf-8")
        except OSError as exc:
            logger.warning(f"Failed to open log file {self.log_file}: {exc}")
            self._file_handle = None

    def _close_file(self):
        """Close the log file."""
        if self._file_handle:
            try:
                self._file_handle.close()
            except OSError:
                pass
            self._file_handle = None

    def log(self, record: LogRecord) -> None:
        """Write a log record to the file."""
        if not self.enabled:
            return
        if not self._should_log(record.level):
            return

        entry = {
            "timestamp": record.timestamp,
            "level": record.level,
            "logger": record.logger_name,
            "message": record.message,
            "session_id": record.session_id,
            "principal_id": record.principal_id,
            "context": record.context,
            "exception": record.exception,
        }

        line = json.dumps(entry, default=str)
        if self._file_handle:
            try:
                self._file_handle.write(line + "\n")
                self._file_handle.flush()
            except OSError as exc:
                logger.warning(f"Failed to write to log file: {exc}")

        self._log_count += 1
        if record.level in ("ERROR", "CRITICAL"):
            self._error_count += 1

    def disable(self):
        """Disable the plugin and close the file."""
        super().disable()
        self._close_file()


class HttpLoggingPlugin(LoggingPlugin):
    """HTTP-based logging plugin.

    Sends log records to an HTTP endpoint as JSON.
    """

    def __init__(
        self,
        name: str = "http_logging",
        hook_bus: HookBus | None = None,
        endpoint_url: str | None = None,
        timeout: float = 5.0,
        **kwargs,
    ):
        super().__init__(name=name, hook_bus=hook_bus, **kwargs)
        self.endpoint_url = endpoint_url or ""
        self.timeout = timeout

    def log(self, record: LogRecord) -> None:
        """Send a log record to the HTTP endpoint."""
        if not self.enabled:
            return
        if not self._should_log(record.level):
            return
        if not self.endpoint_url:
            logger.warning(f"Logging plugin {self.name} has no endpoint URL")
            return

        import urllib.error
        import urllib.request

        entry = {
            "timestamp": record.timestamp,
            "level": record.level,
            "logger": record.logger_name,
            "message": record.message,
            "session_id": record.session_id,
            "principal_id": record.principal_id,
            "context": record.context,
            "exception": record.exception,
        }

        data = json.dumps(entry, default=str).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with safe_urlopen(req, timeout=self.timeout) as resp:
                if resp.status >= 400:
                    logger.warning(f"HTTP logging endpoint returned {resp.status}")
        except urllib.error.URLError as exc:
            logger.warning(f"Failed to send log to {self.endpoint_url}: {exc}")
        except Exception as exc:
            logger.warning(f"Unexpected error sending log: {exc}")

        self._log_count += 1
        if record.level in ("ERROR", "CRITICAL"):
            self._error_count += 1


# ─── Export ──────────────────────────────────────────────────────────────────


__all__ = [
    "LogRecord",
    "LogDestination",
    "LoggingPlugin",
    "LoggingHooks",
    "FileLoggingPlugin",
    "HttpLoggingPlugin",
    "create_logging_plugin",
]
