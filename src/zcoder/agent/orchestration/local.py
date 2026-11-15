"""
local.py — Local (offline stub) provider adapter (Phase 2).
"""

from __future__ import annotations

from typing import Any

from .adapter import ProviderAdapter, ProviderResult


class LocalAdapter(ProviderAdapter):
    """Adapter for local / offline inference. Does not call any network."""

    @classmethod
    def provider_id(cls) -> str:
        return "local"

    def build_payload(
        self,
        model: str,
        messages: list[dict[str, Any]],
        system: str | None,
        max_tokens: int,
        sampling: dict[str, Any],
    ) -> dict[str, Any]:
        return {}

    def parse_response(self, data: dict[str, Any]) -> str:
        return data.get("text", "") or "[local mode] No upstream call — local stub response."

    def endpoint_for(self, base_url: str, model: str) -> str:
        return ""

    def headers_for(self, api_key: str) -> dict[str, str]:
        return {}
