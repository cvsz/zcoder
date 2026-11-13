"""
Model lifecycle hooks for ZCoder.

Provides hooks for model selection, validation, and capability negotiation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from zcoder.agent.plugin.events import HookEvent
from zcoder.agent.plugin.hook_bus import HookBus, HookContext, HookResult


class ModelLifecycleEvent(StrEnum):
    """Model lifecycle event types."""

    PRE_SELECTION = "model.pre_selection"
    POST_SELECTION = "model.post_selection"
    PRE_SWITCH = "model.pre_switch"
    POST_SWITCH = "model.post_switch"
    CAPABILITY_NEGOTIATION = "model.capability_negotiation"
    VALIDATION = "model.validation"
    HEALTH_CHECK = "model.health_check"
    FALLBACK = "model.fallback"


@dataclass
class ModelInfo:
    """Model information for lifecycle events."""

    model_id: str
    provider: str
    display_name: str = ""
    context_window: int = 0
    max_output: int = 0
    capabilities: list[str] = field(default_factory=list)
    pricing: dict = field(default_factory=dict)
    tier: str = "current"


@dataclass
class ModelSelectionContext:
    """Context for model selection hooks."""

    requested_model: str | None = None
    task_type: str = "general"
    required_capabilities: list[str] = field(default_factory=list)
    budget: float | None = None
    preferred_tier: str = "current"
    exclude_models: list[str] = field(default_factory=list)
    fallback_chain: list[str] = field(default_factory=list)


@dataclass
class ModelValidationResult:
    """Result of model validation."""

    valid: bool
    model_id: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    suggested_alternative: str | None = None


class ModelLifecycleHooks:
    """Manages model lifecycle hooks."""

    def __init__(self, hook_bus: HookBus):
        self.hook_bus = hook_bus

    async def fire_pre_selection(self, context: ModelSelectionContext) -> HookResult:
        """Fire pre-model-selection hook."""
        hook_context = HookContext(
            event=HookEvent.PRE_MODEL_SWITCH,
            args={
                "requested_model": context.requested_model,
                "task_type": context.task_type,
                "required_capabilities": context.required_capabilities,
                "budget": context.budget,
                "preferred_tier": context.preferred_tier,
                "exclude_models": context.exclude_models,
                "fallback_chain": context.fallback_chain,
            },
            extra={
                "event_type": "model.pre_selection",
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
        return await self.hook_bus.fire(hook_context)

    async def fire_post_selection(self, model_info: ModelInfo, context: ModelSelectionContext) -> HookResult:
        """Fire post-model-selection hook."""
        hook_context = HookContext(
            event=HookEvent.POST_MODEL_SWITCH,
            args={
                "selected_model": model_info.model_id,
                "provider": model_info.provider,
                "display_name": model_info.display_name,
                "context_window": model_info.context_window,
                "max_output": model_info.max_output,
                "capabilities": model_info.capabilities,
                "task_type": context.task_type,
                "budget": context.budget,
            },
            extra={
                "event_type": "model.post_selection",
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
        return await self.hook_bus.fire(hook_context)

    async def fire_pre_switch(self, old_model: ModelInfo | None, new_model: ModelInfo) -> HookResult:
        """Fire pre-model-switch hook."""
        hook_context = HookContext(
            event=HookEvent.PRE_MODEL_SWITCH,
            args={
                "old_model": old_model.model_id if old_model else None,
                "new_model": new_model.model_id,
                "old_provider": old_model.provider if old_model else None,
                "new_provider": new_model.provider,
            },
            extra={
                "event_type": "model.pre_switch",
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
        return await self.hook_bus.fire(hook_context)

    async def fire_post_switch(self, old_model: ModelInfo | None, new_model: ModelInfo) -> HookResult:
        """Fire post-model-switch hook."""
        hook_context = HookContext(
            event=HookEvent.POST_MODEL_SWITCH,
            args={
                "old_model": old_model.model_id if old_model else None,
                "new_model": new_model.model_id,
                "old_provider": old_model.provider if old_model else None,
                "new_provider": new_model.provider,
            },
            extra={
                "event_type": "model.post_switch",
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
        return await self.hook_bus.fire(hook_context)

    async def fire_capability_negotiation(
        self,
        model_id: str,
        required_capabilities: list[str],
    ) -> HookResult:
        """Fire capability negotiation hook."""
        hook_context = HookContext(
            event=HookEvent.MODEL_CALL,
            args={
                "model_id": model_id,
                "required_capabilities": required_capabilities,
            },
            extra={
                "event_type": "model.capability_negotiation",
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
        return await self.hook_bus.fire(hook_context)

    async def fire_validation(self, model_id: str) -> HookResult:
        """Fire model validation hook."""
        hook_context = HookContext(
            event=HookEvent.MODEL_CALL,
            args={
                "model_id": model_id,
            },
            extra={
                "event_type": "model.validation",
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
        return await self.hook_bus.fire(hook_context)

    async def fire_health_check(self, model_id: str) -> HookResult:
        """Fire model health check hook."""
        hook_context = HookContext(
            event=HookEvent.MODEL_CALL,
            args={
                "model_id": model_id,
            },
            extra={
                "event_type": "model.health_check",
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
        return await self.hook_bus.fire(hook_context)

    async def fire_fallback(
        self,
        failed_model: str,
        fallback_model: str,
        reason: str,
    ) -> HookResult:
        """Fire model fallback hook."""
        hook_context = HookContext(
            event=HookEvent.MODEL_CALL,
            args={
                "failed_model": failed_model,
                "fallback_model": fallback_model,
                "reason": reason,
            },
            extra={
                "event_type": "model.fallback",
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
        return await self.hook_bus.fire(hook_context)


# Built-in hook implementations


async def default_pre_selection_hook(context: ModelSelectionContext) -> ModelSelectionContext:
    """Default pre-selection hook that can modify the selection context."""
    # Example: Add default fallback chain if not provided
    if not context.fallback_chain and context.requested_model:
        context.fallback_chain = ["claude-sonnet-5", "claude-haiku-5"]
    return context


async def cost_budget_hook(context: ModelSelectionContext) -> ModelSelectionContext:
    """Hook that filters models based on budget."""
    if context.budget is not None:
        # Could filter fallback chain based on budget
        # This is a placeholder for actual budget filtering logic
        pass
    return context


async def capability_filter_hook(context: ModelSelectionContext) -> ModelSelectionContext:
    """Hook that ensures selected model has required capabilities."""
    if context.required_capabilities:
        # Could filter fallback chain to only models with required capabilities
        pass
    return context


async def model_validation_hook(model_id: str) -> dict:
    """Validate a model ID against known models."""
    from zcoder.agent.model_registry import get_model

    record = get_model(model_id)
    if record is None:
        return {"valid": False, "error": f"Unknown model: {model_id}"}

    if record.is_retired():
        return {
            "valid": False,
            "error": f"Model {model_id} is retired",
            "suggested_alternative": "claude-sonnet-5",
        }

    if record.is_deprecated():
        return {
            "valid": True,
            "warning": f"Model {model_id} is deprecated",
            "deprecation_date": record.deprecation_date,
        }

    return {"valid": True}


async def capability_negotiation_hook(model_id: str, required_capabilities: list[str]) -> dict:
    """Negotiate capabilities for a model."""

    results = {}
    for cap in required_capabilities:
        # Check if model supports capability
        # This is a simplified check
        results[cap] = {"supported": True, "native": True}

    return {
        "model_id": model_id,
        "capabilities": results,
        "negotiated": True,
    }


async def model_fallback_hook(failed_model: str, fallback_model: str, reason: str) -> dict:
    """Handle model fallback."""
    return {
        "failed_model": failed_model,
        "fallback_model": fallback_model,
        "reason": reason,
        "timestamp": datetime.utcnow().isoformat(),
    }


# Register built-in hooks with hook bus


def register_model_lifecycle_hooks(hook_bus: HookBus) -> None:
    """Register built-in model lifecycle hooks."""

    hook_bus.register(
        HookEvent.PRE_MODEL_SWITCH,
        lambda ctx: default_pre_selection_hook(ModelSelectionContext(**ctx.args)),
        tier="builtin",
    )

    hook_bus.register(
        HookEvent.MODEL_CALL,
        lambda ctx: capability_negotiation_hook(
            ctx.args["model_id"], ctx.args.get("required_capabilities", [])
        ),
        tier="builtin",
    )

    hook_bus.register(
        HookEvent.MODEL_CALL,
        lambda ctx: model_validation_hook(ctx.args["model_id"]),
        tier="builtin",
    )

    hook_bus.register(
        HookEvent.MODEL_CALL,
        lambda ctx: capability_negotiation_hook(
            ctx.args["model_id"], ctx.args.get("required_capabilities", [])
        ),
        tier="builtin",
    )
