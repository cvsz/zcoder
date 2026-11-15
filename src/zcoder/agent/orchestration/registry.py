"""
registry.py — Adapter registry (Phase 2).

Registers and looks up :class:`ProviderAdapter` instances by provider id.
"""

from __future__ import annotations

from .adapter import ProviderAdapter


class AdapterRegistry:
    """Maps provider id -> ProviderAdapter instance."""

    def __init__(self) -> None:
        self._adapters: dict[str, ProviderAdapter] = {}

    def register(self, provider: str, adapter: ProviderAdapter) -> None:
        """Register an adapter for *provider*."""
        self._adapters[provider] = adapter

    def get(self, provider: str) -> ProviderAdapter:
        """Return the adapter for *provider*, or raise ``KeyError``."""
        if provider not in self._adapters:
            raise KeyError(f"No adapter registered for provider '{provider}'")
        return self._adapters[provider]

    def list(self) -> list[str]:
        """Return the list of registered provider ids."""
        return sorted(self._adapters.keys())
