"""Tests for zcoder.agent.codeagent.mcp_client - MCP client integration."""

from __future__ import annotations

from pathlib import Path

import pytest

from zcoder.agent.codeagent.mcp_client import (
    MCPCapability,
    MCPConnectionError,
    MCPError,
    MCPServerConfig,
    MCPServerNotFound,
    MCPTool,
    _make_transport,
    _rpc_request,
    _rpc_result,
    http_entry,
    mcp_config_entry,
    sse_entry,
    stdio_entry,
    ws_entry,
)


class TestMCPErrors:
    """Tests for MCP exception classes."""

    def test_mcp_error(self):
        err = MCPError("boom")
        assert str(err) == "boom"
        assert isinstance(err, Exception)

    def test_mcp_server_not_found(self):
        err = MCPServerNotFound("not found")
        assert str(err) == "not found"
        assert isinstance(err, MCPError)

    def test_mcp_connection_error(self):
        err = MCPConnectionError("conn failed")
        assert str(err) == "conn failed"
        assert isinstance(err, MCPError)


class TestRPCRequest:
    """Tests for JSON-RPC helpers."""

    def test_rpc_request(self):
        req = _rpc_request("tools/list", {"arg": "val"})
        assert req["jsonrpc"] == "2.0"
        assert "id" in req
        assert req["method"] == "tools/list"
        assert req["params"] == {"arg": "val"}

    def test_rpc_request_no_params(self):
        req = _rpc_request("initialize")
        assert req["jsonrpc"] == "2.0"
        assert req["method"] == "initialize"
        assert req["params"] == {}

    def test_rpc_result_success(self):
        resp = {"jsonrpc": "2.0", "id": "1", "result": {"tools": []}}
        assert _rpc_result(resp) == {"tools": []}

    def test_rpc_result_error(self):
        resp = {"jsonrpc": "2.0", "id": "1", "error": {"code": -32600, "message": "Invalid Request"}}
        with pytest.raises(MCPError, match="-32600 Invalid Request"):
            _rpc_result(resp)


class TestMCPServerConfig:
    """Tests for MCPServerConfig dataclass."""

    def test_creation(self):
        config = MCPServerConfig(name="test-server", type="stdio", command="mcp-server")
        assert config.name == "test-server"
        assert config.type == "stdio"
        assert config.command == "mcp-server"
        assert config.args == []
        assert config.env == {}
        assert config.url is None
        assert config.headers == {}
        assert config.timeout_ms == 28 * 60 * 60 * 1000
        assert config.always_load is False
        assert config.disabled is False
        assert config.scope == "local"
        assert config.source == ""
        assert config.channel is False

    def test_creation_with_url(self):
        config = MCPServerConfig(name="remote", type="http", url="https://example.com/mcp")
        assert config.type == "http"
        assert config.url == "https://example.com/mcp"

    def test_creation_with_all_fields(self):
        config = MCPServerConfig(
            name="full",
            type="websocket",
            command=None,
            args=["--flag"],
            env={"KEY": "val"},
            url="ws://example.com",
            headers={"Authorization": "Bearer token"},
            timeout_ms=5000,
            always_load=True,
            disabled=False,
            scope="user",
            source="config",
            channel=True,
        )
        assert config.args == ["--flag"]
        assert config.env == {"KEY": "val"}
        assert config.headers == {"Authorization": "Bearer token"}
        assert config.timeout_ms == 5000
        assert config.always_load is True
        assert config.scope == "user"
        assert config.source == "config"
        assert config.channel is True


class TestMCPTool:
    """Tests for MCPTool dataclass."""

    def test_creation(self):
        tool = MCPTool(
            name="read_file",
            description="Read a file",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
            server="filesystem",
        )
        assert tool.name == "read_file"
        assert tool.description == "Read a file"
        assert tool.server == "filesystem"
        assert tool.input_schema == {"type": "object", "properties": {"path": {"type": "string"}}}
        assert tool.annotations == {}

    def test_creation_with_annotations(self):
        tool = MCPTool(
            name="write",
            description="Write a file",
            input_schema={"type": "object"},
            server="fs",
            annotations={"title": "Write File", "readOnlyHint": False},
        )
        assert tool.annotations == {"title": "Write File", "readOnlyHint": False}


