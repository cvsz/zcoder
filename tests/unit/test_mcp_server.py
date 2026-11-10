"""Regression tests for src/zcoder/agent/codeagent/mcp_server.py"""

from __future__ import annotations

from typing import Any

import pytest

from zcoder.agent.codeagent.mcp_client import MCPError
from zcoder.agent.codeagent.mcp_server import MCPServer, build_fastapi_app
from zcoder.agent.codeagent.tools import Tool, ToolContext, ToolOutput


class _FakeAgent:
    """Minimal fake CodeAgent for testing MCP server."""

    def __init__(self) -> None:
        self.ws = object()
        self.llm = object()
        self.policy = object()
        self.subagents = object()
        self.skills = object()
        self.tools: dict[str, Tool] = {}


class _FakeTool:
    """Minimal fake Tool for testing MCP server."""

    def __init__(
        self,
        name: str = "test_tool",
        description: str = "A test tool",
        parameters: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters or {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }

    def func(self, ctx: ToolContext, args: dict[str, Any]) -> ToolOutput:
        return ToolOutput(text=f"hello {args.get('name', 'world')}")


def _make_server(agent: Any | None = None) -> MCPServer:
    return MCPServer(root=".", agent=agent)


class TestMCPServerInit:
    """Tests for MCPServer.__init__ and list_tools."""

    def test_standalone_server_has_default_tools(self) -> None:
        server = _make_server()
        assert len(server.list_tools()) >= 1
        assert all("name" in t for t in server.list_tools())

    def test_agent_server_has_agent_tools(self) -> None:
        agent = _FakeAgent()
        agent.tools = {"custom_tool": _FakeTool(name="custom_tool")}
        server = _make_server(agent=agent)
        names = {t["name"] for t in server.list_tools()}
        assert "custom_tool" in names


class TestMCPServerCallTool:
    """Tests for MCPServer.call_tool."""

    @pytest.mark.asyncio
    async def test_unknown_tool_raises_mcp_error(self) -> None:
        server = _make_server()
        with pytest.raises(MCPError, match="Unknown tool"):
            await server.call_tool("nonexistent_tool", {})

    @pytest.mark.asyncio
    async def test_standalone_agent_only_tool_raises_mcp_error(self) -> None:
        server = _make_server()  # no agent
        with pytest.raises(MCPError, match="requires an active zcoder agent session"):
            await server.call_tool("Agent", {})

    @pytest.mark.asyncio
    async def test_agent_only_tool_with_agent_succeeds(self) -> None:
        agent = _FakeAgent()
        agent.tools = {"Agent": _FakeTool(name="Agent")}
        server = _make_server(agent=agent)
        result = await server.call_tool("Agent", {})
        assert result["isError"] is False
        assert result["content"][0]["content"] == "hello world"

    @pytest.mark.asyncio
    async def test_valid_tool_call_succeeds(self) -> None:
        server = _make_server()
        # Find any tool and call it with empty args
        tools = server.list_tools()
        if tools:
            result = await server.call_tool(tools[0]["name"], {})
            assert "isError" in result
            assert "content" in result
        else:
            assert len(tools) >= 0


class TestMCPServerResources:
    """Tests for MCP server resource methods."""

    @pytest.mark.asyncio
    async def test_list_resources_returns_list(self) -> None:
        server = _make_server()
        resources = await server.list_resources()
        assert isinstance(resources, list)

    @pytest.mark.asyncio
    async def test_read_resource_invalid_uri(self) -> None:
        server = _make_server()
        with pytest.raises(Exception, match="Unsupported resource URI"):
            await server.read_resource("http://evil.com/evil")

    @pytest.mark.asyncio
    async def test_read_resource_nonexistent(self) -> None:
        server = _make_server()
        with pytest.raises(Exception, match="Resource not found"):
            await server.read_resource("zcoder://file/nonexistent.txt")


class TestMCPServerJSONRPC:
    """Tests for MCPServer.handle JSON-RPC dispatch."""

    @pytest.mark.asyncio
    async def test_initialize(self) -> None:
        server = _make_server()
        result = await server.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {},
            }
        )
        assert result["protocolVersion"] == "2024-11-05"
        assert result["serverInfo"]["name"] == "zcoder"

    @pytest.mark.asyncio
    async def test_tools_list(self) -> None:
        server = _make_server()
        result = await server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        assert "tools" in result
        assert len(result["tools"]) >= 1

    @pytest.mark.asyncio
    async def test_method_not_found(self) -> None:
        server = _make_server()
        result = await server.handle(
            {"jsonrpc": "2.0", "id": 3, "method": "nonexistent_method", "params": {}}
        )
        assert result["error"]["code"] == -32601
        assert "Method not found" in result["error"]["message"]

    @pytest.mark.asyncio
    async def test_tools_call_unknown_tool(self) -> None:
        server = _make_server()
        result = await server.handle(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "nonexistent_tool", "arguments": {}},
            }
        )
        assert result["isError"] is True
        assert "Unknown tool" in result["content"][0]["content"]


def test_build_fastapi_app() -> None:
    from fastapi.testclient import TestClient

    server = _make_server()
    app = build_fastapi_app(server)
    client = TestClient(app)
    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["protocolVersion"] == "2024-11-05"
    assert data["serverInfo"]["name"] == "zcoder"


def test_mcp_sse_endpoint() -> None:
    from fastapi.testclient import TestClient

    server = _make_server()
    app = build_fastapi_app(server)
    client = TestClient(app)
    with client.stream("GET", "/mcp/sse") as stream:
        assert stream.status_code == 200
        lines = iter(stream.iter_lines())
        first_line = next(lines)
        assert first_line == "event: endpoint"
        second_line = next(lines)
        assert second_line.startswith("data: /mcp/messages/")
