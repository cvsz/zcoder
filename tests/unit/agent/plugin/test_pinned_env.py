"""Tests for pinned environment variables."""

import pytest

from zcoder.agent.plugin.events import HookEvent
from zcoder.agent.plugin.hook_bus import HookContext
from zcoder.agent.plugin.pinned_env import (
    ALWAYS_PINNED,
    PinnedEnvHooks,
    PinnedEnvManager,
    create_pinned_env_manager,
)
from zcoder.agent.plugin.tier import PluginTier


class TestPinnedEnvManager:
    """Tests for PinnedEnvManager."""

    def test_always_pinned(self):
        """Test always pinned variables."""
        manager = PinnedEnvManager()
        for var in ALWAYS_PINNED:
            assert manager.is_pinned(var) is True

    def test_not_pinned(self):
        """Test non-pinned variables."""
        manager = PinnedEnvManager()
        assert manager.is_pinned("MY_CUSTOM_VAR") is False
        assert manager.is_pinned("PATH") is False

    def test_managed_env_pinned(self):
        """Test managed env vars are pinned."""
        manager = PinnedEnvManager()
        manager.set_managed_env({"ORG_API_KEY": "secret"})
        assert manager.is_pinned("ORG_API_KEY") is True

    def test_launcher_pinned(self):
        """Test launcher variable is pinned when launcher set."""
        manager = PinnedEnvManager()
        manager.set_launcher("my_launcher")
        assert manager.is_pinned("CLAUDE_CODE_PROCESS_WRAPPER") is True

    def test_check_write_prepend_allowed(self):
        """Test prepend tier can write pinned vars."""
        manager = PinnedEnvManager()
        result = manager.check_write("LD_PRELOAD", PluginTier.PREPEND)
        assert result.blocked is False

    def test_check_write_append_allowed(self):
        """Test append tier can write pinned vars."""
        manager = PinnedEnvManager()
        result = manager.check_write("LD_PRELOAD", PluginTier.APPEND)
        assert result.blocked is False

    def test_check_write_builtin_allowed(self):
        """Test builtin tier can write pinned vars."""
        manager = PinnedEnvManager()
        result = manager.check_write("LD_PRELOAD", PluginTier.BUILTIN)
        assert result.blocked is False

    def test_check_write_user_blocked(self):
        """Test user tier blocked from writing pinned vars."""
        manager = PinnedEnvManager()
        result = manager.check_write("LD_PRELOAD", PluginTier.USER)
        assert result.blocked is True
        assert result.deny_reason == "pinned_env"

    def test_check_write_user_allowed_non_pinned(self):
        """Test user tier can write non-pinned vars."""
        manager = PinnedEnvManager()
        result = manager.check_write("MY_CUSTOM_VAR", PluginTier.USER)
        assert result.blocked is False

    def test_check_read_prepend_continues(self):
        """Test prepend tier continues past user tier on read."""
        manager = PinnedEnvManager()
        result = manager.check_read("LD_PRELOAD", PluginTier.PREPEND)
        assert result.blocked is False
        assert result.modified_args is not None
        assert result.modified_args.get("continue_past_user_tier") is True


class TestPinnedEnvHooks:
    """Tests for PinnedEnvHooks."""

    @pytest.fixture
    def hooks(self):
        """Create hooks fixture."""
        from zcoder.agent.plugin.hook_bus import HookBus
        from zcoder.agent.plugin.manager import PluginManager

        manager = PluginManager()
        bus = HookBus(manager)
        mgr = create_pinned_env_manager(bus)
        return PinnedEnvHooks(manager=mgr, hook_bus=bus)

    async def test_env_set_user_blocked(self, hooks):
        """Test user tier blocked from setting pinned var."""
        ctx = HookContext(
            event=HookEvent.ENV_SET,
            origin_tier=PluginTier.USER,
            args={"name": "LD_PRELOAD", "value": "/lib.so"},
        )
        result = await hooks._on_env_set(ctx)
        assert result.blocked is True
        assert result.deny_reason == "pinned_env"

    async def test_env_set_user_allowed_non_pinned(self, hooks):
        """Test user tier can set non-pinned var."""
        ctx = HookContext(
            event=HookEvent.ENV_SET,
            origin_tier=PluginTier.USER,
            args={"name": "MY_VAR", "value": "value"},
        )
        result = await hooks._on_env_set(ctx)
        assert result.blocked is False

    async def test_env_set_prepend_allowed(self, hooks):
        """Test prepend tier can set pinned var."""
        ctx = HookContext(
            event=HookEvent.ENV_SET,
            origin_tier=PluginTier.PREPEND,
            args={"name": "LD_PRELOAD", "value": "/lib.so"},
        )
        result = await hooks._on_env_set(ctx)
        assert result.blocked is False

    async def test_env_get_prepend_continues(self, hooks):
        """Test prepend tier continues past user tier on get."""
        ctx = HookContext(
            event=HookEvent.ENV_GET,
            origin_tier=PluginTier.PREPEND,
            args={"name": "LD_PRELOAD"},
        )
        result = await hooks._on_env_get(ctx)
        assert result.blocked is False
        assert result.modified_args is not None
        assert result.modified_args.get("continue_past_user_tier") is True
