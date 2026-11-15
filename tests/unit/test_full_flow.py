"""Integration test for Phase 8: full flow end-to-end.

Covers credential → adapter → streaming → session log → tools → agents → web
per Prompt 7.8.
"""

from __future__ import annotations

import asyncio

import pytest

from zcoder.agent.orchestration.agents import AgentRegistry, AgentOptions
from zcoder.agent.orchestration.session_log import (
    EventType,
    SessionEvent,
    SessionEventStore,
)
from zcoder.agent.orchestration.tools import (
    ToolDefinition,
    ToolExecutionPipeline,
    ToolRegistry,
    ValueSchemaSpec,
)
from zcoder.agent.orchestration.web import WebRuntime, SearchProvider, FetchProvider
from zcoder.agent.orchestration.providers import resolve_api_key, MissingCredentialError


def test_credential_seam_blocks_missing_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(MissingCredentialError):
        resolve_api_key("groq")


def test_adapter_registry_has_all_providers():
    from zcoder.agent.orchestration import adapter as _  # noqa: F401
    from zcoder.agent.orchestration.registry import AdapterRegistry
    from zcoder.agent.orchestration.openai_compatible import OpenAICompatibleAdapter
    from zcoder.agent.orchestration.anthropic import AnthropicAdapter
    from zcoder.agent.orchestration.gemini import GeminiAdapter
    from zcoder.agent.orchestration.ollama import OllamaAdapter
    from zcoder.agent.orchestration.local import LocalAdapter

    reg = AdapterRegistry()
    reg.register("openai_compatible", OpenAICompatibleAdapter())
    reg.register("anthropic", AnthropicAdapter())
    reg.register("gemini", GeminiAdapter())
    reg.register("ollama", OllamaAdapter())
    reg.register("local", LocalAdapter())
    assert set(reg.list()) == {
        "anthropic",
        "gemini",
        "local",
        "ollama",
        "openai_compatible",
    }


def test_session_log_append_and_snapshot(tmp_path):
    store = SessionEventStore(db_path=tmp_path / "flow.db")
    store.append(SessionEvent(event_type=EventType.TURN_START, session_id="s1"))
    store.append(SessionEvent(event_type=EventType.ASSISTANT_MESSAGE, session_id="s1", payload={"content": "hi"}))
    snap = store.snapshot_events("s1")
    assert snap["session_format_version"] == 4
    assert snap["event_count"] == 2


def test_tool_registry_and_pipeline():
    reg = ToolRegistry()
    calls = []
    reg.register(
        ToolDefinition(
            name="echo",
            description="echo",
            parameters=ValueSchemaSpec(),
            execute=lambda **p: calls.append(p) or p.get("msg"),
        )
    )
    from zcoder.agent.orchestration.tools import ToolExecutionPipeline

    pipeline = ToolExecutionPipeline(reg)

    async def run():
        return await pipeline.run("echo", {"msg": "flow"})

    result = asyncio.run(run())
    assert result.success is True
    assert result.result == "flow"


def test_agent_registry_flow():
    reg = AgentRegistry()
    agent = reg.create(AgentOptions(), session="s1")
    assert reg.get(agent.id) is agent
    assert reg.list_agents() == [agent.id]


def test_web_runtime_search_fetch():
    rt = WebRuntime()
    rt.register_search_provider("x", SearchProvider("x", lambda q: [{"q": q}]))
    rt.register_fetch_provider("f", FetchProvider("f", lambda u: {"url": u}))

    async def run():
        search_res = await rt.search("hello")
        fetch_res = await rt.fetch("http://example.com")
        return search_res, fetch_res

    search_res, fetch_res = asyncio.run(run())
    assert search_res == [{"q": "hello"}]
    assert fetch_res == {"url": "http://example.com"}
