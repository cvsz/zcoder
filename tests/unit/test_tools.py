"""Unit tests for Phase 5: Tool Registry & Guarded Execution."""

from __future__ import annotations

import asyncio

import pytest

from zcoder.agent.orchestration.tools import (
    ToolDefinition,
    ToolExecutionPipeline,
    ToolRegistry,
    ToolResult,
    ValueSchemaSpec,
    executeToolBatch,
)


def test_value_schema_spec_validation():
    spec = ValueSchemaSpec(
        type="object",
        properties={"name": {"type": "string"}, "count": {"type": "integer"}},
        required=["name"],
    )
    assert spec.validate({"name": "a", "count": 1}) == []
    assert spec.validate({"count": 1}) == ["missing required parameter: name"]
    assert spec.validate({"name": 123}) == ["parameter 'name' must be a string"]
    assert spec.validate({"name": "a", "count": "x"}) == ["parameter 'count' must be an integer"]


def test_tool_registry_register_get_list():
    reg = ToolRegistry()
    assert reg.list() == []
    tool = ToolDefinition(
        name="echo",
        description="echo tool",
        parameters=ValueSchemaSpec(),
        execute=lambda **p: p,
    )
    reg.register(tool)
    assert reg.list() == ["echo"]
    assert reg.get("echo") is tool
    assert reg.get("missing") is None


def test_tool_validation_in_registry():
    reg = ToolRegistry()
    reg.register(
        ToolDefinition(
            name="add",
            description="add two numbers",
            parameters=ValueSchemaSpec(
                properties={"a": {"type": "integer"}, "b": {"type": "integer"}},
                required=["a", "b"],
            ),
            execute=lambda **p: p["a"] + p["b"],
        )
    )
    pipeline = ToolExecutionPipeline(reg)

    async def run():
        return await pipeline.run("add", {"a": 1, "b": 2})

    result = asyncio.run(run())
    assert result.success is True
    assert result.result == 3


def test_pipeline_unknown_tool():
    pipeline = ToolExecutionPipeline(ToolRegistry())

    async def run():
        return await pipeline.run("nope", {})

    result = asyncio.run(run())
    assert result.success is False
    assert "unknown tool" in result.error


def test_pipeline_validation_error():
    reg = ToolRegistry()
    reg.register(
        ToolDefinition(
            name="add",
            description="add",
            parameters=ValueSchemaSpec(required=["a"]),
            execute=lambda **p: p["a"],
        )
    )
    pipeline = ToolExecutionPipeline(reg)

    async def run():
        return await pipeline.run("add", {})

    result = asyncio.run(run())
    assert result.success is False
    assert "missing required parameter" in result.error


def test_pipeline_emits_events():
    reg = ToolRegistry()
    reg.register(
        ToolDefinition(
            name="echo",
            description="echo",
            parameters=ValueSchemaSpec(),
            execute=lambda **p: p.get("msg"),
        )
    )
    events = []
    pipeline = ToolExecutionPipeline(reg)
    pipeline.set_emitter(lambda name, payload: events.append((name, payload)))

    async def run():
        return await pipeline.run("echo", {"msg": "hi"})

    result = asyncio.run(run())
    assert result.success is True
    assert any(name == "result" for name, _ in events)
    assert any(name == "change" for name, _ in events)


async def _slow_tool(**kwargs):
    await asyncio.sleep(0.05)
    return kwargs.get("v", 0)


def test_execute_tool_batch_concurrency():
    reg = ToolRegistry()
    reg.register(
        ToolDefinition(name="slow", description="slow", parameters=ValueSchemaSpec(), execute=_slow_tool)
    )
    pipeline = ToolExecutionPipeline(reg)

    calls = [("slow", {"v": i}) for i in range(5)]

    async def run():
        return await executeToolBatch(pipeline, calls, max_concurrency=2)

    results = asyncio.run(run())
    assert len(results) == 5
    assert all(r.success for r in results)
    assert sorted(r.result for r in results) == [0, 1, 2, 3, 4]
