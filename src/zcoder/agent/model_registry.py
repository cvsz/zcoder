"""
model_registry.py — Expanded Model Registry with Full Metadata

Extends the existing MODEL_CATALOG to support all fields required by the
provider-neutral runtime contract (Section 6 of full-master-aee.md).

Each model record supports:
- Provider ID
- Model ID
- Display name
- Model family
- Release date
- Availability
- Lifecycle state
- Context window
- Maximum output tokens
- Input modalities
- Output modalities
- Reasoning support
- Tool calling
- Streaming
- Structured output
- Pricing tiers
- Rate limits
- Regional restrictions
- Data retention policy
- Local hardware requirements
- Quantization
- Deprecation date
- Verification timestamp
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from zcoder.agent.capability_contract import (
    CapabilityMetadata,
    CapabilityRegistry,
    CapabilityStatus,
    CapabilityType,
)


class LifecycleState(Enum):
    """Lifecycle state of a model."""

    ACTIVE = "active"
    DEPRECATED = "deprecated"
    RETIRED = "retired"
    UNKNOWN = "unknown"


@dataclass
class ModelModality:
    """Represents a modality (input/output type) for a model."""

    type: str  # e.g., "text", "image", "audio", "video"
    supported: bool = True


@dataclass
class PricingTier:
    """A pricing tier for model usage."""

    max_input_tokens: int | None = None
    price_per_input_token: float = 0.0
    price_per_output_token: float = 0.0
    label: str | None = None


@dataclass
class ModelRecord:
    """Complete model record with all metadata fields."""

    provider_id: str
    model_id: str
    display_name: str
    model_family: str = ""
    release_date: str | None = None  # ISO format date string
    availability: str = "available"  # "available", "limited", "unavailable"
    lifecycle_state: LifecycleState = LifecycleState.ACTIVE
    context_window: int = 1_000_000  # maximum input tokens
    max_output_tokens: int = 128_000  # maximum output tokens
    input_modalities: list[ModelModality] = field(default_factory=list)
    output_modalities: list[ModelModality] = field(default_factory=list)
    reasoning_support: bool = False
    tool_calling: bool = False
    streaming: bool = False
    structured_output: bool = False
    pricing_tiers: list[PricingTier] = field(default_factory=list)
    rate_limit_per_minute: int | None = None
    rate_limit_per_day: int | None = None
    regional_restrictions: list[str] = field(default_factory=list)  # country codes
    data_retention_policy: str = "unspecified"  # "unspecified", "24h", "30d", "etc."
    local_hardware_requirements: dict[str, Any] = field(default_factory=dict)
    quantization: str | None = None  # e.g., "gguf-q4_k_m", "awq", None for none
    deprecation_date: str | None = None  # ISO format date string
    verification_timestamp: str | None = None  # ISO when model was verified
    notes: str = ""

    def is_available(self) -> bool:
        """Check if the model is available (not retired)."""
        return self.lifecycle_state in (LifecycleState.ACTIVE, LifecycleState.DEPRECATED)

    def is_retired(self) -> bool:
        """Check if the model is retired."""
        return self.lifecycle_state == LifecycleState.RETIRED

    def is_deprecated(self) -> bool:
        """Check if the model is deprecated but still callable."""
        return self.lifecycle_state == LifecycleState.DEPRECATED

    def pricing_for_tokens(self, input_tokens: int, output_tokens: int) -> float | None:
        """Calculate price for given token counts using the best applicable tier."""
        total = 0.0
        for tier in self.pricing_tiers:
            input_cost = 0.0
            output_cost = 0.0
            if tier.max_input_tokens is None or input_tokens <= tier.max_input_tokens:
                input_cost = input_tokens * tier.price_per_input_token
            if tier.max_input_tokens is None or output_tokens <= tier.max_input_tokens:
                output_cost = output_tokens * tier.price_per_output_token
            total += input_cost + output_cost
        return total if total > 0 else None

    def __str__(self) -> str:
        return f"{self.display_name} ({self.model_id})"

    def __repr__(self) -> str:
        return (
            f"ModelRecord(provider_id='{self.provider_id}', model_id='{self.model_id}', "
            f"display_name='{self.display_name}', family='{self.model_family}', "
            f"lifecycle={self.lifecycle_state.value}, context={self.context_window})"
        )


# ── Expanded Model Catalog ──────────────────────────────────────────────

# This replaces/extends the existing MODEL_CATALOG in src/zcoder/agent/models/registry.py
# with full metadata per the document contract.

MODEL_CATALOG: dict[str, ModelRecord] = {}


def register_model(
    provider_id: str,
    model_id: str,
    display_name: str,
    model_family: str = "",
    release_date: str | None = None,
    availability: str = "available",
    lifecycle_state: LifecycleState = LifecycleState.ACTIVE,
    context_window: int = 1_000_000,
    max_output_tokens: int = 128_000,
    input_modalities: list[ModelModality] | None = None,
    output_modalities: list[ModelModality] | None = None,
    reasoning_support: bool = False,
    tool_calling: bool = False,
    streaming: bool = False,
    structured_output: bool = False,
    pricing_tiers: list[PricingTier] | None = None,
    rate_limit_per_minute: int | None = None,
    rate_limit_per_day: int | None = None,
    regional_restrictions: list[str] | None = None,
    data_retention_policy: str = "unspecified",
    local_hardware_requirements: dict[str, Any] | None = None,
    quantization: str | None = None,
    deprecation_date: str | None = None,
    verification_timestamp: str | None = None,
    notes: str = "",
) -> None:
    """Register a model in the expanded catalog with full metadata."""
    from zcoder.agent.capability_contract import (
        CapabilityRegistry,
        CapabilityType,
    )

    record = ModelRecord(
        provider_id=provider_id,
        model_id=model_id,
        display_name=display_name,
        model_family=model_family,
        release_date=release_date,
        availability=availability,
        lifecycle_state=lifecycle_state,
        context_window=context_window,
        max_output_tokens=max_output_tokens,
        input_modalities=input_modalities or [],
        output_modalities=output_modalities or [],
        reasoning_support=reasoning_support,
        tool_calling=tool_calling,
        streaming=streaming,
        structured_output=structured_output,
        pricing_tiers=pricing_tiers or [],
        rate_limit_per_minute=rate_limit_per_minute,
        rate_limit_per_day=rate_limit_per_day,
        regional_restrictions=regional_restrictions or [],
        data_retention_policy=data_retention_policy,
        local_hardware_requirements=local_hardware_requirements or {},
        quantization=quantization,
        deprecation_date=deprecation_date,
        verification_timestamp=verification_timestamp,
        notes=notes,
    )

    MODEL_CATALOG[model_id] = record

    # Also register capabilities in the capability registry
    # Determine which capabilities this model supports based on metadata
    capabilities: dict[CapabilityType, CapabilityMetadata] = {}

    if reasoning_support:
        capabilities[CapabilityType.reasoning] = CapabilityMetadata(
            status=CapabilityStatus.NATIVE,  # Will be overridden by provider if native
            confidence=0.8,
        )
    if tool_calling:
        capabilities[CapabilityType.tool_calling] = CapabilityMetadata(
            status=CapabilityStatus.NATIVE,
            confidence=0.8,
        )
    if streaming:
        capabilities[CapabilityType.streaming] = CapabilityMetadata(
            status=CapabilityStatus.NATIVE,
            confidence=0.8,
        )
    if structured_output:
        capabilities[CapabilityType.structured_output] = CapabilityMetadata(
            status=CapabilityStatus.NATIVE,
            confidence=0.8,
        )

    for cap_type, metadata in capabilities.items():
        CapabilityRegistry.register(model_id, cap_type, metadata)


def get_model(model_id: str) -> ModelRecord | None:
    """Get a model record by model ID."""
    return MODEL_CATALOG.get(model_id)


def list_models(
    provider_id: str | None = None,
    lifecycle_state: LifecycleState | None = None,
    available_only: bool = True,
) -> list[ModelRecord]:
    """List models, optionally filtered by provider, lifecycle state, or availability."""
    models = list(MODEL_CATALOG.values())

    if provider_id is not None:
        models = [m for m in models if m.provider_id == provider_id]

    if lifecycle_state is not None:
        models = [m for m in models if m.lifecycle_state == lifecycle_state]

    if available_only:
        models = [m for m in models if m.is_available()]

    return sorted(models, key=lambda m: m.display_name)


def get_capability(
    model_id: str,
    capability: CapabilityType,
) -> CapabilityMetadata | None:
    """Get capability metadata for a model."""
    from zcoder.agent.capability_contract import CapabilityRegistry

    return CapabilityRegistry.get(model_id, capability)


# ── Convenience functions ────────────────────────────────────────────────


def has_capability(
    model_id: str,
    capability: CapabilityType,
    status: CapabilityStatus = CapabilityStatus.NATIVE,
) -> bool:
    """Check if a model has a specific capability with a given status."""
    from zcoder.agent.capability_contract import CapabilityRegistry

    return CapabilityRegistry.has(model_id, capability, status)


def model_available(model_id: str) -> bool:
    """Check if a model is available (not retired)."""
    record = get_model(model_id)
    if record is None:
        return False
    return record.is_available()


def model_retired(model_id: str) -> bool:
    """Check if a model is retired."""
    record = get_model(model_id)
    if record is None:
        return False
    return record.is_retired()


def model_deprecated(model_id: str) -> bool:
    """Check if a model is deprecated."""
    record = get_model(model_id)
    if record is None:
        return False
    return record.is_deprecated()


__all__ = [
    "ModelRecord",
    "ModelModality",
    "PricingTier",
    "LifecycleState",
    "MODEL_CATALOG",
    "register_model",
    "get_model",
    "list_models",
    "get_capability",
    "has_capability",
    "model_available",
    "model_retired",
    "model_deprecated",
    "CapabilityStatus",
    "CapabilityType",
    "CapabilityMetadata",
    "CapabilityRegistry",
]

# Initialize the Claude model catalog with full ModelRecord metadata
# This must be called at module level to populate MODEL_CATALOG


def _init_claude_catalog() -> None:
    """Initialize the Claude model catalog with full ModelRecord metadata."""

    def _tier(price_in: float, price_out: float, max_input: int | None = None) -> PricingTier:
        return PricingTier(
            max_input_tokens=max_input,
            price_per_input_token=price_in,
            price_per_output_token=price_out,
        )

    def _modality(mtype: str) -> ModelModality:
        return ModelModality(type=mtype)

    # Register claude-fable-5-2
    register_model(
        provider_id="anthropic",
        model_id="claude-fable-5-2",
        display_name="Claude Fable 5.2",
        model_family="fable",
        release_date="2026-11-09",
        availability="available",
        lifecycle_state=LifecycleState.ACTIVE,
        context_window=1_000_000,
        max_output_tokens=128_000,
        input_modalities=[_modality("text")],
        output_modalities=[_modality("text")],
        reasoning_support=True,
        tool_calling=True,
        streaming=True,
        structured_output=True,
        pricing_tiers=[
            _tier(8.0, 40.0, max_input=200_000),
        ],
        rate_limit_per_minute=40_000,
        rate_limit_per_day=1_200_000,
        regional_restrictions=["US", "EU"],
        data_retention_policy="30d",
        local_hardware_requirements={"min_ram_gb": 16, "gpu_recommended": True},
    )

    # Register claude-mythos-5-2
    register_model(
        provider_id="anthropic",
        model_id="claude-mythos-5-2",
        display_name="Claude Mythos 5.2",
        model_family="mythos",
        release_date="2026-11-09",
        availability="available",
        lifecycle_state=LifecycleState.ACTIVE,
        context_window=1_000_000,
        max_output_tokens=128_000,
        input_modalities=[_modality("text")],
        output_modalities=[_modality("text")],
        reasoning_support=True,
        tool_calling=True,
        streaming=True,
        structured_output=True,
        pricing_tiers=[
            _tier(8.0, 40.0, max_input=200_000),
        ],
        rate_limit_per_minute=40_000,
        rate_limit_per_day=1_200_000,
        regional_restrictions=["US", "EU"],
        data_retention_policy="30d",
        local_hardware_requirements={"min_ram_gb": 16, "gpu_recommended": True},
    )

    # Register claude-fable-5-1
    register_model(
        provider_id="anthropic",
        model_id="claude-fable-5-1",
        display_name="Claude Fable 5.1",
        model_family="fable",
        release_date="2026-10-01",
        availability="available",
        lifecycle_state=LifecycleState.ACTIVE,
        context_window=1_000_000,
        max_output_tokens=128_000,
        input_modalities=[_modality("text")],
        output_modalities=[_modality("text")],
        reasoning_support=True,
        tool_calling=True,
        streaming=True,
        structured_output=True,
        pricing_tiers=[
            _tier(10.0, 50.0, max_input=100_000),
            _tier(8.0, 40.0, max_input=200_000),
        ],
        rate_limit_per_minute=35_000,
        rate_limit_per_day=1_000_000,
        regional_restrictions=["US", "EU"],
        data_retention_policy="30d",
        local_hardware_requirements={"min_ram_gb": 16, "gpu_recommended": True},
        deprecation_date=None,
        verification_timestamp="2026-10-26T12:00:00Z",
        notes="Current model catalog entry (checked 2026-10-26). Adaptive thinking is always on. "
        "Fable 5.1 replaces Fable 5 in the current lineup; API support is optional and this metadata "
        "does not enable network inference.",
    )

    # Register claude-opus-5-5
    register_model(
        provider_id="anthropic",
        model_id="claude-opus-5-5",
        display_name="Claude Opus 5.5",
        model_family="opus",
        release_date="2026-10-01",
        availability="available",
        lifecycle_state=LifecycleState.ACTIVE,
        context_window=1_000_000,
        max_output_tokens=128_000,
        input_modalities=[_modality("text")],
        output_modalities=[_modality("text")],
        reasoning_support=True,
        tool_calling=True,
        streaming=True,
        structured_output=True,
        pricing_tiers=[
            _tier(4.0, 20.0, max_input=100_000),
            _tier(3.0, 15.0, max_input=200_000),
        ],
        rate_limit_per_minute=10_000,
        rate_limit_per_day=500_000,
        regional_restrictions=["US", "EU"],
        data_retention_policy="30d",
        local_hardware_requirements={"min_ram_gb": 32, "gpu_required": True},
        deprecation_date=None,
        verification_timestamp="2026-10-26T12:00:00Z",
        notes="Current model catalog entry (checked 2026-10-26). Adaptive thinking is always on. "
        "API support is optional and this metadata does not enable network inference.",
    )

    # Register claude-sonnet-5-5
    register_model(
        provider_id="anthropic",
        model_id="claude-sonnet-5-5",
        display_name="Claude Sonnet 5.5",
        model_family="sonnet",
        release_date="2026-10-01",
        availability="available",
        lifecycle_state=LifecycleState.ACTIVE,
        context_window=1_000_000,
        max_output_tokens=128_000,
        input_modalities=[_modality("text")],
        output_modalities=[_modality("text")],
        reasoning_support=True,
        tool_calling=True,
        streaming=True,
        structured_output=True,
        pricing_tiers=[
            _tier(2.0, 10.0, max_input=100_000),
            _tier(1.5, 8.0, max_input=200_000),
        ],
        rate_limit_per_minute=30_000,
        rate_limit_per_day=2_000_000,
        regional_restrictions=["US", "EU"],
        data_retention_policy="30d",
        local_hardware_requirements={"min_ram_gb": 16, "gpu_recommended": True},
        deprecation_date=None,
        verification_timestamp="2026-10-26T12:00:00Z",
        notes="Current model catalog entry (checked 2026-10-26). API support is optional and this "
        "metadata does not enable network inference.",
    )

    # Register claude-haiku-5-5
    register_model(
        provider_id="anthropic",
        model_id="claude-haiku-5-5",
        display_name="Claude Haiku 5.5",
        model_family="haiku",
        release_date="2026-10-01",
        availability="available",
        lifecycle_state=LifecycleState.ACTIVE,
        context_window=1_000_000,
        max_output_tokens=128_000,
        input_modalities=[_modality("text")],
        output_modalities=[_modality("text")],
        reasoning_support=True,
        tool_calling=True,
        streaming=True,
        structured_output=True,
        pricing_tiers=[
            _tier(0.1, 0.5, max_input=100_000),
            _tier(0.08, 0.4, max_input=200_000),
        ],
        rate_limit_per_minute=30_000,
        rate_limit_per_day=2_000_000,
        regional_restrictions=["US", "EU"],
        data_retention_policy="30d",
        local_hardware_requirements={"min_ram_gb": 8, "gpu_recommended": False},
        deprecation_date=None,
        verification_timestamp="2026-10-26T12:00:00Z",
        notes="Current model catalog entry (checked 2026-10-26).",
    )

    # Register legacy/hardware-optimized models for Ollama
    register_model(
        provider_id="ollama",
        model_id="llama3.2:3b",
        display_name="Llama 3.2 3B",
        model_family="llama",
        release_date="2024-09-01",
        availability="available",
        lifecycle_state=LifecycleState.ACTIVE,
        context_window=128_000,
        max_output_tokens=8192,
        input_modalities=[_modality("text")],
        output_modalities=[_modality("text")],
        reasoning_support=False,
        tool_calling=False,
        streaming=True,
        structured_output=False,
        pricing_tiers=[],
        rate_limit_per_minute=None,
        rate_limit_per_day=None,
        regional_restrictions=[],
        data_retention_policy="unspecified",
        local_hardware_requirements={"min_ram_gb": 8, "gpu_vram_gb": 6, "quantization": "q4_k_m"},
        deprecation_date=None,
        verification_timestamp="2026-10-26T12:00:00Z",
        notes="Local Ollama model, zero-cost route.",
    )

    register_model(
        provider_id="ollama",
        model_id="llama3.2:13b",
        display_name="Llama 3.2 13B",
        model_family="llama",
        release_date="2024-09-01",
        availability="available",
        lifecycle_state=LifecycleState.ACTIVE,
        context_window=128_000,
        max_output_tokens=8192,
        input_modalities=[_modality("text")],
        output_modalities=[_modality("text")],
        reasoning_support=False,
        tool_calling=False,
        streaming=True,
        structured_output=False,
        pricing_tiers=[],
        rate_limit_per_minute=None,
        rate_limit_per_day=None,
        regional_restrictions=[],
        data_retention_policy="unspecified",
        local_hardware_requirements={"min_ram_gb": 16, "gpu_vram_gb": 12, "quantization": "q4_k_m"},
        deprecation_date=None,
        verification_timestamp="2026-10-26T12:00:00Z",
        notes="Local Ollama model, zero-cost route.",
    )

    # Register deprecated models
    register_model(
        provider_id="anthropic",
        model_id="claude-instant-1.2",
        display_name="Claude Instant 1.2",
        model_family="instant",
        release_date="2024-03-01",
        availability="limited",
        lifecycle_state=LifecycleState.DEPRECATED,
        context_window=100_000,
        max_output_tokens=8192,
        input_modalities=[_modality("text")],
        output_modalities=[_modality("text")],
        reasoning_support=False,
        tool_calling=False,
        streaming=True,
        structured_output=False,
        pricing_tiers=[
            _tier(1.0, 2.0),
        ],
        rate_limit_per_minute=15_000,
        rate_limit_per_day=500_000,
        regional_restrictions=["US", "EU"],
        data_retention_policy="30d",
        local_hardware_requirements={"min_ram_gb": 8, "gpu_recommended": False},
        deprecation_date="2026-12-01",
        verification_timestamp="2026-03-15T12:00:00Z",
        notes="Deprecated but still callable. Retirement scheduled 2026-12-01.",
    )

    # Register claude-3-opus-20240229 as retired
    register_model(
        provider_id="anthropic",
        model_id="claude-3-opus-20240229",
        display_name="Claude 3 Opus (2024)",
        model_family="opus",
        release_date="2024-02-29",
        availability="limited",
        lifecycle_state=LifecycleState.RETIRED,
        context_window=200_000,
        max_output_tokens=4096,
        input_modalities=[_modality("text")],
        output_modalities=[_modality("text")],
        reasoning_support=True,
        tool_calling=True,
        streaming=True,
        structured_output=True,
        pricing_tiers=[
            _tier(15.0, 75.0),
        ],
        rate_limit_per_minute=5_000,
        rate_limit_per_day=100_000,
        regional_restrictions=["US", "EU"],
        data_retention_policy="30d",
        local_hardware_requirements={"min_ram_gb": 64, "gpu_required": True},
        deprecation_date=None,
        verification_timestamp="2026-03-15T12:00:00Z",
        notes="Retired model. See claude-3-opus-20241219 for successor.",
    )


_init_claude_catalog()
