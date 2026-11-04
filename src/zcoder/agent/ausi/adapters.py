"""
ausi/adapters.py — Provider-agnostic adapter interface for AUSI.

Defines the consistent interface that all provider adapters must expose:
  — discover()
  — health_check()
  — list_models()
  — execute()
  — execute_background()
  — get_task_status()
  — cancel_task()
  — get_capabilities()

Each adapter wraps a specific AI coding environment (OpenCode, Codex, Claude Code,
Gemini CLI, Kilo, etc.) and translates between the AUSI internal contract and
the provider's native API/CLI.
"""

from __future__ import annotations

import abc
import re
from typing import Any


class ProviderCapabilities:
    """Capabilities metadata for a provider."""

    def __init__(
        self,
        *,
        supports_discover: bool = True,
        supports_health_check: bool = True,
        supports_list_models: bool = True,
        supports_execute: bool = True,
        supports_execute_background: bool = False,
        supports_get_task_status: bool = False,
        supports_cancel_task: bool = False,
        supports_get_capabilities: bool = True,
    ):
        self.supports_discover = supports_discover
        self.supports_health_check = supports_health_check
        self.supports_list_models = supports_list_models
        self.supports_execute = supports_execute
        self.supports_execute_background = supports_execute_background
        self.supports_get_task_status = supports_get_task_status
        self.supports_cancel_task = supports_cancel_task
        self.supports_get_capabilities = supports_get_capabilities


class ProviderStatus:
    """Status returned by health_check()."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class AdapterResult:
    """Result of an adapter execution."""

    def __init__(
        self,
        success: bool,
        text: str = "",
        model: str = "",
        provider: str = "",
        task_id: str = "",
        error: str = "",
        raw: dict | None = None,
    ):
        self.success = success
        self.text = text
        self.model = model
        self.provider = provider
        self.task_id = task_id
        self.error = error
        self.raw = raw

    def __bool__(self) -> bool:
        return self.success

    def __str__(self) -> str:
        return self.text or "(no response)"

    def __repr__(self) -> str:
        return f"AdapterResult(success={self.success}, model={self.model}, provider={self.provider})"


class BaseProviderAdapter(abc.ABC):
    """Abstract base class for all AUSI provider adapters.

    Subclasses must implement the core operations defined in the AUSI interface.
    The abstract methods raise NotImplementedError if not supported.
    """

    def __init__(self, name: str, provider: str, **kwargs):
        self.name = name
        self.provider = provider  # e.g. "opencode", "codex", "gemini-cli", "kilo"
        self.capabilities = ProviderCapabilities()
        self._last_health_check: float = 0
        self._status = ProviderStatus.UNKNOWN

    @abc.abstractmethod
    def discover(self) -> list[dict[str, Any]]:
        """Discover available models and their capabilities.

        Returns a list of model dicts with at least:
        - "id": model identifier
        - "name": display name
        - "provider": provider name
        - Optional: "context_window", "price_in", "price_out", "tier"
        """
        raise NotImplementedError(f"{self.name} adapter does not implement discover().")

    @abc.abstractmethod
    def health_check(self) -> dict[str, str]:
        """Check provider health/availability.

        Returns a dict with at least:
        - "status": one of ProviderStatus.* values
        - Optional: "latency_ms", "error", "details"
        """
        raise NotImplementedError(f"{self.name} adapter does not implement health_check().")

    @abc.abstractmethod
    def list_models(self) -> list[dict[str, Any]]:
        """List available models from the provider.

        Returns model catalog similar to discover().
        """
        raise NotImplementedError(f"{self.name} adapter does not implement list_models().")

    @abc.abstractmethod
    def execute(self, prompt: str, model: str | None = None, **options) -> AdapterResult:
        """Execute a task on the provider.

        Args:
            prompt: The prompt/task to execute
            model: Model identifier (optional, may use default)
            **options: Provider-specific options (temperature, max_tokens, etc.)

        Returns:
            AdapterResult with success flag and response text
        """
        raise NotImplementedError(f"{self.name} adapter does not implement execute().")

    @abc.abstractmethod
    def execute_background(
        self, prompt: str, model: str | None = None, **options
    ) -> tuple[str, dict[str, Any]]:
        """Execute a task asynchronously.

        Args:
            prompt: The prompt/task to execute
            model: Model identifier (optional)
            **options: Provider-specific options

        Returns:
            Tuple of (task_id, metadata) where metadata may contain
            initial status, estimated completion, etc.
        """
        raise NotImplementedError(f"{self.name} adapter does not implement execute_background().")

    @abc.abstractmethod
    def get_task_status(self, task_id: str) -> AdapterResult:
        """Check status of a background task.

        Args:
            task_id: The task identifier from execute_background()

        Returns:
            AdapterResult with current status and optionally partial results
        """
        raise NotImplementedError(f"{self.name} adapter does not implement get_task_status().")

    @abc.abstractmethod
    def cancel_task(self, task_id: str) -> bool:
        """Cancel a background task.

        Args:
            task_id: The task identifier from execute_background()

        Returns:
            True if cancellation was successful, False otherwise
        """
        raise NotImplementedError(f"{self.name} adapter does not implement cancel_task().")

    def get_capabilities(self) -> ProviderCapabilities:
        """Return the capabilities metadata for this adapter.

        By default returns a base ProviderCapabilities. Subclasses may override
        to report which AUSI operations are natively supported.
        """
        return self.capabilities

    def _validate_model(self, model: str) -> str:
        """Validate and normalize a model identifier for the provider."""
        if not model:
            return self._get_default_model()
        return model

    @abc.abstractmethod
    def _get_default_model(self) -> str:
        """Return the default model for this provider."""
        pass

    def _strip_credentials(self, prompt: str) -> str:
        """Redact any potential secrets or credentials from a prompt before execution."""
        validated = prompt
        # Remove anything that looks like an API key or token
        patterns = [
            r"sk-[a-zA-Z0-9]{20,}",  # OpenAI-style keys
            r"bearer [a-zA-Z0-9\-_]+",  # Bearer tokens
            r"api_key\s*=\s*['\"][^'\"]+['\"]",  # API key assignments
        ]
        for pattern in patterns:
            validated = re.sub(pattern, "[REDACTED]", validated)
        return validated
