"""Tests for session compaction hooks."""

import pytest

from zcoder.agent.plugin.compaction import create_compaction_hooks
from zcoder.agent.plugin.events import HookEvent
from zcoder.agent.plugin.hook_bus import HookContext
from zcoder.agent.plugin.tier import PluginTier


class TestCompactionHooks:
    """Tests for CompactionHooks."""

    @pytest.fixture
    def hooks(self):
        """Create hooks fixture."""
        from zcoder.agent.plugin.hook_bus import HookBus
        from zcoder.agent.plugin.manager import PluginManager
        manager = PluginManager()
        bus = HookBus(manager)
        return create_compaction_hooks(bus)

    async def test_session_compact_user_continues(self, hooks):
        """Test user tier continues past user tier."""
        ctx = HookContext(
            event=HookEvent.SESSION_COMPACT,
            origin_tier=PluginTier.USER,
        )
        result = await hooks._on_compact(ctx)
        assert result.blocked is False
        assert result.modified_args is not None
        assert result.modified_args.get("continue_past_user_tier") is True

    async def test_session_compact_prepend_allowed(self, hooks):
        """Test prepend tier not blocked."""
        ctx = HookContext(
            event=HookEvent.SESSION_COMPACT,
            origin_tier=PluginTier.PREPEND,
        )
        result = await hooks._on_compact(ctx)
        assert result.blocked is False

    async def test_pre_compact_user_continues(self, hooks):
        """Test user tier continues past user tier for pre_compact."""
        ctx = HookContext(
            event=HookEvent.CLASSIC_PRE_COMPACT,
            origin_tier=PluginTier.USER,
        )
        result = await hooks._on_pre_compact(ctx)
        assert result.blocked is False
        assert result.modified_args is not None
        assert result.modified_args.get("continue_past_user_tier") is True

    async def test_post_compact_user_continues(self, hooks):
        """Test user tier continues past user tier for post_compact."""
        ctx = HookContext(
            event=HookEvent.CLASSIC_POST_COMPACT,
            origin_tier=PluginTier.USER,
        )
        result = await hooks._on_post_compact(ctx)
        assert result.blocked is False
        assert result.modified_args is not None
        assert result.modified_args.get("continue_past_user_tier") is True