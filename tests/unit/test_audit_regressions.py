"""Regression tests สำหรับ bug ที่พบจาก audit (runtime crash และ deadlock)."""

import asyncio
import importlib
from pathlib import Path
from typing import Any

import pytest

from zcoder.core.security import safe_resolve


def test_safe_resolve_returns_path_and_accepts_base_dir_keyword(tmp_path):
    result = safe_resolve("sub/file.txt", base_dir=tmp_path)
    assert isinstance(result, Path)
    result.parent.mkdir(parents=True)
    result.write_text("ok")
    assert (tmp_path / "sub" / "file.txt").read_text() == "ok"


def test_guarded_executor_keeps_successful_tool_result():
    from zcoder.tools.guard import GuardedToolExecutor
    from zcoder.tools.types import ToolContext, ToolOutput, ToolResult

    class _Tool:
        name = "echo"
        description = "echo"
        parameters: dict[str, Any] = {}
        category = "test"

        async def execute(self, context: ToolContext, params: dict[str, Any]) -> ToolResult:
            return ToolResult(success=True, output=ToolOutput(text="hi"), metadata={"k": 1})

    result = asyncio.run(GuardedToolExecutor().execute(_Tool(), ToolContext(), {}))
    assert result.success is True
    assert result.metadata["k"] == 1
    assert result.metadata["tool"] == "echo"
    assert "elapsed_ms" in result.metadata


def test_distributed_queue_enqueue_does_not_deadlock():
    from zcoder.agent.orchestration.distributed import DistributedQueue, DistributedTask, TaskStatus

    async def _run() -> None:
        queue = DistributedQueue()
        task = DistributedTask(id="t1", name="Task", payload={})
        assert await asyncio.wait_for(queue.enqueue(task), timeout=2) is True
        assert queue.remove_task("t1") is True
        assert task.status is TaskStatus.CANCELLED
        assert queue.size() == 0

    asyncio.run(_run())


@pytest.mark.parametrize(
    "module",
    [
        "zcoder.agent.codeagent.team_task_board",
        "zcoder.agent.models.zcoder_model",
        "zcoder.agent.models.sonnet5",
        "zcoder.infrastructure.stores.postgres",
    ],
)
def test_modules_import(module):
    importlib.import_module(module)


def test_token_usage_tracking_and_forecast():
    from zcoder.agent.optimization import tokens

    tokens._usage_history.clear()
    tokens._track_usage(100, 0.5, "claude-sonnet-5")
    forecast = tokens.forecast_spend(days=7, daily_prompts=2)
    assert forecast["total_forecast_usd"] >= 0


def test_web_search_rejects_blank_query():
    from zcoder.agent.codeagent.web_search import WebSearchArgsError, parse_search_args

    assert parse_search_args({"queries": ["a", "a", "b"]}) == ["a", "b"]
    with pytest.raises(WebSearchArgsError):
        parse_search_args({"queries": ["  "]})


def test_stdio_mcp_transport_roundtrip(tmp_path):
    """send() ต้อง drain ได้จริง (เดิมเรียก drain() บน transport เปล่า -> AttributeError)."""
    import sys

    from zcoder.agent.codeagent.mcp_client import MCPServerConfig, StdioTransport

    server = tmp_path / "echo_server.py"
    server.write_text(
        "import json, sys\n"
        "for line in sys.stdin:\n"
        "    msg = json.loads(line)\n"
        "    if msg.get('id') is not None:\n"
        "        print(json.dumps({'jsonrpc': '2.0', 'id': msg['id'], 'result': {'echo': msg['method']}}), flush=True)\n"
    )
    cfg = MCPServerConfig(name="echo", type="stdio", command=sys.executable, args=[str(server)])

    async def _run() -> dict:
        transport = StdioTransport(cfg, tmp_path, read_timeout=10.0)
        await transport.connect()
        try:
            return await transport.send({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        finally:
            await transport.close()

    reply = asyncio.run(_run())
    assert reply["result"] == {"echo": "tools/list"}


@pytest.mark.parametrize("url", ["http://127.0.0.1:11434/api/tags", "http://169.254.169.254/latest/meta-data/"])
def test_agent_webfetch_tool_refuses_internal_addresses(url):
    from zcoder.agent.codeagent.tools import ToolContext, default_tools

    out = default_tools()["WebFetch"].func(ToolContext(workspace=None), {"url": url})
    assert out.text.startswith("Failed to fetch") and "Refusing" in out.text


def test_tool_coroutines_run_on_agent_loop_from_worker_thread():
    """Async clients ผูกกับ loop ของ agent: tool ใน to_thread ต้องรัน coroutine บน loop เดิม."""
    from zcoder.agent.codeagent.tools import ToolContext, _run_on_agent_loop

    async def _main() -> bool:
        main_loop = asyncio.get_running_loop()
        ctx = ToolContext(workspace=None, agent_loop=main_loop)

        async def which_loop() -> asyncio.AbstractEventLoop:
            return asyncio.get_running_loop()

        ran_on = await asyncio.to_thread(_run_on_agent_loop, ctx, which_loop())
        return ran_on is main_loop

    assert asyncio.run(_main())


def test_hashed_embedding_is_deterministic_and_lexically_meaningful():
    import numpy as np

    from zcoder.agent.rag.vector_stores import hashed_embedding

    a = hashed_embedding("postgres connection pool timeout", 256)
    assert np.allclose(a, hashed_embedding("postgres connection pool timeout", 256))
    related = float(a @ hashed_embedding("connection pool timeout in postgres", 256))
    unrelated = float(a @ hashed_embedding("render the textual tui layout", 256))
    assert related > 0.5 > unrelated
    assert not hashed_embedding("", 16).any()


def test_offline_vector_store_ranks_by_cosine_and_filters():
    from zcoder.agent.rag.vector_stores import (
        OfflineVectorStore,
        VectorConfig,
        VectorStoreBackend,
        hashed_embedding,
    )

    store = OfflineVectorStore(VectorConfig(backend=VectorStoreBackend.OFFLINE, dimension=128, metric="cosine"))
    docs = {
        "db": "postgres connection pool settings",
        "ui": "textual widgets and layout",
        "db2": "postgres pool sizing guide",
    }
    for cid, text in docs.items():
        store.insert(cid, hashed_embedding(text, 128), {"content": text, "kind": "db" if "db" in cid else "ui"})
    results = store.search(hashed_embedding("postgres pool", 128), k=3)
    assert [r.chunk_id for r in results][-1] == "ui"
    assert results[0].score >= results[1].score >= results[2].score
    only_ui = store.search(hashed_embedding("postgres pool", 128), k=3, filter_metadata={"kind": "ui"})
    assert [r.chunk_id for r in only_ui] == ["ui"]


def test_zcoder_client_sends_sampling_params_in_options(monkeypatch):
    from zcoder.agent.models import zcoder_model

    captured: dict[str, Any] = {}

    def _fake_post(self, payload):
        captured.update(payload)
        return {"message": {"content": "ok"}}

    monkeypatch.setattr(zcoder_model.ZCoderClient, "_post", _fake_post)
    client = zcoder_model.ZCoderClient(max_tokens=64, temperature=0.2)
    assert client.call_text("hi") == "ok"
    assert captured["options"] == {"temperature": 0.2, "num_predict": 64}
    assert "temperature" not in captured
