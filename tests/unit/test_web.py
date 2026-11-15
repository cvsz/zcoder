"""Unit tests for Phase 7: Web / Search / Fetch Capability Seam."""

from __future__ import annotations

import asyncio

import pytest

from zcoder.agent.orchestration.web import (
    FetchProvider,
    SearchBilling,
    SearchProvider,
    WebFetchTool,
    WebRuntime,
    WebSearchTool,
)


def test_search_billing_modes():
    assert SearchBilling.AUTO == "auto"
    assert SearchBilling.ACCOUNT == "account"
    assert SearchBilling.API_KEY == "api-key"


def test_web_runtime_register_providers():
    rt = WebRuntime()
    rt.register_search_provider("brave", SearchProvider("brave", lambda q: [{"q": q}]))
    rt.register_fetch_provider("readability", FetchProvider("readability", lambda u: {"url": u}))
    prov = rt.list_providers()
    assert "brave" in prov["search"]
    assert "readability" in prov["fetch"]
    assert rt.search_ready() is True
    assert rt.fetch_ready() is True


def test_web_runtime_no_providers():
    rt = WebRuntime()
    assert rt.search_ready() is False
    assert rt.fetch_ready() is False


def test_web_runtime_unknown_provider():
    rt = WebRuntime()
    rt.register_search_provider("x", SearchProvider("x", lambda q: []))
    with pytest.raises(ValueError, match="unknown search provider"):
        asyncio.run(rt.search("q", provider="nope"))


def test_web_search_tool_max_queries():
    rt = WebRuntime()
    rt.register_search_provider("x", SearchProvider("x", lambda q: [{"q": q}]))
    tool = WebSearchTool(rt, max_queries=2)
    with pytest.raises(ValueError, match="max 2 queries"):
        asyncio.run(tool(["a", "b", "c"]))


def test_web_search_tool_result():
    rt = WebRuntime()
    rt.register_search_provider("x", SearchProvider("x", lambda q: [{"q": q}]))
    tool = WebSearchTool(rt)

    async def run():
        return await tool(["a", "b"])

    res = asyncio.run(run())
    assert len(res) == 2
    assert res[0]["query"] == "a"
    assert res[0]["results"] == [{"q": "a"}]


def test_web_fetch_tool_truncation():
    rt = WebRuntime()
    rt.register_fetch_provider("x", FetchProvider("x", lambda u: "<p>" + "x" * 300000 + "</p>"))
    tool = WebFetchTool(rt)

    async def run():
        return await tool("http://example.com")

    res = asyncio.run(run())
    assert res["bytes"] <= WebFetchTool.MAX_BYTES + 50
    assert "[truncated at 200K]" in res["markdown"]


def test_web_fetch_tool_html_to_markdown():
    rt = WebRuntime()
    rt.register_fetch_provider("x", FetchProvider("x", lambda u: "<h1>Title</h1><p>Body</p>"))
    tool = WebFetchTool(rt)

    async def run():
        return await tool("http://example.com")

    res = asyncio.run(run())
    assert "Title" in res["markdown"]
    assert "Body" in res["markdown"]
    assert "<" not in res["markdown"]
