"""Regression tests for Slice E.10 — MCP server name and URL validation."""

import json
from pathlib import Path

from zcoder.claude.capabilities.code import McpConnector


def _write_mcp_json(path: Path, servers: dict) -> Path:
    data = {"mcpServers": servers}
    path.write_text(json.dumps(data))
    return path


def test_valid_http_server_loaded(tmp_path):
    mcp = tmp_path / ".mcp.json"
    _write_mcp_json(mcp, {"my-server": {"type": "http", "url": "https://example.com"}})
    mc = McpConnector.from_json_file(mcp)
    assert "my-server" in mc.servers
    assert mc.servers["my-server"]["url"] == "https://example.com"


def test_invalid_scheme_rejected(tmp_path):
    mcp = tmp_path / ".mcp.json"
    _write_mcp_json(mcp, {"bad": {"type": "http", "url": "ftp://example.com"}})
    mc = McpConnector.from_json_file(mcp)
    assert "bad" not in mc.servers


def test_invalid_name_rejected(tmp_path):
    mcp = tmp_path / ".mcp.json"
    _write_mcp_json(mcp, {"../escape": {"type": "http", "url": "https://example.com"}})
    mc = McpConnector.from_json_file(mcp)
    assert "../escape" not in mc.servers


def test_stdio_server_without_url_accepted(tmp_path):
    mcp = tmp_path / ".mcp.json"
    _write_mcp_json(mcp, {"local": {"type": "stdio", "command": "python"}})
    mc = McpConnector.from_json_file(mcp)
    assert "local" in mc.servers


def test_multiple_valid_servers(tmp_path):
    mcp = tmp_path / ".mcp.json"
    _write_mcp_json(
        mcp,
        {
            "s1": {"type": "http", "url": "https://a.com"},
            "s2": {"type": "sse", "url": "https://b.com"},
            "s3": {"type": "stdio", "command": "node"},
        },
    )
    mc = McpConnector.from_json_file(mcp)
    assert "s1" in mc.servers
    assert "s2" in mc.servers
    assert "s3" in mc.servers


def test_mixed_valid_and_invalid(tmp_path):
    mcp = tmp_path / ".mcp.json"
    _write_mcp_json(
        mcp,
        {
            "good": {"type": "http", "url": "https://example.com"},
            "bad-url": {"type": "http", "url": "file:///etc/passwd"},
            "evil/../etc": {"type": "http", "url": "https://example.com"},
        },
    )
    mc = McpConnector.from_json_file(mcp)
    assert "good" in mc.servers
    assert "bad-url" not in mc.servers
    assert "evil/../etc" not in mc.servers
