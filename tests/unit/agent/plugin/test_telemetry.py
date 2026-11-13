"""Tests for telemetry plugin."""

import pytest

from zcoder.agent.plugin.events import HookEvent
from zcoder.agent.plugin.hook_bus import HookContext
from zcoder.agent.plugin.telemetry import TelemetryHooks, TelemetryPlugin, create_telemetry_plugin
from zcoder.agent.plugin.tier import PluginTier


class TestTelemetryPlugin:
    """Tests for TelemetryPlugin."""

    def test_log(self):
        """Test logging an event."""
        plugin = TelemetryPlugin()
        plugin.log("test_event", {"key": "value"})
        assert len(plugin.event_queue) == 1
        assert plugin.event_queue[0].event == "test_event"
        assert plugin.event_queue[0].props == {"key": "value"}

    def test_mark_ok(self):
        """Test marking a feature as ok."""
        plugin = TelemetryPlugin()
        plugin.mark("feature1", "ok")
        assert len(plugin.mark_queue) == 1
        assert plugin.mark_queue[0].feature == "feature1"
        assert plugin.mark_queue[0].kind == "ok"

    def test_mark_sad_requires_reason(self):
        """Test sad mark requires reason."""
        plugin = TelemetryPlugin()
        with pytest.raises(ValueError, match="Reason required"):
            plugin.mark("feature1", "sad")

    def test_mark_bad_requires_reason(self):
        """Test bad mark requires reason."""
        plugin = TelemetryPlugin()
        with pytest.raises(ValueError, match="Reason required"):
            plugin.mark("feature1", "bad")

    def test_mark_sad_with_reason(self):
        """Test sad mark with reason."""
        plugin = TelemetryPlugin()
        plugin.mark("feature1", "sad", reason="failed")
        assert len(plugin.mark_queue) == 1
        assert plugin.mark_queue[0].reason == "failed"

    def test_invalid_kind(self):
        """Test invalid kind raises error."""
        plugin = TelemetryPlugin()
        with pytest.raises(ValueError, match="Invalid mark kind"):
            plugin.mark("feature1", "invalid")

    def test_validate_event_name(self):
        """Test event name validation."""
        plugin = TelemetryPlugin()
        assert plugin._validate_event_name("valid_event") is True
        assert plugin._validate_event_name("ValidEvent") is False
        assert plugin._validate_event_name("123invalid") is False

    def test_disable(self):
        """Test disabling plugin."""
        plugin = TelemetryPlugin()
        plugin.disable()
        assert plugin.enabled is False
        plugin.log("test", {})
        assert len(plugin.event_queue) == 0  # Should not add when disabled


class TestTelemetryHooks:
    """Tests for TelemetryHooks."""

    @pytest.fixture
    def hooks(self):
        """Create hooks fixture."""
        from zcoder.agent.plugin.hook_bus import HookBus
        from zcoder.agent.plugin.manager import PluginManager

        manager = PluginManager()
        bus = HookBus(manager)
        plugin = create_telemetry_plugin(bus)
        return TelemetryHooks(plugin=plugin, hook_bus=bus)

    async def test_telemetry_log_builtin_allowed(self, hooks):
        """Test builtin tier can log."""
        ctx = HookContext(
            event=HookEvent.TELEMETRY_LOG,
            origin_tier=PluginTier.BUILTIN,
            args={"event": "test_event", "props": {"key": "value"}},
        )
        result = await hooks._on_log(ctx)
        assert result.blocked is False
        assert len(hooks.plugin.event_queue) == 1

    async def test_telemetry_log_user_blocked(self, hooks):
        """Test user tier blocked from logging."""
        ctx = HookContext(
            event=HookEvent.TELEMETRY_LOG,
            origin_tier=PluginTier.USER,
            args={"event": "test_event", "props": {}},
        )
        result = await hooks._on_log(ctx)
        assert result.blocked is True
        assert result.deny_reason == "telemetry_gate"

    async def test_telemetry_mark_builtin_allowed(self, hooks):
        """Test builtin tier can mark."""
        ctx = HookContext(
            event=HookEvent.TELEMETRY_MARK,
            origin_tier=PluginTier.BUILTIN,
            args={"feature": "feature1", "kind": "ok"},
        )
        result = await hooks._on_mark(ctx)
        assert result.blocked is False
        assert len(hooks.plugin.mark_queue) == 1

    async def test_telemetry_mark_user_blocked(self, hooks):
        """Test user tier blocked from marking."""
        ctx = HookContext(
            event=HookEvent.TELEMETRY_MARK,
            origin_tier=PluginTier.USER,
            args={"feature": "feature1", "kind": "ok"},
        )
        result = await hooks._on_mark(ctx)
        assert result.blocked is True
        assert result.deny_reason == "telemetry_gate"

    async def test_telemetry_mark_invalid_kind(self, hooks):
        """Test invalid kind blocked."""
        ctx = HookContext(
            event=HookEvent.TELEMETRY_MARK,
            origin_tier=PluginTier.BUILTIN,
            args={"feature": "feature1", "kind": "invalid"},
        )
        result = await hooks._on_mark(ctx)
        assert result.blocked is True
        assert result.deny_reason == "telemetry_validation"

    async def test_telemetry_mark_sad_requires_reason(self, hooks):
        """Test sad mark without reason blocked."""
        ctx = HookContext(
            event=HookEvent.TELEMETRY_MARK,
            origin_tier=PluginTier.BUILTIN,
            args={"feature": "feature1", "kind": "sad"},
        )
        result = await hooks._on_mark(ctx)
        assert result.blocked is True
        assert result.deny_reason == "telemetry_validation"