class TestMCPCapability:
    """Tests for MCPCapability dataclass."""

    def test_creation(self):
        cap = MCPCapability()
        assert cap.tools == []
        assert cap.prompts == []
        assert cap.resources == []
        assert cap.resource_templates == []

    def test_creation_with_data(self):
        tools = [MCPTool(name="t1", description="d1", input_schema={}, server="s")]
        cap = MCPCapability(
            tools=tools,
            prompts=[{"name": "p1"}],
            resources=[{"uri": "r1"}],
            resource_templates=[{"uriTemplate": "r2"}],
        )
        assert len(cap.tools) == 1
        assert cap.tools[0].name == "t1"
        assert cap.prompts == [{"name": "p1"}]
        assert cap.resources == [{"uri": "r1"}]
        assert cap.resource_templates == [{"uriTemplate": "r2"}]


class TestMCPClientConfig:
    """Tests for MCPClient configuration methods."""

    @pytest.fixture
    def client(self):
        from zcoder.agent.codeagent.mcp_client import MCPClient

        return MCPClient(cwd=Path("/tmp"))

    def test_add_server(self, client):
        config = MCPServerConfig(name="s1", type="stdio", command="cmd")
        client.add_server(config)
        servers = client.list_servers()
        assert "s1" in servers
        assert servers["s1"] is config

    def test_add_disabled_server_not_added(self, client):
        config = MCPServerConfig(name="disabled", type="stdio", command="cmd", disabled=True)
        client.add_server(config)
        servers = client.list_servers()
        assert "disabled" not in servers

    def test_add_reserved_name_raises(self, client):
        config = MCPServerConfig(name="workspace", type="stdio", command="cmd")
        with pytest.raises(MCPError, match="Reserved MCP server name"):
            client.add_server(config)

    def test_remove_server(self, client):
        config = MCPServerConfig(name="s1", type="stdio", command="cmd")
        client.add_server(config)
        client.remove_server("s1")
        servers = client.list_servers()
        assert "s1" not in servers

    def test_remove_nonexistent_server_no_error(self, client):
        client.remove_server("nonexistent")  # should not raise

    def test_server_status_not_configured(self, client):
        assert client.server_status("nonexistent") == "not configured"

    def test_server_status_disabled(self, client):
        # Disabled servers are not added to _servers at all
        config = MCPServerConfig(name="disabled", type="stdio", command="cmd", disabled=True)
        client.add_server(config)
        assert client.server_status("disabled") == "not configured"
        assert "disabled" not in client.list_servers()

    def test_server_status_not_connected(self, client):
        config = MCPServerConfig(name="s1", type="stdio", command="cmd")
        client.add_server(config)
        assert client.server_status("s1") == "not connected"


class TestMakeTransport:
    """Tests for _make_transport factory function."""

    def test_stdio_transport(self):
        config = MCPServerConfig(name="s1", type="stdio", command="cmd")
        transport = _make_transport(config, Path("/tmp"))
        from zcoder.agent.codeagent.mcp_client import StdioTransport

        assert isinstance(transport, StdioTransport)
        assert transport.config is config

    def test_http_transport(self):
        config = MCPServerConfig(name="s1", type="http", url="https://example.com")
        transport = _make_transport(config, Path("/tmp"))
        from zcoder.agent.codeagent.mcp_client import HTTPTransport

        assert isinstance(transport, HTTPTransport)

    def test_sse_transport(self):
        config = MCPServerConfig(name="s1", type="sse", url="https://example.com")
        transport = _make_transport(config, Path("/tmp"))
        from zcoder.agent.codeagent.mcp_client import SSETransport

        assert isinstance(transport, SSETransport)

    def test_websocket_transport(self):
        config = MCPServerConfig(name="s1", type="websocket", url="ws://example.com")
        transport = _make_transport(config, Path("/tmp"))
        from zcoder.agent.codeagent.mcp_client import WebSocketTransport

        assert isinstance(transport, WebSocketTransport)

    def test_unknown_transport_raises(self):
        config = MCPServerConfig(name="s1", type="unknown", command="cmd")
        with pytest.raises(MCPError, match="Unknown MCP transport type"):
            _make_transport(config, Path("/tmp"))


