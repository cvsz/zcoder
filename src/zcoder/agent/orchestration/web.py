"""
web.py — Web / Search / Fetch Capability Seam (Phase 7 of Big Upgrade).

WebRuntime with search/fetch providers, searchBilling rules (auto/account/api-key),
web_search tool (max 10 queries per request, rate-limited), web_fetch tool
(HTML→markdown via turndown, 200K cap).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any


class SearchBilling(str):
    AUTO = "auto"
    ACCOUNT = "account"
    API_KEY = "api-key"


@dataclass
class SearchProvider:
    name: str
    search: Any  # callable(query, ...) -> list[dict]


@dataclass
class FetchProvider:
    name: str
    fetch: Any  # callable(url, ...) -> dict | str


class SearchRateLimiter:
    """Simple token-bucket rate limiter per provider."""

    def __init__(self, max_calls: int, window_seconds: float) -> None:
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self._tokens = float(max_calls)
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            self._last = now
            self._tokens = min(self.max_calls, self._tokens + elapsed * (self.max_calls / self.window_seconds))
            if self._tokens < 1.0:
                wait = (1.0 - self._tokens) / (self.max_calls / self.window_seconds)
                await asyncio.sleep(wait)
                self._tokens = 0.0
            else:
                self._tokens -= 1.0


class WebRuntime:
    """Web/search/fetch capability seam."""

    def __init__(self) -> None:
        self._search_providers: dict[str, SearchProvider] = {}
        self._fetch_providers: dict[str, FetchProvider] = {}
        self._search_limiters: dict[str, SearchRateLimiter] = {}
        self.billing_mode: str = SearchBilling.AUTO

    def register_search_provider(self, name: str, provider: SearchProvider, max_calls_per_min: int = 60) -> None:
        """Register a search provider."""
        self._search_providers[name] = provider
        self._search_limiters[name] = SearchRateLimiter(max_calls=max_calls_per_min, window_seconds=60.0)

    def register_fetch_provider(self, name: str, provider: FetchProvider) -> None:
        """Register a fetch provider."""
        self._fetch_providers[name] = provider

    def list_providers(self) -> dict[str, list[str]]:
        """Return registered provider names."""
        return {
            "search": sorted(self._search_providers.keys()),
            "fetch": sorted(self._fetch_providers.keys()),
        }

    def search_ready(self) -> bool:
        return len(self._search_providers) > 0

    def fetch_ready(self) -> bool:
        return len(self._fetch_providers) > 0

    async def search(self, query: str, provider: str | None = None, **kwargs: Any) -> list[dict[str, Any]]:
        """Search through a registered search provider."""
        providers = self._search_providers
        if not providers:
            raise RuntimeError("no search provider registered")
        name = provider or next(iter(providers))
        if name not in providers:
            raise ValueError(f"unknown search provider: {name}")
        await self._search_limiters[name].acquire()
        prov = providers[name]
        if asyncio.iscoroutinefunction(prov.search):
            return await prov.search(query, **kwargs)
        return prov.search(query, **kwargs)

    async def fetch(self, url: str, provider: str | None = None, **kwargs: Any) -> Any:
        """Fetch through a registered fetch provider."""
        providers = self._fetch_providers
        if not providers:
            raise RuntimeError("no fetch provider registered")
        name = provider or next(iter(providers))
        if name not in providers:
            raise ValueError(f"unknown fetch provider: {name}")
        prov = providers[name]
        if asyncio.iscoroutinefunction(prov.fetch):
            return await prov.fetch(url, **kwargs)
        return prov.fetch(url, **kwargs)


# ── Web tools ──────────────────────────────────────────────────────────────


class WebSearchTool:
    """web_search tool: limited to 10 queries per request, rate-limited."""

    def __init__(self, runtime: WebRuntime, max_queries: int = 10) -> None:
        self.runtime = runtime
        self.max_queries = max_queries

    async def __call__(self, queries: list[str], provider: str | None = None) -> list[dict[str, Any]]:
        if len(queries) > self.max_queries:
            raise ValueError(f"max {self.max_queries} queries per request, got {len(queries)}")
        results = []
        for q in queries:
            res = await self.runtime.search(q, provider=provider)
            results.append({"query": q, "results": res})
        return results


class WebFetchTool:
    """web_fetch tool: HTML→markdown via turndown, 200K cap."""

    MAX_BYTES = 200_000

    def __init__(self, runtime: WebRuntime) -> None:
        self.runtime = runtime

    async def __call__(self, url: str, provider: str | None = None) -> dict[str, Any]:
        raw = await self.runtime.fetch(url, provider=provider)
        text = raw if isinstance(raw, str) else str(raw)
        if len(text.encode("utf-8")) > self.MAX_BYTES:
            text = text[: self.MAX_BYTES] + "\n[truncated at 200K]"
        markdown = self._to_markdown(text)
        return {"url": url, "markdown": markdown, "bytes": len(markdown.encode("utf-8"))}

    @staticmethod
    def _to_markdown(html: str) -> str:
        """Best-effort HTML→markdown without external deps."""
        import re

        text = html
        text = re.sub(r"<script.*?</script>", "", text, flags=re.S | re.I)
        text = re.sub(r"<style.*?</style>", "", text, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
