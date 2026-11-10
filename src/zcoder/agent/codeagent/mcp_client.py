"""MCP client — Model Context Protocol support for zcoder.

Supports four transports:
  * stdio   — local subprocess server
  * http    — remote HTTP / streamable-http server
  * sse     — remote SSE server (deprecated, auto-fallback from http)
  * websocket — remote WebSocket server (persistent bidirectional)

JSON-RPC 2.0 over all transports. Capability discovery (tools/prompts/resources),
tool invocation, list_changed notifications with reconnection, and automatic
reconnection with exponential backoff.

zcoder runs entirely on loopback local inference — MCP servers are configured
by the user/org and run locally or on approved remote endpoints.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess  # nosec B404  # stdio MCP servers are user/org-configured
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx

# ---------------------------------------------------------------------------
# Configuration & transport selection
# ---------------------------------------------------------------------------

_TRANSPORT_RE = re.compile(r"^(stdio|http|sse|websocket|ws)$", re.IGNORECASE)

# Reserved built-in server names (Claude Code-compatible).
_RESERVED_NAMES = frozenset(
    {"workspace", "claude-in-chrome", "computer-use", "claude preview", "claude browser"}
)

# Default MCP protocol timeout values.
_MCP_TOOL_TIMEOUT_DEFAULT_MS = 28 * 60 * 60 * 1000  # ~28 hours
_MCP_IDLE_TIMEOUT_STDIO_MS = 30 * 60 * 1000  # 30 minutes
_MCP_IDLE_TIMEOUT_HTTP_MS = 5 * 60 * 1000  # 5 minutes
_MAX_RECONNECT_ATTEMPTS = 5
_INITIAL_BACKOFF_S = 1.0


@dataclass
class MCPServerConfig:
    """Configuration for one MCP server."""

    name: str
    type: str  # stdio | http | sse | websocket | ws
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    timeout_ms: int = _MCP_TOOL_TIMEOUT_DEFAULT_MS
    always_load: bool = False
    disabled: bool = False
    scope: str = "local"  # local | project | user | managed
    source: str = ""  # where the config came from
    channel: bool = False  # claude/channel capability


@dataclass
class MCPTool:
    """One tool offered by an MCP server."""

    name: str
    description: str
    input_schema: dict[str, Any]
    server: str
    annotations: dict[str, Any] = field(default_factory=dict)


@dataclass
class MCPCapability:
    """Discovery result from a server."""

    tools: list[MCPTool] = field(default_factory=list)
    prompts: list[dict[str, Any]] = field(default_factory=list)
    resources: list[dict[str, Any]] = field(default_factory=list)


class MCPError(Exception):
    """Base MCP client error."""


class MCPServerNotFound(MCPError):
    pass


class MCPConnectionError(MCPError):
    pass


# ---------------------------------------------------------------------------
# JSON-RPC helpers
# ---------------------------------------------------------------------------


def _rpc_request(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": method, "params": params or {}}


def _rpc_result(response: dict[str, Any]) -> Any:
    if "error" in response:
        err = response["error"]
        raise MCPError(f"{err.get('code')} {err.get('message')}")
    return response.get("result")


# ---------------------------------------------------------------------------
# Transport implementations
# ---------------------------------------------------------------------------


class _BaseTransport:
    async def connect(self) -> None:
        raise NotImplementedError

    async def send(self, message: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    async def notifications(self) -> asyncio.Queue[dict[str, Any]]:
        raise NotImplementedError

    async def close(self) -> None:
        raise NotImplementedError


class StdioTransport(_BaseTransport):
    """Local subprocess MCP server communicating over stdin/stdout JSON-RPC."""

    def __init__(
        self,
        config: MCPServerConfig,
        cwd: Path,
        read_timeout: float = 30.0,
    ):
        self.config = config
        self.cwd = cwd
        self.read_timeout = read_timeout
        self._proc: subprocess.Popen | None = None
        self._reader: asyncio.StreamReader | None = None
        self._read_transport: Any = None
        self._writer: Any = None
        self._notify_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._reader_task: asyncio.Task | None = None
        self._started = asyncio.Event()
        # _read_loop and send() both consume from self._reader; serialize them
        # so a notification read never races with a response read and corrupts the stream.
        self._read_lock = asyncio.Lock()
        self._pending: dict[Any, asyncio.Future[dict[str, Any]]] = {}

    async def connect(self) -> None:
        env = dict(os.environ)
        env.update(self.config.env)
        env["CLAUDE_PROJECT_DIR"] = str(self.cwd)
        try:
            cmd = self.config.command
            if cmd is None:
                raise MCPConnectionError(f"stdio server '{self.config.name}' has no command")
            self._proc = subprocess.Popen(  # noqa: S603  # nosec B602  # user-configured stdio server
                [cmd, *self.config.args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                cwd=self.cwd,
                env=env,
            )
        except OSError as exc:
            raise MCPConnectionError(f"stdio server '{self.config.name}' failed to start: {exc}") from exc

        loop = asyncio.get_event_loop()
        self._reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(self._reader)
        _read_transport, _ = await loop.connect_read_pipe(lambda: protocol, self._proc.stdout)
        self._read_transport = _read_transport
        write_transport, _ = await loop.connect_write_pipe(asyncio.streams.FlowControlMixin, self._proc.stdin)
        self._writer = write_transport
        self._reader_task = asyncio.create_task(self._read_loop())
        self._started.set()

    async def _read_loop(self) -> None:
        assert self._reader is not None
        while True:
            line = await self._reader.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            req_id = msg.get("id")
            if "method" in msg and req_id is None:
                await self._notify_queue.put(msg)
            elif req_id is not None:
                fut = self._pending.pop(req_id, None)
                if fut is not None and not fut.done():
                    fut.set_result(msg)

    async def send(self, message: dict[str, Any]) -> dict[str, Any]:
        assert self._writer is not None and self._proc is not None
        req_id = message.get("id")
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict[str, Any]] | None = None
        if req_id is not None:
            fut = loop.create_future()
            self._pending[req_id] = fut
        async with self._read_lock:
            payload = json.dumps(message) + "\n"
            self._writer.write(payload.encode())
            await self._writer.drain()
            if fut is None:
                return {}
            try:
                return await asyncio.wait_for(fut, timeout=self.read_timeout)
            except TimeoutError:
                self._pending.pop(req_id, None)
                raise MCPConnectionError(
                    f"stdio server '{self.config.name}' timed out waiting for response"
                ) from None

    async def notifications(self) -> asyncio.Queue[dict[str, Any]]:
        return self._notify_queue

    async def close(self) -> None:
        if self._reader_task:
            self._reader_task.cancel()
        if self._writer:
            try:
                self._writer.close()
            except OSError:
                pass
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=1)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    self._proc.kill()
                except OSError:
                    pass


class HTTPTransport(_BaseTransport):
    """Remote HTTP / streamable-http MCP server."""

    def __init__(self, config: MCPServerConfig, read_timeout: float = 30.0):
        self.config = config
        self.read_timeout = read_timeout
        self._client: httpx.AsyncClient | None = None
        self._notify_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._session_id: str | None = None

    async def connect(self) -> None:
        headers = dict(self.config.headers)
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        self._client = httpx.AsyncClient(headers=headers, timeout=self.read_timeout)
        url = self.config.url or ""
        # streamable-http: POST to the URL; session id returned in Mcp-Session-Id header.
        resp = await self._client.post(
            url, json={"jsonrpc": "2.0", "method": "initialize", "params": {}, "id": "0"}
        )
        self._session_id = resp.headers.get("mcp-session-id") or self._session_id

    async def send(self, message: dict[str, Any]) -> dict[str, Any]:
        assert self._client is not None
        headers: dict[str, str] = {}
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        resp = await self._client.post(self.config.url or "", json=message, headers=headers)
        if resp.status_code >= 400:
            raise MCPConnectionError(f"HTTP server '{self.config.name}' returned {resp.status_code}")
        return resp.json()

    async def notifications(self) -> asyncio.Queue[dict[str, Any]]:
        return self._notify_queue

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()


class SSETransport(_BaseTransport):
    """Remote client for the legacy MCP SSE transport."""

    def __init__(self, config: MCPServerConfig, read_timeout: float = 30.0):
        self.config = config
        self.read_timeout = read_timeout
        self._client: httpx.AsyncClient | None = None
        self._notify_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._listen_task: asyncio.Task | None = None
        self._endpoint_ready = asyncio.Event()
        self._message_endpoint: str | None = None
        self._pending: dict[Any, asyncio.Future[dict[str, Any]]] = {}
        self._stream_error: Exception | None = None

    async def connect(self) -> None:
        self._client = httpx.AsyncClient(timeout=self.read_timeout)
        self._listen_task = asyncio.create_task(self._sse_listen())
        try:
            await asyncio.wait_for(self._endpoint_ready.wait(), timeout=self.read_timeout)
        except TimeoutError as exc:
            await self.close()
            raise MCPConnectionError(
                f"SSE server '{self.config.name}' did not advertise a message endpoint"
            ) from exc
        if self._message_endpoint is None:
            error = self._stream_error or MCPConnectionError(
                "SSE stream closed before endpoint was advertised"
            )
            await self.close()
            raise MCPConnectionError(f"SSE server '{self.config.name}' failed: {error}") from error

    async def _dispatch_sse_event(self, event: str, data: str) -> None:
        if event == "endpoint":
            self._message_endpoint = urljoin(self.config.url or "", data)
            self._endpoint_ready.set()
            return
        if event != "message":
            return
        try:
            message = json.loads(data)
        except json.JSONDecodeError:
            return
        message_id = message.get("id")
        if "method" in message and message_id is None:
            await self._notify_queue.put(message)
            return
        future = self._pending.pop(message_id, None)
        if future is not None and not future.done():
            future.set_result(message)

    async def _sse_listen(self) -> None:
        assert self._client is not None
        event = "message"
        data_lines: list[str] = []
        try:
            async with self._client.stream(
                "GET",
                self.config.url or "",
                headers={"Accept": "text/event-stream", **self.config.headers},
            ) as stream:
                stream.raise_for_status()
                async for line in stream.aiter_lines():
                    if not line:
                        if data_lines:
                            await self._dispatch_sse_event(event, "\n".join(data_lines))
                        event = "message"
                        data_lines = []
                    elif line.startswith(":"):
                        continue
                    elif line.startswith("event:"):
                        event = line[6:].strip()
                    elif line.startswith("data:"):
                        data_lines.append(line[5:].lstrip())
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._stream_error = exc
        finally:
            self._endpoint_ready.set()
            error = MCPConnectionError(f"SSE stream for '{self.config.name}' closed")
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(error)
            self._pending.clear()

    async def send(self, message: dict[str, Any]) -> dict[str, Any]:
        if self._client is None or self._message_endpoint is None:
            raise MCPConnectionError(f"SSE server '{self.config.name}' is not connected")
        message_id = message.get("id")
        future: asyncio.Future[dict[str, Any]] | None = None
        if message_id is not None:
            future = asyncio.get_running_loop().create_future()
            self._pending[message_id] = future
        try:
            response = await self._client.post(
                self._message_endpoint,
                json=message,
                headers=self.config.headers,
            )
            if response.status_code >= 400:
                raise MCPConnectionError(f"SSE server '{self.config.name}' returned {response.status_code}")
            if future is None:
                return {}
            return await asyncio.wait_for(future, timeout=self.read_timeout)
        except Exception:
            if future is not None and self._pending.get(message_id) is future:
                self._pending.pop(message_id, None)
            raise

    async def notifications(self) -> asyncio.Queue[dict[str, Any]]:
        return self._notify_queue

    async def close(self) -> None:
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
            self._listen_task = None
        if self._client:
            await self._client.aclose()
            self._client = None


class WebSocketTransport(_BaseTransport):
    """Remote WebSocket MCP server (persistent bidirectional)."""

    def __init__(self, config: MCPServerConfig, read_timeout: float = 30.0):
        self.config = config
        self.read_timeout = read_timeout
        self._ws: Any = None
        self._notify_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._listen_task: asyncio.Task | None = None
        self._pending: dict[str, asyncio.Future] = {}

    async def connect(self) -> None:
        # Lazy import websockets so it is optional.
        try:
            import websockets
        except ImportError as exc:
            raise MCPConnectionError("websockets package is required for WebSocket MCP transport") from exc

        self._ws = await websockets.connect(self.config.url or "", extra_headers=self.config.headers)
        self._listen_task = asyncio.create_task(self._ws_listen())

    async def _ws_listen(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                msg_id = msg.get("id")
                if "method" in msg and msg_id is None:
                    await self._notify_queue.put(msg)
                elif msg_id and msg_id in self._pending:
                    fut = self._pending.pop(msg_id)
                    if not fut.done():
                        fut.set_result(msg)
        except Exception:
            pass

    async def send(self, message: dict[str, Any]) -> dict[str, Any]:
        assert self._ws is not None
        req_id = message.get("id")
        if not isinstance(req_id, str):
            req_id = str(req_id) if req_id is not None else "0"
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[req_id] = fut
        await self._ws.send(json.dumps(message))
        try:
            return await asyncio.wait_for(fut, timeout=self.read_timeout)
        except TimeoutError:
            self._pending.pop(req_id, None)
            raise MCPConnectionError(f"WebSocket server '{self.config.name}' timed out") from None

    async def notifications(self) -> asyncio.Queue[dict[str, Any]]:
        return self._notify_queue

    async def close(self) -> None:
        if self._listen_task:
            self._listen_task.cancel()
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass


def _make_transport(config: MCPServerConfig, cwd: Path) -> _BaseTransport:
    t = config.type.lower()
    if t == "stdio":
        return StdioTransport(config, cwd)
    if t == "http":
        return HTTPTransport(config)
    if t == "sse":
        return SSETransport(config)
    if t in ("websocket", "ws"):
        return WebSocketTransport(config)
    raise MCPError(f"Unknown MCP transport type: {config.type}")


# ---------------------------------------------------------------------------
# MCP client
# ---------------------------------------------------------------------------


class MCPClient:
    """Manages MCP server connections, discovery, and tool invocation.

    Servers are configured via MCPServerConfig. The client connects lazily,
    discovers capabilities, caches tool lists, and routes tool calls to the
    right server. list_changed notifications trigger re-discovery.
    """

    def __init__(self, cwd: Path | None = None, max_concurrent: int = 16):
        self.cwd = Path(cwd or Path.cwd()).resolve()
        self.max_concurrent = max_concurrent
        self._servers: dict[str, MCPServerConfig] = {}
        self._transports: dict[str, _BaseTransport] = {}
        self._capabilities: dict[str, MCPCapability] = {}
        self._connected: dict[str, bool] = {}
        self._connect_locks: dict[str, asyncio.Lock] = {}
        self._notify_tasks: dict[str, asyncio.Task] = {}
        self._reconnect_tasks: dict[str, asyncio.Task] = {}
        self._session_lock = asyncio.Lock()

    # -- configuration -----------------------------------------------------

    def add_server(self, config: MCPServerConfig) -> None:
        if config.disabled:
            return
        if config.name.lower() in {n.lower() for n in _RESERVED_NAMES}:
            raise MCPError(f"Reserved MCP server name: {config.name}")
        self._servers[config.name] = config
        self._connect_locks[config.name] = asyncio.Lock()

    def remove_server(self, name: str) -> None:
        self._servers.pop(name, None)
        self._connected.pop(name, None)
        self._capabilities.pop(name, None)
        task = self._notify_tasks.pop(name, None)
        if task:
            task.cancel()
        task = self._reconnect_tasks.pop(name, None)
        if task:
            task.cancel()

    def list_servers(self) -> dict[str, MCPServerConfig]:
        return dict(self._servers)

    def server_status(self, name: str) -> str:
        if name not in self._servers:
            return "not configured"
        if self._servers[name].disabled:
            return "disabled"
        if not self._connected.get(name):
            return "not connected"
        return "connected"

    # -- connection --------------------------------------------------------

    async def _ensure_connected(self, name: str) -> _BaseTransport:
        async with self._connect_locks[name]:
            if self._connected.get(name) and name in self._transports:
                return self._transports[name]
            config = self._servers[name]
            transport = _make_transport(config, self.cwd)
            try:
                await transport.connect()
            except Exception as exc:
                raise MCPConnectionError(f"Failed to connect to MCP server '{name}': {exc}") from exc
            self._transports[name] = transport
            self._connected[name] = True
            # Start notification listener.
            self._notify_tasks[name] = asyncio.create_task(self._notification_loop(name, transport))
            return transport

    async def _notification_loop(self, name: str, transport: _BaseTransport) -> None:
        queue = await transport.notifications()
        while True:
            try:
                msg = await queue.get()
            except asyncio.CancelledError:
                return
            method = msg.get("method", "")
            if method == "notifications/tools/list_changed":
                async with self._session_lock:
                    try:
                        await self.discover(name)
                    except Exception:
                        pass  # keep old capabilities on discovery failure
            elif method.startswith("notifications/"):
                # Other notifications are ignored for now.
                pass

    async def connect(self, name: str) -> None:
        await self._ensure_connected(name)

    async def disconnect(self, name: str) -> None:
        transport = self._transports.pop(name, None)
        self._connected[name] = False
        task = self._notify_tasks.pop(name, None)
        if task:
            task.cancel()
        if transport:
            try:
                await transport.close()
            except Exception:
                pass

    async def disconnect_all(self) -> None:
        for name in list(self._transports):
            await self.disconnect(name)

    # -- discovery ---------------------------------------------------------

    async def discover(self, name: str) -> MCPCapability:
        transport = await self._ensure_connected(name)
        result = await transport.send(_rpc_request("tools/list"))
        tools_raw = result.get("tools", []) if isinstance(result, dict) else []
        tools = [
            MCPTool(
                name=t.get("name", ""),
                description=t.get("description", ""),
                input_schema=t.get("inputSchema", {}) or {},
                server=name,
                annotations=t.get("annotations", {}) or {},
            )
            for t in tools_raw
        ]
        caps = MCPCapability(tools=tools)
        self._capabilities[name] = caps
        return caps

    async def discover_all(self) -> dict[str, MCPCapability]:
        for name in self._servers:
            if self._connected.get(name):
                try:
                    await self.discover(name)
                except Exception:
                    pass
        return dict(self._capabilities)

    def get_tools(self, name: str) -> list[MCPTool]:
        return list(self._capabilities.get(name, MCPCapability()).tools)

    def find_tool(self, full_name: str) -> tuple[str, MCPTool] | None:
        """Resolve an mcp__<server>__<tool> name to (server, tool)."""
        parts = full_name.split("__", 2)
        if len(parts) != 3 or parts[0] != "mcp":
            return None
        server, tool_name = parts[1], parts[2]
        if server not in self._capabilities:
            return None
        for t in self._capabilities[server].tools:
            if t.name == tool_name:
                return server, t
        return None

    # -- invocation --------------------------------------------------------

    async def call_tool(self, server: str, tool: str, arguments: dict[str, Any]) -> Any:
        transport = await self._ensure_connected(server)
        params = {"name": tool, "arguments": arguments}
        result = await transport.send(_rpc_request("tools/call", params))
        return _rpc_result(result)

    async def call_tool_full_name(self, full_name: str, arguments: dict[str, Any]) -> Any:
        resolved = self.find_tool(full_name)
        if not resolved:
            raise MCPError(f"Unknown MCP tool: {full_name}")
        server, tool = resolved
        return await self.call_tool(server, tool.name, arguments)

    # -- lifecycle ---------------------------------------------------------

    async def reconnect_failed(self) -> None:
        """Retry all failed servers (called by /mcp reconnect all)."""
        for name in list(self._servers):
            if not self._connected.get(name):
                try:
                    await self.disconnect(name)
                except Exception:
                    pass
                try:
                    await self.connect(name)
                    await self.discover(name)
                except Exception:
                    pass

    async def aclose(self) -> None:
        await self.disconnect_all()


# ---------------------------------------------------------------------------
# CLI helpers (thin, no rendering)
# ---------------------------------------------------------------------------


def mcp_config_entry(name: str, **kwargs: Any) -> dict[str, Any]:
    """Build a .mcp.json entry dict for one server."""
    entry: dict[str, Any] = {}
    if "command" in kwargs:
        entry["command"] = kwargs["command"]
        entry["args"] = kwargs.get("args", [])
    if "url" in kwargs:
        entry["url"] = kwargs["url"]
    if "type" in kwargs:
        entry["type"] = kwargs["type"]
    if kwargs.get("env"):
        entry["env"] = kwargs["env"]
    if kwargs.get("headers"):
        entry["headers"] = kwargs["headers"]
    if kwargs.get("timeout") is not None:
        entry["timeout"] = kwargs["timeout"]
    return {name: entry}


def stdio_entry(
    name: str, command: str, args: list[str] | None = None, env: dict[str, str] | None = None
) -> dict[str, Any]:
    return mcp_config_entry(name, command=command, args=args or [], env=env or {}, type="stdio")


def http_entry(name: str, url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    return mcp_config_entry(name, url=url, headers=headers or {}, type="http")


def sse_entry(name: str, url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    return mcp_config_entry(name, url=url, headers=headers or {}, type="sse")


def ws_entry(name: str, url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    return mcp_config_entry(name, url=url, headers=headers or {}, type="websocket")