class TestConfigEntryHelpers:
    """Tests for MCP config entry helper functions."""

    def test_mcp_config_entry_command(self):
        entry = mcp_config_entry("fs", command="npx", args=["-y", "@modelcontextprotocol/server-filesystem"])
        assert entry["fs"]["command"] == "npx"
        assert entry["fs"]["args"] == ["-y", "@modelcontextprotocol/server-filesystem"]

    def test_mcp_config_entry_url(self):
        entry = mcp_config_entry("remote", url="https://example.com/mcp", type="http")
        assert entry["remote"]["url"] == "https://example.com/mcp"
        assert entry["remote"]["type"] == "http"

    def test_mcp_config_entry_with_env(self):
        entry = mcp_config_entry("fs", command="npx", env={"API_KEY": "secret"})
        assert entry["fs"]["env"] == {"API_KEY": "secret"}

    def test_stdio_entry(self):
        entry = stdio_entry("fs", "npx", ["-y", "@mcp/fs"])
        assert entry["fs"]["command"] == "npx"
        assert entry["fs"]["type"] == "stdio"
        assert entry["fs"]["args"] == ["-y", "@mcp/fs"]

    def test_http_entry(self):
        entry = http_entry("remote", "https://example.com/mcp")
        assert entry["remote"]["url"] == "https://example.com/mcp"
        assert entry["remote"]["type"] == "http"

    def test_sse_entry(self):
        entry = sse_entry("remote", "https://example.com/sse")
        assert entry["remote"]["url"] == "https://example.com/sse"
        assert entry["remote"]["type"] == "sse"

    def test_ws_entry(self):
        entry = ws_entry("remote", "wss://example.com/ws")
        assert entry["remote"]["url"] == "wss://example.com/ws"
        assert entry["remote"]["type"] == "websocket"


class TestMCPClientIntegration:
    """Integration-style tests for MCP client with mocked transports."""

    @pytest.fixture
    def client(self):
        from zcoder.agent.codeagent.mcp_client import MCPClient

        return MCPClient(cwd=Path("/tmp"))

    def test_add_and_list_servers(self, client):
        config1 = MCPServerConfig(name="s1", type="stdio", command="cmd1")
        config2 = MCPServerConfig(name="s2", type="http", url="https://ex.com")
        client.add_server(config1)
        client.add_server(config2)
        servers = client.list_servers()
        assert len(servers) == 2
        assert servers["s1"] is config1
        assert servers["s2"] is config2

    def test_find_tool_resolved(self, client):

        client._capabilities["fs"] = MCPCapability(
            tools=[
                MCPTool(name="read", description="Read", input_schema={}, server="fs"),
                MCPTool(name="write", description="Write", input_schema={}, server="fs"),
            ]
        )
        result = client.find_tool("mcp__fs__read")
        assert result is not None
        server, tool = result
        assert server == "fs"
        assert tool.name == "read"

    def test_find_tool_not_found(self, client):
        result = client.find_tool("mcp__nonexistent__tool")
        assert result is None

    def test_find_tool_invalid_format(self, client):
        result = client.find_tool("invalid_format")
        assert result is None

    def test_find_tool_wrong_prefix(self, client):
        result = client.find_tool("not_mcp__fs__read")
        assert result is None

    def test_get_tools_empty(self, client):
        tools = client.get_tools("nonexistent")
        assert tools == []

    def test_get_tools_with_data(self, client):
        client._capabilities["fs"] = MCPCapability(
            tools=[MCPTool(name="read", description="Read", input_schema={}, server="fs")]
        )
        tools = client.get_tools("fs")
        assert len(tools) == 1
        assert tools[0].name == "read"
