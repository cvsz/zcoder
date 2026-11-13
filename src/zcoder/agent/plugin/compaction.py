"""Session compaction hooks for zcoder plugin system.

Implements organization-controlled session compaction hooks,
compatible with claude-code's session.compact, pre_compact, post_compact events.
"""

import logging
from dataclasses import dataclass

from zcoder.agent.plugin.events import HookEvent
from zcoder.agent.plugin.hook_bus import HookBus, HookContext, HookResult
from zcoder.agent.plugin.tier import PluginTier

logger = logging.getLogger(__name__)


@dataclass
class CompactionHooks:
    """Hook handlers for session compaction events."""

    hook_bus: HookBus

    def __post_init__(self):
        self.hook_bus.register(HookEvent.SESSION_COMPACT, self._on_compact)
        self.hook_bus.register(HookEvent.CLASSIC_PRE_COMPACT, self._on_pre_compact)
        self.hook_bus.register(HookEvent.CLASSIC_POST_COMPACT, self._on_post_compact)

    async def _on_compact(self, context: HookContext) -> HookResult:
        """Handle session.compact event - org/engine controlled."""
        # Continue past user tier: compaction is org/engine controlled
        if context.origin_tier == PluginTier.USER:
            return HookResult(modified_args={"continue_past_user_tier": True})
        return HookResult()

    async def _on_pre_compact(self, context: HookContext) -> HookResult:
        """Handle classic.pre_compact event - org/engine controlled."""
        if context.origin_tier == PluginTier.USER:
            return HookResult(modified_args={"continue_past_user_tier": True})
        return HookResult()

    async def _on_post_compact(self, context: HookContext) -> HookResult:
        """Handle classic.post_compact event - org/engine controlled."""
        if context.origin_tier == PluginTier.USER:
            return HookResult(modified_args={"continue_past_user_tier": True})
        return HookResult()


def create_compaction_hooks(hook_bus: HookBus) -> CompactionHooks:
    """Create compaction hooks."""
    return CompactionHooks(hook_bus=hook_bus)
