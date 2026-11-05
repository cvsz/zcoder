"""
capability_contract.py — Normalized Capability Contract for ZCoder Provider-Neutral Runtime

Defines the canonical capability contract that all providers must adhere to.
A provider is NOT considered fully supported merely because an HTTP request succeeds.
Capabilities have evidence and confidence metadata.

Contract versions:
  - v1.0: Initial release with 21 capability types
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class CapabilityStatus(Enum):
    """Status of a capability for a given provider/model."""

    NATIVE = "native"  # Native support, no adapter needed
    ADAPTER = "adapter"  # Adapter-translated support
    EXPERIMENTAL = "experimental"  # Experimental support
    UNSUPPORTED = "unsupported"  # Known not supported
    UNKNOWN = "unknown"  # Unknown if supported


@dataclass
class CapabilityMetadata:
    """Metadata for a single capability."""

    status: CapabilityStatus = CapabilityStatus.UNKNOWN
    evidence_level: str = "E0_CODE_EXISTS"  # E0-E5 per document testing levels
    confidence: float = 0.0  # 0.0 = no confidence, 1.0 = full confidence
    last_verified: str | None = None  # ISO timestamp string
    adapter_name: str | None = None  # Name of adapter if ADAPTER status


# ── 21 Capability Types per Document Contract ────────────────────────────


class CapabilityType(Enum):
    """The 21 capability types from the provider-neutral runtime contract."""

    # Text generation
    text_generation = auto()

    # Code generation
    code_generation = auto()

    # Reasoning
    reasoning = auto()

    # Streaming
    streaming = auto()

    # Tool calling
    tool_calling = auto()

    # Structured output
    structured_output = auto()

    # Image input
    image_input = auto()

    # Image generation
    image_generation = auto()

    # Audio input
    audio_input = auto()

    # Audio generation
    audio_generation = auto()

    # Speech to text
    speech_to_text = auto()

    # Text to speech
    text_to_speech = auto()

    # Realtime audio
    realtime_audio = auto()

    # Video input
    video_input = auto()

    # Video generation
    video_generation = auto()

    # Video editing
    video_editing = auto()

    # Embeddings
    embeddings = auto()

    # Reranking
    reranking = auto()

    # Computer use
    computer_use = auto()

    # Long context
    long_context = auto()


# ── Global capability registry ──────────────────────────────────────────


class CapabilityRegistry:
    """Registry tracking capability status per provider/model."""

    _registry: dict[str, dict[CapabilityType, CapabilityMetadata]] = {}

    @classmethod
    def register(
        cls,
        provider_or_model: str,
        capability: CapabilityType,
        metadata: CapabilityMetadata,
    ) -> None:
        """Register a capability status for a provider or model."""
        if provider_or_model not in cls._registry:
            cls._registry[provider_or_model] = {}
        cls._registry[provider_or_model][capability] = metadata

    @classmethod
    def get(
        cls,
        provider_or_model: str,
        capability: CapabilityType,
    ) -> CapabilityMetadata | None:
        """Get capability status for a provider or model."""
        provider_registry = cls._registry.get(provider_or_model)
        if provider_registry is None:
            return None
        return provider_registry.get(capability)

    @classmethod
    def has(
        cls,
        provider_or_model: str,
        capability: CapabilityType,
        status: CapabilityStatus = CapabilityStatus.NATIVE,
    ) -> bool:
        """Check if a capability has a specific status."""
        metadata = cls.get(provider_or_model, capability)
        if metadata is None:
            return False
        return metadata.status == status

    @classmethod
    def all_capabilities(
        cls,
        provider_or_model: str,
    ) -> dict[CapabilityType, CapabilityMetadata]:
        """Get all capabilities for a provider or model."""
        return cls._registry.get(provider_or_model, {}).copy()

    @classmethod
    def providers_with_capability(
        cls,
        capability: CapabilityType,
        status: CapabilityStatus = CapabilityStatus.NATIVE,
    ) -> list[str]:
        """Get all providers where a capability has a specific status."""
        providers = []
        for provider, capabilities in cls._registry.items():
            if capabilities.get(capability, CapabilityMetadata()).status == status:
                providers.append(provider)
        return providers


# ── Convenience functions ────────────────────────────────────────────────


def native(provider_or_model: str, capability: CapabilityType) -> bool:
    """Check if a capability is natively supported."""
    return CapabilityRegistry.has(provider_or_model, capability, CapabilityStatus.NATIVE)


def adapter_supported(provider_or_model: str, capability: CapabilityType) -> bool:
    """Check if a capability is supported via adapter."""
    return CapabilityRegistry.has(provider_or_model, capability, CapabilityStatus.ADAPTER)


def experimental(provider_or_model: str, capability: CapabilityType) -> bool:
    """Check if a capability is experimental."""
    return CapabilityRegistry.has(provider_or_model, capability, CapabilityStatus.EXPERIMENTAL)


def unsupported(provider_or_model: str, capability: CapabilityType) -> bool:
    """Check if a capability is known to be unsupported."""
    return CapabilityRegistry.has(provider_or_model, capability, CapabilityStatus.UNSUPPORTED)


def unknown(provider_or_model: str, capability: CapabilityType) -> bool:
    """Check if capability status is unknown."""
    return CapabilityRegistry.has(provider_or_model, capability, CapabilityStatus.UNKNOWN)


# ── Pre-registered capabilities (populate at startup) ──────────────────

# These should be populated during provider initialization.
# Example pattern:
#
# from zcoder.agent.capability_contract import CapabilityType, CapabilityMetadata, CapabilityStatus, native
# from zcoder.agent.providers import SomeProvider
#
# CapabilityRegistry.register(
#     "openai",
#     CapabilityType.text_generation,
#     CapabilityMetadata(
#         status=CapabilityStatus.NATIVE,
#         evidence_level="E4_LIVE_EXTERNAL_TESTED",
#         confidence=0.98,
#         last_verified="2026-10-20T12:00:00Z",
#     ),
# )
#
# Later, when checking:
#
# if native("openai", CapabilityType.text_generation):
#     # proceed with text generation


__all__ = [
    "CapabilityType",
    "CapabilityStatus",
    "CapabilityMetadata",
    "CapabilityRegistry",
    "native",
    "adapter_supported",
    "experimental",
    "unsupported",
    "unknown",
]
