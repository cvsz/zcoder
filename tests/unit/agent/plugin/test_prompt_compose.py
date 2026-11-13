"""Tests for prompt composition hooks."""

import pytest

from zcoder.agent.plugin.events import HookEvent
from zcoder.agent.plugin.hook_bus import HookContext
from zcoder.agent.plugin.prompt_compose import create_prompt_composition_hooks
from zcoder.agent.plugin.tier import PluginTier


class TestPromptCompositionHooks:
    """Tests for PromptCompositionHooks."""

    @pytest.fixture
    def hooks(self):
        """Create hooks fixture."""
        from zcoder.agent.plugin.hook_bus import HookBus
        from zcoder.agent.plugin.manager import PluginManager

        manager = PluginManager()
        bus = HookBus(manager)
        return create_prompt_composition_hooks(bus)

    async def test_prompt_compose_user_continues(self, hooks):
        """Test user tier continues past user tier for prompt.compose."""
        ctx = HookContext(
            event=HookEvent.PROMPT_COMPOSE,
            origin_tier=PluginTier.USER,
        )
        result = await hooks._on_compose(ctx)
        assert result.blocked is False
        assert result.modified_args is not None
        assert result.modified_args.get("continue_past_user_tier") is True

    async def test_prompt_section_user_continues(self, hooks):
        """Test user tier continues past user tier for prompt.section."""
        ctx = HookContext(
            event=HookEvent.PROMPT_SECTION,
            origin_tier=PluginTier.USER,
        )
        result = await hooks._on_section(ctx)
        assert result.blocked is False
        assert result.modified_args is not None
        assert result.modified_args.get("continue_past_user_tier") is True

    async def test_prompt_context_user_continues(self, hooks):
        """Test user tier continues past user tier for prompt.context."""
        ctx = HookContext(
            event=HookEvent.PROMPT_CONTEXT,
            origin_tier=PluginTier.USER,
        )
        result = await hooks._on_context(ctx)
        assert result.blocked is False
        assert result.modified_args is not None
        assert result.modified_args.get("continue_past_user_tier") is True

    async def test_prompt_attachment_user_continues(self, hooks):
        """Test user tier continues past user tier for prompt.attachment."""
        ctx = HookContext(
            event=HookEvent.PROMPT_ATTACHMENT,
            origin_tier=PluginTier.USER,
        )
        result = await hooks._on_attachment(ctx)
        assert result.blocked is False
        assert result.modified_args is not None
        assert result.modified_args.get("continue_past_user_tier") is True

    async def test_skill_prompt_user_continues(self, hooks):
        """Test user tier continues past user tier for skill.prompt."""
        ctx = HookContext(
            event=HookEvent.SKILL_PROMPT,
            origin_tier=PluginTier.USER,
        )
        result = await hooks._on_skill_prompt(ctx)
        assert result.blocked is False
        assert result.modified_args is not None
        assert result.modified_args.get("continue_past_user_tier") is True

    async def test_attribution_text_user_continues(self, hooks):
        """Test user tier continues past user tier for attribution.text."""
        ctx = HookContext(
            event=HookEvent.ATTRIBUTION_TEXT,
            origin_tier=PluginTier.USER,
        )
        result = await hooks._on_attribution(ctx)
        assert result.blocked is False
        assert result.modified_args is not None
        assert result.modified_args.get("continue_past_user_tier") is True

    async def test_prepend_tier_not_blocked(self, hooks):
        """Test prepend tier not blocked for any prompt event."""
        for event in [
            HookEvent.PROMPT_COMPOSE,
            HookEvent.PROMPT_SECTION,
            HookEvent.PROMPT_CONTEXT,
            HookEvent.PROMPT_ATTACHMENT,
            HookEvent.SKILL_PROMPT,
            HookEvent.ATTRIBUTION_TEXT,
        ]:
            ctx = HookContext(event=event, origin_tier=PluginTier.PREPEND)
            if event == HookEvent.PROMPT_COMPOSE:
                result = await hooks._on_compose(ctx)
            elif event == HookEvent.PROMPT_SECTION:
                result = await hooks._on_section(ctx)
            elif event == HookEvent.PROMPT_CONTEXT:
                result = await hooks._on_context(ctx)
            elif event == HookEvent.PROMPT_ATTACHMENT:
                result = await hooks._on_attachment(ctx)
            elif event == HookEvent.SKILL_PROMPT:
                result = await hooks._on_skill_prompt(ctx)
            else:
                result = await hooks._on_attribution(ctx)
            assert result.blocked is False, f"Prepend blocked for {event}"
