from __future__ import annotations

import pytest

from zcoder.agent.codeagent.mcp_server import MCPServer
from zcoder.agent.codeagent.tools import Tool


@pytest.mark.asyncio
async def test_tool_execution_errors_do_not_expose_exception_details(tmp_path, monkeypatch):
    server = MCPServer(tmp_path)

    def fail(_ctx, _args):
        raise RuntimeError("database password=super-secret")

    server._tools["ExplodingTool"] = Tool(
        name="ExplodingTool",
        description="Test tool",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        category="read",
        func=fail,
    )
    monkeypatch.setattr(
        "zcoder.agent.codeagent.mcp_server.preview",
        lambda *_args: ("ExplodingTool", None),
    )

    response = await server.call_tool("ExplodingTool", {})

    assert response["isError"] is True
    message = response["content"][0]["content"]
    assert message == "Tool execution failed. Check server logs for details."
    assert "super-secret" not in message
    assert "RuntimeError" not in message
