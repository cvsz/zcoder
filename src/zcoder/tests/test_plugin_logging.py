"""Tests for zcoder.agent.plugin.logging - Logging plugin system."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from zcoder.agent.plugin.hook_bus import HookBus
from zcoder.agent.plugin.logging import (
    FileLoggingPlugin,
    HttpLoggingPlugin,
    LogDestination,
    LoggingHooks,
    LoggingPlugin,
    LogRecord,
)
from zcoder.agent.plugin.manager import PluginManager
from zcoder.agent.plugin.tier import PluginTier


class TestLogRecord:
    """Tests for LogRecord dataclass."""

    def test_creation(self):
        record = LogRecord(
            level="INFO",
            message="Test message",
            logger_name="my_logger",
            session_id="sess-1",
            principal_id="user-1",
            context={"key": "value"},
        )
        assert record.level == "INFO"
        assert record.message == "Test message"
        assert record.logger_name == "my_logger"
        assert record.session_id == "sess-1"
        assert record.principal_id == "user-1"
        assert record.context == {"key": "value"}
        assert record.exception is None
        assert record.timestamp > 0

    def test_creation_minimal(self):
        record = LogRecord(level="ERROR", message="Something failed")
        assert record.level == "ERROR"
        assert record.message == "Something failed"
        assert record.logger_name == "zcoder"
        assert record.session_id == ""
        assert record.context == {}


class TestLogDestination:
    """Tests for LogDestination dataclass."""

    def test_creation(self):
        dest = LogDestination(
            name="file_dest",
            type="file",
            enabled=True,
            min_level="WARNING",
            config={"path": "/tmp/log.txt"},
        )
        assert dest.name == "file_dest"
        assert dest.type == "file"
        assert dest.enabled is True
        assert dest.min_level == "WARNING"
        assert dest.config == {"path": "/tmp/log.txt"}


class TestLoggingPlugin:
    """Tests for LoggingPlugin base class."""

    def test_creation(self):
        plugin = LoggingPlugin(name="test_logging")
        assert plugin.name == "test_logging"
        assert plugin.enabled is True
        assert plugin.tier == PluginTier.USER
        assert plugin.min_level == "DEBUG"
        assert plugin.hook_bus is None

    def test_should_log(self):
        plugin = LoggingPlugin(name="test", min_level="WARNING")
        assert plugin._should_log("DEBUG") is False
        assert plugin._should_log("INFO") is False
        assert plugin._should_log("WARNING") is True
        assert plugin._should_log("ERROR") is True
        assert plugin._should_log("CRITICAL") is True

    def test_log_not_implemented(self):
        plugin = LoggingPlugin(name="test")
        record = LogRecord(level="INFO", message="test")
        with pytest.raises(NotImplementedError):
            plugin.log(record)

    def test_add_remove_destination(self):
        plugin = LoggingPlugin(name="test")
        dest = LogDestination(name="dest1", type="file", config={"path": "/tmp/test.log"})
        plugin.add_destination(dest)
        assert plugin.get_destination("dest1") is dest
        assert "dest1" in plugin.list_destinations()

        assert plugin.remove_destination("dest1") is True
        assert plugin.get_destination("dest1") is None
        assert plugin.remove_destination("nonexistent") is False

    def test_enable_disable(self):
        plugin = LoggingPlugin(name="test")
        assert plugin.enabled is True

        plugin.disable()
        assert plugin.enabled is False

        plugin.enable()
        assert plugin.enabled is True

    def test_get_stats(self):
        plugin = LoggingPlugin(name="test_logging")
        stats = plugin.get_stats()
        assert stats["name"] == "test_logging"
        assert stats["enabled"] is True
        assert stats["tier"] == "USER"
        assert stats["min_level"] == "DEBUG"
        assert stats["log_count"] == 0
        assert stats["error_count"] == 0
        assert stats["destinations"] == []


class TestFileLoggingPlugin:
    """Tests for FileLoggingPlugin."""

    def test_creation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            plugin = FileLoggingPlugin(name="file_test", log_file=str(log_file))
            assert plugin.log_file == str(log_file)
            assert plugin._file_handle is not None
            plugin.disable()

    def test_log_to_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            plugin = FileLoggingPlugin(name="file_test", log_file=str(log_file))
            try:
                record = LogRecord(
                    level="INFO",
                    message="Test message",
                    logger_name="test_logger",
                    session_id="sess-1",
                    principal_id="user-1",
                )
                plugin.log(record)

                # Read the file and verify
                content = log_file.read_text()
                entry = json.loads(content.strip())
                assert entry["level"] == "INFO"
                assert entry["message"] == "Test message"
                assert entry["logger"] == "test_logger"
                assert entry["session_id"] == "sess-1"
                assert entry["principal_id"] == "user-1"
            finally:
                plugin.disable()

    def test_log_level_filtering(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            plugin = FileLoggingPlugin(name="file_test", log_file=str(log_file), min_level="WARNING")
            try:
                # DEBUG should not be logged
                plugin.log(LogRecord(level="DEBUG", message="debug msg"))
                # ERROR should be logged
                plugin.log(LogRecord(level="ERROR", message="error msg"))

                content = log_file.read_text()
                lines = [line for line in content.strip().split("\n") if line]
                assert len(lines) == 1
                entry = json.loads(lines[0])
                assert entry["level"] == "ERROR"
                assert entry["message"] == "error msg"
            finally:
                plugin.disable()

    def test_stats_tracking(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            plugin = FileLoggingPlugin(name="file_test", log_file=str(log_file))
            try:
                plugin.log(LogRecord(level="INFO", message="info msg"))
                plugin.log(LogRecord(level="ERROR", message="error msg"))
                plugin.log(LogRecord(level="ERROR", message="another error"))

                stats = plugin.get_stats()
                assert stats["log_count"] == 3
                assert stats["error_count"] == 2
            finally:
                plugin.disable()


class TestHttpLoggingPlugin:
    """Tests for HttpLoggingPlugin."""

    def test_creation(self):
        plugin = HttpLoggingPlugin(name="http_test", endpoint_url="https://example.com/logs")
        assert plugin.endpoint_url == "https://example.com/logs"
        assert plugin.timeout == 5.0

    def test_log_no_endpoint(self):
        plugin = HttpLoggingPlugin(name="http_test")
        # Should not raise, just warn
        plugin.log(LogRecord(level="INFO", message="test"))
        assert plugin._log_count == 0


class TestLoggingHooks:
    """Tests for LoggingHooks."""

    def test_creation(self):

        manager = PluginManager()
        bus = HookBus(manager)
        plugin = LoggingPlugin(name="test_logging")
        hooks = LoggingHooks(plugin=plugin, hook_bus=bus)
        assert hooks.plugin is plugin
        assert hooks.hook_bus is bus
