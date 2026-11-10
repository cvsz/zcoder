"""MCP server — exposes zcoder's tools to external MCP clients.

zcoder can now act as an MCP *server* (not just a client). External MCP
hosts (Claude Desktop, Cursor, etc.) connect to zcoder over stdio or
HTTP/SSE and call zcoder's tools through the Model Context Protocol.

Transports:
  * stdio   — subprocess-based (default for MCP hosts)
  * http    — streamable-HTTP / SSE over localhost
  * websocket — persistent bidirectional (requires websockets package)

JSON-RPC 2.0 methods:
  initialize, tools/list, tools/call, resources/list, resources/read,
  prompts/list, prompts/get, ping

zcoder runs entirely on loopback local inference — this server binds to
loopback by default and never calls hosted model APIs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from zcoder.agent.codeagent.loop import CodeAgent
from zcoder.agent.codeagent.mcp_client import MCPError
from zcoder.agent.codeagent.tools import (
    Tool,
    ToolContext,
    ToolError,
    ToolOutput,
    default_tools,
    preview,
)
from zcoder.agent.codeagent.workspace import IGNORED_DIRS, Workspace

logger = logging.getLogger("zcoder.mcp.server")

_MCP_VERSION = "2024-11-05"
_PROTOCOL_VERSION = "2024-11-05"
_SERVER_NAME = "zcoder"
_SERVER_VERSION = "1.0.0"

# Tools that require an active CodeAgent (LLM/policy/registry) and cannot run
# in a standalone MCP server without a full agent. They are advertised but
# return a clear error when invoked outside an agent session.
_AGENT_ONLY_TOOLS = frozenset(
    {
        "Agent",
        "MCP",
        "Skill",
        "AskUserQuestion",
        "LSP",
        "TaskOutput",
        "BashOutput",
        "KillShell",
        "BackgroundOutput",
    }
)

# Read-only tools safe to expose without authentication gating beyond the MCP
# host's own transport security.
_READ_ONLY_TOOLS = frozenset({"Read", "Glob", "Grep", "LS", "TodoWrite"})


def _tool_to_mcp(tool: Tool) -> dict[str, Any]:
    """Convert a zcoder Tool into an MCP tool definition."""
    return {
        "name": tool.name,
        "description": tool.description or "",
        "inputSchema": tool.parameters or {"type": "object", "properties": {}, "additionalProperties": False},
    }


@dataclass
class _MCPRequest:
    jsonrpc: str
    id: Any
    method: str
    params: dict[str, Any] | None


@dataclass
class _MCPServerState:
    ws: Workspace
    agent: CodeAgent | None = None
    tools: dict[str, Tool] = field(default_factory=dict)
    initialized: bool = False


class MCPServer:
    """MCP 2024-11-05 server wrapping a zcoder CodeAgent (or standalone tools)."""

    def __init__(self, root: Path | str = ".", agent: CodeAgent | None = None):
        self.root = Path(root).expanduser().resolve()
        self.agent = agent
        self.ws = agent.ws if agent is not None else Workspace(self.root)
        self.state = _MCPServerState(ws=self.ws, agent=agent)
        self._tools: dict[str, Tool] = {}
        self._tool_ctx = ToolContext(
            self.ws,
            agent_llm=agent.llm if agent else None,
            agent_policy=agent.policy if agent else None,
            agent_registry=agent.subagents if agent else None,
            agent_mcp=None,
            agent_skills=agent.skills if agent else None,
        )
        # Build tool map once (agent-provided or standalone defaults).
        if agent is not None:
            self._tools = dict(agent.tools)
        else:
            self._tools = default_tools()
        self.state.tools = self._tools

    # ------------------------------------------------------------------ tools

    def list_tools(self) -> list[dict[str, Any]]:
        return [_tool_to_mcp(t) for t in self._tools.values()]

    def _can_call(self, name: str) -> bool:
        if self.agent is None and name in _AGENT_ONLY_TOOLS:
            return False
        return True

    async def call_tool(self, name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
        if name not in self._tools:
            raise MCPError(f"Unknown tool: {name}")
        tool = self._tools[name]
        if not self._can_call(name):
            raise MCPError(
                f"Tool '{name}' requires an active zcoder agent session. "
                f"Start zcoder with --mcp-server to enable it."
            )
        args = arguments or {}
        # Validate + preview (permission-like, non-mutating summary).
        try:
            from zcoder.agent.codeagent.tools import validate_args

            args = validate_args(tool, args)
        except ToolError as exc:
            return {"isError": True, "content": [{"type": "text", "content": str(exc)}]}

        summary, _diff = preview(self._tool_ctx, tool, args)
        logger.debug("MCP tool call: %s args=%s preview=%s", name, args, summary)

        # Execute the tool (sync function run in a thread to avoid blocking).
        loop = asyncio.get_running_loop()
        try:
            out: ToolOutput = await loop.run_in_executor(None, tool.func, self._tool_ctx, args)
        except ToolError as exc:
            return {"isError": True, "content": [{"type": "text", "content": str(exc)}]}
        except Exception:  # unexpected tool bug
            logger.exception("MCP tool %s failed", name)
            return {"isError": True, "content": [{"type": "text", "content": "Tool execution failed. Check server logs for details."}]}

        text = out.text or ""
        if out.diff:
            text = f"{text}\n\n--- Diff ---\n{out.diff}" if text else out.diff
        return {
            "content": [
                {"type": "text", "content": text or "(no output)"},
            ],
            "isError": False,
        }

    # ------------------------------------------------------------------ resources

    async def list_resources(self) -> list[dict[str, Any]]:
        """List workspace files as MCP resources (bounded scan)."""
        resources: list[dict[str, Any]] = []
        scanned = 0
        for path in self.ws.root.rglob("*"):
            scanned += 1
            if scanned > 2048:
                break
            if not path.is_file():
                continue
            rel = path.relative_to(self.ws.root)
            if any(part in IGNORED_DIRS for part in rel.parts):
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            resources.append(
                {
                    "uri": f"zcoder://file/{rel.as_posix()}",
                    "name": rel.as_posix(),
                    "mimeType": "text/plain",
                    "size": size,
                }
            )
        return resources

    async def read_resource(self, uri: str) -> dict[str, Any]:
        if not uri.startswith("zcoder://file/"):
            raise MCPError(f"Unsupported resource URI: {uri}")
        rel = uri[len("zcoder://file/") :]
        path = (self.ws.root / rel).resolve()
        if not any(path == r or r in path.parents for r in (self.ws.root,)):
            raise MCPError(f"Resource outside workspace: {uri}")
        if not path.is_file():
            raise MCPError(f"Resource not found: {uri}")
        data = path.read_bytes()
        text = data.decode("utf-8", errors="replace")
        return {"contents": [{"uri": uri, "mimeType": "text/plain", "text": text}]}

    # ------------------------------------------------------------------ prompts

    async def list_prompts(self) -> list[dict[str, Any]]:
        return []

    # ------------------------------------------------------------------ JSON-RPC dispatch

    async def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        method = message.get("method")
        params = message.get("params") or {}
        req_id = message.get("id")

        if method == "initialize":
            return {
                "protocolVersion": _PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"listChanged": False, "subscribe": False},
                    "prompts": {"listChanged": False},
                    "logging": {},
                },
                "serverInfo": {"name": _SERVER_NAME, "version": _SERVER_VERSION},
            }
        if method == "initialized":
            # Client notification; no response.
            self.state.initialized = True
            return None
        if method == "tools/list":
            return {"tools": self.list_tools()}
        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if not isinstance(name, str):
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32602, "message": "Invalid params: 'name' is required"},
                }
            try:
                return await self.call_tool(name, arguments)
            except MCPError as exc:
                return {"isError": True, "content": [{"type": "text", "content": str(exc)}]}
        if method == "resources/list":
            return {"resources": await self.list_resources()}
        if method == "resources/read":
            try:
                return await self.read_resource(params.get("uri", ""))
            except MCPError as exc:
                return {"isError": True, "content": [{"type": "text", "content": str(exc)}]}
        if method == "prompts/list":
            return {"prompts": await self.list_prompts()}
        if method == "ping":
            return {}
        if method == "notifications/initialized":
            return None

        if req_id is not None:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }
        return None


# ---------------------------------------------------------------------------
# stdio transport
# ---------------------------------------------------------------------------


async def run_stdio(server: MCPServer) -> None:
    """Serve MCP over stdin/stdout (line-delimited JSON-RPC 2.0)."""
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    loop = asyncio.get_running_loop()
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)
    writer_transport, _ = await loop.connect_write_pipe(
        lambda: asyncio.streams.FlowControlMixin(), sys.stdout
    )
    writer = asyncio.StreamWriter(writer_transport, protocol, None, loop)

    while True:
        line = await reader.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            _send(writer, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
            continue
        try:
            response = await server.handle(msg)
        except Exception:  # unexpected server error
            logger.exception("MCP server handler failed")
            response = {
                "jsonrpc": "2.0",
                "id": msg.get("id"),
                "error": {"code": -32603, "message": "Internal server error"},
            }
        if response is not None:
            response.setdefault("jsonrpc", "2.0")
            if "id" not in response and msg.get("id") is not None:
                response["id"] = msg["id"]
            _send(writer, response)


def _send(writer: asyncio.StreamWriter, msg: dict[str, Any]) -> None:
    data = (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")
    writer.write(data)
    # Fire-and-forget drain; the reader loop will backpressure naturally.


# ---------------------------------------------------------------------------
# HTTP / SSE transport (FastAPI)
# ---------------------------------------------------------------------------


def build_fastapi_app(server: MCPServer) -> Any:
    """Build a FastAPI app serving MCP over streamable-HTTP + SSE."""
    from fastapi import Body, FastAPI
    from fastapi.responses import JSONResponse, StreamingResponse

    app = FastAPI(title="zcoder MCP Server", version=_SERVER_VERSION)

    @app.post("/mcp")
    async def mcp_endpoint(body: dict | list[dict] = Body(...)):  # noqa: B008
        if not isinstance(body, list):
            body = [body]
        responses = []
        for msg in body:
            try:
                resp = await server.handle(msg)
            except Exception:  # noqa: BLE001
                logger.exception("MCP HTTP handler failed")
                resp = {
                    "jsonrpc": "2.0",
                    "id": msg.get("id") if isinstance(msg, dict) else None,
                    "error": {"code": -32603, "message": "Internal server error"},
                }
            if resp is not None:
                resp.setdefault("jsonrpc", "2.0")
                if "id" not in resp and isinstance(msg, dict) and msg.get("id") is not None:
                    resp["id"] = msg["id"]
                responses.append(resp)
        if len(responses) == 1:
            return JSONResponse(responses[0])
        return JSONResponse(responses)

    @app.get("/mcp/sse")
    async def mcp_sse():
        """Server-Sent Events endpoint for MCP over HTTP."""
        queue: asyncio.Queue[str] = asyncio.Queue()

        async def event_stream():
            while True:
                msg = await queue.get()
                yield f"data: {msg}\n\n"

        # Register a one-shot handler that pushes responses into the queue.
        # This is a simplified SSE bridge; full bidirectional SSE would need
        # a persistent session registry.
        async def _push(method: str, params: dict[str, Any], req_id: Any):
            resp = await server.handle(
                {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}
            )
            if resp is not None:
                await queue.put(json.dumps(resp, ensure_ascii=False))

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    return app


def run_http(server: MCPServer, host: str = "127.0.0.1", port: int = 8422) -> None:
    """Run the MCP server over HTTP/SSE using uvicorn."""
    try:
        import uvicorn
    except ImportError as exc:
        raise MCPError("uvicorn is required for HTTP MCP transport: pip install uvicorn") from exc

    app = build_fastapi_app(server)
    uvicorn.run(app, host=host, port=port, log_level="warning")


# ---------------------------------------------------------------------------
# WebSocket transport
# ---------------------------------------------------------------------------


async def run_websocket(server: MCPServer, host: str = "127.0.0.1", port: int = 8423) -> None:
    """Serve MCP over WebSocket."""
    try:
        import websockets
    except ImportError as exc:
        raise MCPError("websockets package is required for WebSocket MCP transport") from exc

    async def _handler(websocket):
        async for raw in websocket:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send(
                    json.dumps(
                        {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
                    )
                )
                continue
            try:
                resp = await server.handle(msg)
            except Exception:  # noqa: BLE001
                logger.exception("MCP WebSocket handler failed")
                resp = {
                    "jsonrpc": "2.0",
                    "id": msg.get("id"),
                    "error": {"code": -32603, "message": "Internal server error"},
                }
            if resp is not None:
                resp.setdefault("jsonrpc", "2.0")
                if "id" not in resp and msg.get("id") is not None:
                    resp["id"] = msg["id"]
                await websocket.send(json.dumps(resp, ensure_ascii=False))

    async with websockets.serve(_handler, host, port):
        await asyncio.Future()  # run forever
