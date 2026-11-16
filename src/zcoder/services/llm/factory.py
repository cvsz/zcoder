"""
zcoder.services.llm.factory — LLM provider factory.

Resolves provider adapters from configuration. Follows Explicit > Implicit
at Package Boundaries (Section 4.7): the factory explicitly maps config to
concrete adapter instances, never using hidden defaults inside run().

Registration as an effect: plugins call register_provider() at load time,
and consumers access providers through the registry (Registrations Are
Effects, Section 4.2).
"""

from __future__ import annotations

from typing import Any

from zcoder.services.llm.anthropic_adapter import AnthropicAdapter
from zcoder.services.llm.deepseek_adapter import DeepSeekAdapter
from zcoder.services.llm.definition import LLMProvider
from zcoder.services.llm.gemini_adapter import GeminiAdapter
from zcoder.services.llm.ollama_adapter import OllamaAdapter
from zcoder.services.llm.openai_adapter import OpenAIAdapter


class ProviderRegistry:
    """Registry of LLM provider adapters keyed by provider name."""

    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}
        self._factories: dict[str, Any] = {}

    def register_factory(self, name: str, factory: Any) -> None:
        """Register a provider factory callable under *name*.

        This is the registration effect: plugins call this at load time.
        """
        self._factories[name] = factory

    def register_instance(self, name: str, instance: LLMProvider) -> None:
        """Register a pre-built provider instance under *name*."""
        self._providers[name] = instance

    def get(self, name: str) -> LLMProvider:
        """Get a provider by name, building it lazily if a factory is registered."""
        if name in self._providers:
            return self._providers[name]
        if name in self._factories:
            instance = self._factories[name]()
            self._providers[name] = instance
            return instance
        raise KeyError(f"No LLM provider registered for '{name}'")

    def list_providers(self) -> list[str]:
        """List all registered provider names."""
        return sorted(set(self._providers) | set(self._factories))


# Default registry — plugins and consumers share this instance.
registry = ProviderRegistry()


def register_provider(name: str, instance: LLMProvider) -> None:
    """Register a provider instance as an effect.

    Call this from plugin bootstrap code (Registrations Are Effects pattern).
    """
    registry.register_instance(name, instance)


def build_deepseek(api_key: str | None = None, base_url: str | None = None) -> DeepSeekAdapter:
    """Build a DeepSeekAdapter instance."""
    return DeepSeekAdapter(api_key=api_key, base_url=base_url)


def build_openai(api_key: str | None = None, base_url: str | None = None) -> OpenAIAdapter:
    """Build an OpenAIAdapter instance."""
    return OpenAIAdapter(api_key=api_key, base_url=base_url)


def build_anthropic(api_key: str | None = None, base_url: str | None = None) -> AnthropicAdapter:
    """Build an AnthropicAdapter instance."""
    return AnthropicAdapter(api_key=api_key, base_url=base_url)


def build_gemini(api_key: str | None = None, base_url: str | None = None) -> GeminiAdapter:
    """Build a GeminiAdapter instance."""
    return GeminiAdapter(api_key=api_key, base_url=base_url)


def build_ollama(api_key: str | None = None, base_url: str | None = None) -> OllamaAdapter:
    """Build an OllamaAdapter instance."""
    return OllamaAdapter(api_key=api_key, base_url=base_url)


def register_default_providers() -> None:
    """Register default provider factories (explicit registration effect)."""
    registry.register_factory("deepseek", build_deepseek)
    registry.register_factory("openai", build_openai)
    registry.register_factory("anthropic", build_anthropic)
    registry.register_factory("gemini", build_gemini)
    registry.register_factory("ollama", build_ollama)
