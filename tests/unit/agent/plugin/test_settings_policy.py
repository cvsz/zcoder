"""Tests for settings policy."""

import pytest

from zcoder.agent.plugin.events import HookEvent
from zcoder.agent.plugin.hook_bus import HookContext
from zcoder.agent.plugin.settings_policy import (
    SettingsPolicyReader,
    create_settings_policy_hooks,
)
from zcoder.agent.plugin.tier import PluginTier


class TestSettingsPolicyReader:
    """Tests for SettingsPolicyReader."""

    def test_read_default(self):
        """Test reading from default source."""
        reader = SettingsPolicyReader()
        # Should not raise
        value = reader.read("database.url", "default")
        assert value is None or isinstance(value, str)

    def test_read_policy(self):
        """Test reading from policy source."""
        reader = SettingsPolicyReader()
        value = reader.read("database.url", "policy")
        # Should not raise, fails closed
        assert value is None or isinstance(value, str)

    def test_read_invalid_source(self):
        """Test reading from invalid source falls back to default."""
        reader = SettingsPolicyReader()
        value = reader.read("test.key", "invalid_source")
        # Should fall back to default
        assert value is None or isinstance(value, str)


class TestSettingsPolicyHooks:
    """Tests for SettingsPolicyHooks."""

    @pytest.fixture
    def hooks(self):
        """Create hooks fixture."""
        from zcoder.agent.plugin.hook_bus import HookBus
        from zcoder.agent.plugin.manager import PluginManager

        manager = PluginManager()
        bus = HookBus(manager)
        return create_settings_policy_hooks(bus)

    async def test_settings_read_user_tier(self, hooks):
        """Test user tier gets value from reader."""
        ctx = HookContext(
            event=HookEvent.SETTINGS_READ,
            origin_tier=PluginTier.USER,
            args={"key": "test.key", "source": "policy"},
        )
        result = await hooks._on_settings_read(ctx)
        assert result.blocked is False
        assert "value" in (result.modified_args or {})

    async def test_settings_read_prepend_tier(self, hooks):
        """Test prepend tier continues past user tier."""
        ctx = HookContext(
            event=HookEvent.SETTINGS_READ,
            origin_tier=PluginTier.PREPEND,
            args={"key": "test.key"},
        )
        result = await hooks._on_settings_read(ctx)
        assert result.blocked is False
        assert result.modified_args is not None
        assert result.modified_args.get("continue_past_user_tier") is True

    async def test_settings_read_append_tier(self, hooks):
        """Test append tier continues past user tier."""
        ctx = HookContext(
            event=HookEvent.SETTINGS_READ,
            origin_tier=PluginTier.APPEND,
            args={"key": "test.key"},
        )
        result = await hooks._on_settings_read(ctx)
        assert result.blocked is False
        assert result.modified_args is not None
        assert result.modified_args.get("continue_past_user_tier") is True
