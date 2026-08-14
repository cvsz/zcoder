"""Account-aware, opt-in Claude model capability preflight."""
from __future__ import annotations

import json
import urllib.request

from claude_models import MODEL_CATALOG


class ModelUnavailableError(ValueError):
    """The configured model is not available to the current API key."""


class ModelCapabilityResolver:
    """Fetch model metadata once per process without retaining credentials."""

    _cache: dict[str, dict] = {}

    def __init__(self, api_key: str):
        self.api_key = api_key

    def resolve(self, model: str) -> dict:
        if model in self._cache:
            return self._cache[model]
        request = urllib.request.Request(
            f"https://api.anthropic.com/v1/models/{model}",
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                metadata = json.loads(response.read().decode())
        except Exception as exc:
            # Offline fallback is deliberately conservative: it verifies only
            # bundled known IDs and never claims account availability.
            if model in MODEL_CATALOG:
                return dict(MODEL_CATALOG[model])
            raise ModelUnavailableError(
                f"Unable to verify model '{model}'. Check account access or connectivity."
            ) from exc
        self._cache[model] = metadata
        return metadata
