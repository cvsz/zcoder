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
