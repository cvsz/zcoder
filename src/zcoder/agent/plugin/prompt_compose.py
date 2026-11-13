"""Prompt composition hooks for zcoder plugin system.

Implements organization-controlled prompt composition hooks,
compatible with claude-code's prompt.compose, prompt.section, prompt.context,
prompt.attachment, skill.prompt, attribution.text events.
"""

import logging
from dataclasses import dataclass

from zcoder.agent.plugin.events import HookEvent
from zcoder.agent.plugin.hook_bus import HookBus, HookContext, HookResult
from zcoder.agent.plugin.tier import PluginTier

logger = logging.getLogger(__name__)


@dataclass
class PromptCompositionHooks:
    """Hook handlers for prompt composition events."""

    hook_bus: HookBus

    def __post_init__(self):
        self.hook_bus.register(HookEvent.PROMPT_COMPOSE, self._on_compose)
        self.hook_bus.register(HookEvent.PROMPT_SECTION, self._on_section)
        self.hook_bus.register(HookEvent.PROMPT_CONTEXT, self._on_context)
        self.hook_bus.register(HookEvent.PROMPT_ATTACHMENT, self._on_attachment)
        self.hook_bus.register(HookEvent.SKILL_PROMPT, self._on_skill_prompt)
        self.hook_bus.register(HookEvent.ATTRIBUTION_TEXT, self._on_attribution)

    async def _on_compose(self, context: HookContext) -> HookResult:
        """Handle prompt.compose event - org controls system prompt."""
        if context.origin_tier == PluginTier.USER:
            return HookResult(modified_args={"continue_past_user_tier": True})
        return HookResult()

    async def _on_section(self, context: HookContext) -> HookResult:
        """Handle prompt.section event - org controls sections."""
        if context.origin_tier == PluginTier.USER:
            return HookResult(modified_args={"continue_past_user_tier": True})
        return HookResult()

    async def _on_context(self, context: HookContext) -> HookResult:
        """Handle prompt.context event - org controls context."""
        if context.origin_tier == PluginTier.USER:
            return HookResult(modified_args={"continue_past_user_tier": True})
        return HookResult()

    async def _on_attachment(self, context: HookContext) -> HookResult:
        """Handle prompt.attachment event - org controls attachments."""
        if context.origin_tier == PluginTier.USER:
            return HookResult(modified_args={"continue_past_user_tier": True})
        return HookResult()

    async def _on_skill_prompt(self, context: HookContext) -> HookResult:
        """Handle skill.prompt event - org controls skill prompts."""
        if context.origin_tier == PluginTier.USER:
            return HookResult(modified_args={"continue_past_user_tier": True})
        return HookResult()

    async def _on_attribution(self, context: HookContext) -> HookResult:
        """Handle attribution.text event - org controls attribution."""
        if context.origin_tier == PluginTier.USER:
            return HookResult(modified_args={"continue_past_user_tier": True})
        return HookResult()


def create_prompt_composition_hooks(hook_bus: HookBus) -> PromptCompositionHooks:
    """Create prompt composition hooks."""
    return PromptCompositionHooks(hook_bus=hook_bus)