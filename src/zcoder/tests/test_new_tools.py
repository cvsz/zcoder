"""Tests for the DatabaseQuery and APICall tools."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from zcoder.agent.codeagent.tools import (
    _api_call,
    _database_query,
    _web_search,
    default_tools,
)
from zcoder.agent.codeagent.workspace import ToolError, Workspace


def _make_ctx(tmp_path: Path):
    ws = Workspace(tmp_path)
    from zcoder.agent.codeagent.tools import ToolContext

    return ToolContext(workspace=ws)


class TestDatabaseQueryTool:
    """Tests for the _database_query tool function."""

    def _setup_db(self, tmp_path: Path) -> Path:
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, age INTEGER)")
        conn.execute("INSERT INTO users (name, age) VALUES ('Alice', 30), ('Bob', 25), ('Carol', 35)")
        conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, user_id INTEGER, amount REAL)")
        conn.execute("INSERT INTO orders (user_id, amount) VALUES (1, 100.50), (2, 50.00), (1, 200.00)")
        conn.commit()
        conn.close()
        return db_path

    def test_select_query(self, tmp_path):
        db_path = self._setup_db(tmp_path)
        ctx = _make_ctx(tmp_path)
        result = _database_query(
            ctx, {"db_path": str(db_path), "query": "SELECT name FROM users WHERE age > 30"}
        )
        assert "1 row(s)" in result.text
        data = json.loads(result.diff)
        assert data["columns"] == ["name"]
        assert data["rows"] == [{"name": "Carol"}]

    def test_select_all_columns(self, tmp_path):
        db_path = self._setup_db(tmp_path)
        ctx = _make_ctx(tmp_path)
        result = _database_query(ctx, {"db_path": str(db_path), "query": "SELECT * FROM users"})
        data = json.loads(result.diff)
        assert data["columns"] == ["id", "name", "age"]
        assert len(data["rows"]) == 3

    def test_query_with_join(self, tmp_path):
        db_path = self._setup_db(tmp_path)
        ctx = _make_ctx(tmp_path)
        result = _database_query(
            ctx,
            {
                "db_path": str(db_path),
                "query": "SELECT u.name, o.amount FROM users u JOIN orders o ON u.id = o.user_id",
            },
        )
        data = json.loads(result.diff)
        assert data["columns"] == ["name", "amount"]
        assert len(data["rows"]) == 3

    def test_empty_result(self, tmp_path):
        db_path = self._setup_db(tmp_path)
        ctx = _make_ctx(tmp_path)
        result = _database_query(
            ctx, {"db_path": str(db_path), "query": "SELECT * FROM users WHERE age > 999"}
        )
        data = json.loads(result.diff)
        assert data == []

    def test_nonexistent_db_raises(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        with pytest.raises(ToolError, match="does not exist"):
            _database_query(ctx, {"db_path": str(tmp_path / "nonexistent.db"), "query": "SELECT 1"})

    def test_db_path_outside_workspace_raises(self, tmp_path):
        # Create a DB outside the workspace
        outside_db = Path(tempfile.mkdtemp()) / "outside.db"
        sqlite3.connect(str(outside_db)).close()
        ctx = _make_ctx(tmp_path)
        with pytest.raises(ToolError, match="outside the workspace"):
            _database_query(ctx, {"db_path": str(outside_db), "query": "SELECT 1"})

    def test_non_select_query_raises(self, tmp_path):
        db_path = self._setup_db(tmp_path)
        ctx = _make_ctx(tmp_path)
        for bad_query in [
            "DELETE FROM users",
            "UPDATE users SET age = 99",
            "INSERT INTO users (name, age) VALUES ('Dave', 40)",
            "DROP TABLE users",
            "CREATE TABLE foo (x INT)",
        ]:
            with pytest.raises(ToolError, match="Only SELECT queries"):
                _database_query(ctx, {"db_path": str(db_path), "query": bad_query})

    def test_multiple_statements_raises(self, tmp_path):
        db_path = self._setup_db(tmp_path)
        ctx = _make_ctx(tmp_path)
        with pytest.raises(ToolError, match="Multiple SQL statements"):
            _database_query(
                ctx,
                {
                    "db_path": str(db_path),
                    "query": "SELECT * FROM users; DELETE FROM users",
                },
            )

    def test_invalid_sql_raises(self, tmp_path):
        db_path = self._setup_db(tmp_path)
        ctx = _make_ctx(tmp_path)
        # SELECT from a nonexistent table passes the SELECT check but fails at SQL execution
        with pytest.raises(ToolError, match="SQL error"):
            _database_query(ctx, {"db_path": str(db_path), "query": "SELECT * FROM nonexistent_table"})

    def test_db_path_is_directory_raises(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        with pytest.raises(ToolError, match="is a directory"):
            _database_query(ctx, {"db_path": str(tmp_path), "query": "SELECT 1"})


class TestAPICallTool:
    """Tests for the _api_call tool function."""

    def test_get_request(self):
        ctx = _make_ctx(Path(tempfile.mkdtemp()))
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = mock_urlopen.return_value.__enter__.return_value
            mock_resp.status = 200
            mock_resp.headers = {"Content-Type": "application/json"}
            mock_resp.read.return_value = b'{"message": "hello"}'
            result = _api_call(ctx, {"url": "https://api.example.com/data"})
        assert "200" in result.text
        data = json.loads(result.diff)
        assert data["status"] == 200
        assert data["body"] == '{"message": "hello"}'

    def test_post_request_with_json_body(self):
        ctx = _make_ctx(Path(tempfile.mkdtemp()))
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = mock_urlopen.return_value.__enter__.return_value
            mock_resp.status = 201
            mock_resp.headers = {"Content-Type": "application/json"}
            mock_resp.read.return_value = b'{"id": 123}'
            result = _api_call(
                ctx,
                {
                    "url": "https://api.example.com/items",
                    "method": "POST",
                    "body": {"name": "test"},
                },
            )
        data = json.loads(result.diff)
        assert data["status"] == 201
        # Verify the request was made with JSON body
        call_args = mock_urlopen.call_args[0][0]
        assert call_args.method == "POST"
        assert call_args.data == b'{"name": "test"}'

    def test_get_request_with_headers(self):
        ctx = _make_ctx(Path(tempfile.mkdtemp()))
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = mock_urlopen.return_value.__enter__.return_value
            mock_resp.status = 200
            mock_resp.headers = {}
            mock_resp.read.return_value = b"ok"
            result = _api_call(
                ctx,
                {
                    "url": "https://api.example.com/data",
                    "headers": {"Authorization": "Bearer token123"},
                },
            )
        data = json.loads(result.diff)
        assert data["status"] == 200
        call_args = mock_urlopen.call_args[0][0]
        # Verify the Authorization header was passed
        auth_headers = [v for k, v in call_args.header_items() if k.lower() == "authorization"]
        assert "Bearer token123" in auth_headers

    def test_invalid_url_scheme_raises(self):
        ctx = _make_ctx(Path(tempfile.mkdtemp()))
        with pytest.raises(ToolError, match="Only http:// and https:// URLs"):
            _api_call(ctx, {"url": "ftp://example.com/file"})

    def test_invalid_method_raises(self):
        ctx = _make_ctx(Path(tempfile.mkdtemp()))
        with pytest.raises(ToolError, match="Unsupported HTTP method"):
            _api_call(ctx, {"url": "https://example.com", "method": "PROPFIND"})

    def test_invalid_timeout_raises(self):
        ctx = _make_ctx(Path(tempfile.mkdtemp()))
        with pytest.raises(ToolError, match="timeout must be a number"):
            _api_call(ctx, {"url": "https://example.com", "timeout": "not_a_number"})

    def test_timeout_out_of_range_raises(self):
        ctx = _make_ctx(Path(tempfile.mkdtemp()))
        with pytest.raises(ToolError, match="timeout must be a number"):
            _api_call(ctx, {"url": "https://example.com", "timeout": 500})

    def test_http_error_response(self):
        ctx = _make_ctx(Path(tempfile.mkdtemp()))
        import urllib.error

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.HTTPError(
                "https://api.example.com/error", 404, "Not Found", {}, None
            )
            result = _api_call(ctx, {"url": "https://api.example.com/error"})
        data = json.loads(result.diff)
        assert data["status"] == 404

    def test_url_required_raises(self):
        ctx = _make_ctx(Path(tempfile.mkdtemp()))
        with pytest.raises(ToolError, match="url is required"):
            _api_call(ctx, {})


class TestWebSearchTool:
    """Tests for the _web_search tool function."""

    def test_web_search(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = mock_urlopen.return_value.__enter__.return_value
            mock_resp.status = 200
            mock_resp.read.return_value = b"""
            <html>
            <div class="result">
                <a class="result__a" href="https://example.com/page1">
                    <h2 class="result__title">First Result</h2>
                </a>
                <a class="result__snippet">This is the first search result snippet.</a>
            </div>
            <div class="result">
                <a class="result__a" href="https://example.com/page2">
                    <h2 class="result__title">Second Result</h2>
                </a>
                <a class="result__snippet">This is the second search result snippet.</a>
            </div>
            """
            result = _web_search(ctx, {"query": "test query"})
        assert "first search result snippet" in result.text
        assert "second search result snippet" in result.text
        assert "First Result" not in result.text

    def test_web_search_no_results(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = mock_urlopen.return_value.__enter__.return_value
            mock_resp.status = 200
            mock_resp.read.return_value = b"<html><body>No results found</body></html>"
            result = _web_search(ctx, {"query": "nonexistent query xyzzy"})
        assert "No results for" in result.text

    def test_web_search_query_required(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        with pytest.raises(ToolError, match="query is required"):
            _web_search(ctx, {})

    def test_web_search_empty_query_raises(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        with pytest.raises(ToolError, match="query is required"):
            _web_search(ctx, {"query": "   "})

    @pytest.mark.asyncio
    async def test_web_search_exception_handling(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = Exception("Network error")
            result = _web_search(ctx, {"query": "test query"})
        assert "Search failed" in result.text


class TestDefaultToolsIncludesNewTools:
    """Tests that the new tools are registered in default_tools()."""

    def test_database_query_in_default_tools(self):
        tools = default_tools()
        assert "DatabaseQuery" in tools
        tool = tools["DatabaseQuery"]
        assert tool.category == "read"
        assert "db_path" in tool.parameters["required"]
        assert "query" in tool.parameters["required"]

    def test_api_call_in_default_tools(self):
        tools = default_tools()
        assert "APICall" in tools
        tool = tools["APICall"]
        assert tool.category == "read"
        assert "url" in tool.parameters["required"]

    def test_web_search_in_default_tools(self):
        tools = default_tools()
        assert "WebSearch" in tools
        tool = tools["WebSearch"]
        assert tool.category == "read"
        assert "query" in tool.parameters["required"]
