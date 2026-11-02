"""web.py — secured browser GUI backend for the code agent (FastAPI + WebSocket).

Threat model: the agent can edit files and run shell commands, so this server is as sensitive as a shell.
Defences, all on by default:

* binds to loopback unless ``--allow-remote`` is given, and *always* requires a bearer token
* Host-header allow-list (DNS-rebinding) and WebSocket Origin allow-list (cross-site WebSocket hijacking)
* token compared in constant time; repeated failures per client are throttled
* strict CSP / no-sniff / no-frame / no-referrer headers, ``no-store`` on the API
* bypass-permissions mode can never be enabled from the browser
* every edit/command still needs an explicit approval click (or an allow rule), identical to the TUI
* connection cap, prompt size cap, per-connection prompt rate limit, approval timeout (fails closed)
* error details are logged server-side; clients only ever see generic messages
"""

from __future__ import annotations

import asyncio
import hmac
import ipaddress
import json
import logging
import os
import secrets
import time
import urllib.parse
from collections import defaultdict, deque
from collections.abc import Callable
from contextlib import aclosing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from zcoder.agent.codeagent.commands import dispatch, list_commands
from zcoder.agent.codeagent.events import (
    Decision,
    ModeChanged,
    PermissionRequest,
    TodoUpdate,
    ToolStart,
    TurnDone,
    UsageUpdate,
    event_to_dict,
)
from zcoder.agent.codeagent.factory import build_agent
from zcoder.agent.codeagent.loop import AskFn, CodeAgent
from zcoder.agent.codeagent.memory import mention_candidates
from zcoder.agent.codeagent.permissions import Mode, rule_for
from zcoder.agent.codeagent.sessions import SessionStore
from zcoder.agent.codeagent.tools import describe_call
from zcoder.agent.codeagent.workspace import ToolError

log = logging.getLogger("zcoder.agent.web")
VERSION = "1.0.0"
LOOPBACK_NAMES = {"localhost", "127.0.0.1", "::1"}
MAX_WS_MESSAGE = 400_000
_DECISIONS = {"allow", "allow_session", "deny"}
CommandSafeWhileBusy = {
    "/status",
    "/cost",
    "/todos",
    "/tools",
    "/help",
    "/memory",
    "/permissions",
    "/model",
    "/sessions",
}


def is_loopback(host: str) -> bool:
    if host in LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@dataclass
class WebConfig:
    root: Path
    token: str
    host: str = "127.0.0.1"
    port: int = 8421
    extra_origins: tuple[str, ...] = ()
    extra_hosts: tuple[str, ...] = ()
    max_connections: int = 4
    max_prompt_chars: int = 100_000
    prompts_per_minute: int = 30
    permission_timeout: float = 600.0
    frontend_dir: Path | None = None
    agent_factory: Callable[[AskFn | None], CodeAgent] | None = None
    store: SessionStore | None = None
    allowed_hosts: set[str] = field(default_factory=set)
    allowed_origins: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        if len(self.token) < 16:
            raise ValueError("web token must be at least 16 characters")
        self.root = Path(self.root).resolve()
        names = {self.host, *LOOPBACK_NAMES, *self.extra_hosts}
        self.allowed_hosts = {n.strip("[]").lower() for n in names}
        origins = set(self.extra_origins)
        for name in names:
            shown = f"[{name}]" if ":" in name else name
            origins.add(f"http://{shown}:{self.port}")
        self.allowed_origins = origins
        if self.agent_factory is None:
            root = self.root
            self.agent_factory = lambda ask: build_agent(root, ask=ask, allow_bypass=False)
        if self.frontend_dir is None:
            env = os.getenv("ZCODER_AGENT_FRONTEND")
            self.frontend_dir = (
                Path(env) if env else Path(__file__).resolve().parents[4] / "webapp" / "frontend" / "agent"
            )


def generate_token() -> str:
    return secrets.token_urlsafe(32)


class AuthLimiter:
    """Throttle repeated bad-token attempts per client address."""

    def __init__(self, max_failures: int = 10, window: float = 60.0) -> None:
        self.max, self.window = max_failures, window
        self._fails: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str) -> deque[float]:
        q = self._fails[key]
        now = time.monotonic()
        while q and now - q[0] > self.window:
            q.popleft()
        return q

    def blocked(self, key: str) -> bool:
        return len(self._prune(key)) >= self.max

    def fail(self, key: str) -> None:
        self._prune(key).append(time.monotonic())


# ----------------------------------------------------------------------------- ASGI middleware
class HostGuard:
    """Reject requests whose Host header is not an allowed name (defeats DNS rebinding)."""

    def __init__(self, app: Any, allowed: set[str]) -> None:
        self.app, self.allowed = app, allowed

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] in {"http", "websocket"}:
            raw = dict(scope["headers"]).get(b"host", b"").decode("latin-1")
            host = (urllib.parse.urlsplit("//" + raw).hostname or "").lower()
            if host not in self.allowed:
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 1008})
                else:
                    await Response("Invalid host header", status_code=400)(scope, receive, send)
                return
        await self.app(scope, receive, send)


class SecurityHeaders:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        host = dict(scope["headers"]).get(b"host", b"").decode("latin-1")
        csp = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            f"connect-src 'self' ws://{host} wss://{host}; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
        )
        api = scope["path"].startswith("/api/")

        async def wrapped(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                extra = {
                    "content-security-policy": csp,
                    "x-content-type-options": "nosniff",
                    "x-frame-options": "DENY",
                    "referrer-policy": "no-referrer",
                    "cross-origin-opener-policy": "same-origin",
                    "cross-origin-resource-policy": "same-origin",
                    "permissions-policy": "camera=(), microphone=(), geolocation=()",
                }
                if api:
                    extra["cache-control"] = "no-store"
                names = {k.lower() for k, _ in headers}
                headers += [(k.encode(), v.encode()) for k, v in extra.items() if k.encode() not in names]
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, wrapped)


# ----------------------------------------------------------------------------- helpers
def public_args(args: dict[str, Any]) -> dict[str, Any]:
    """Tool arguments safe to push to the browser (file bodies are summarised, long strings cut)."""
    out: dict[str, Any] = {}
    for k, v in args.items():
        if isinstance(v, str):
            out[k] = v if len(v) <= 2000 else f"{v[:2000]}… [{len(v)} chars]"
        elif isinstance(v, int | float | bool) or v is None:
            out[k] = v
        else:
            out[k] = json.dumps(v, default=str)[:2000]
    if "content" in args and isinstance(args["content"], str):
        out["content"] = f"<{len(args['content'])} chars>"
    return out


def history_for_client(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for m in messages:
        role, content = m.get("role"), m.get("content")
        if role == "user" and isinstance(content, str):
            rows.append({"role": "user", "text": content.split("\n\n<file path=")[0]})
        elif role == "assistant":
            rows.append(
                {
                    "role": "assistant",
                    "text": content or "",
                    "tools": [tc["function"]["name"] for tc in m.get("tool_calls") or []],
                }
            )
    return rows


def _safe_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


# ----------------------------------------------------------------------------- one browser connection
class Connection:
    def __init__(self, ws: WebSocket, cfg: WebConfig) -> None:
        self.ws, self.cfg = ws, cfg
        self.pending: dict[str, asyncio.Future[Decision]] = {}
        self.turn: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._stamps: deque[float] = deque()
        assert cfg.agent_factory is not None
        self.agent: CodeAgent = cfg.agent_factory(self.ask)
        self.agent.ask = self.ask  # factories that ignore the argument still get the web prompt
        try:
            if self.agent.policy.mode == Mode.BYPASS:  # never allowed over the web
                self.agent.policy.mode = Mode.DEFAULT
            self.agent.policy.allow_bypass = False
        except Exception:  # pragma: no cover - defensive
            pass

    async def send(self, payload: dict[str, Any]) -> bool:
        try:
            async with self._lock:
                await self.ws.send_json(payload)
            return True
        except (RuntimeError, WebSocketDisconnect, ConnectionError):
            return False

    async def ask(self, req: PermissionRequest) -> Decision:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Decision] = loop.create_future()
        self.pending[req.id] = fut
        tool = self.agent.tools.get(req.tool)
        rule = rule_for(tool, req.args) if tool else None
        sent = await self.send(
            {
                "type": "permission",
                "id": req.id,
                "tool": req.tool,
                "summary": req.summary,
                "diff": req.diff,
                "reason": req.reason,
                "session_rule": rule,
                "is_plan": req.tool == "ExitPlanMode",
            }
        )
        if not sent:
            self.pending.pop(req.id, None)
            raise ConnectionError("client gone")
        try:
            return await asyncio.wait_for(fut, self.cfg.permission_timeout)
        except TimeoutError:
            return Decision("deny", "Approval timed out.")
        finally:
            self.pending.pop(req.id, None)

    def deny_all_pending(self, why: str = "Interrupted.") -> None:
        for fut in list(self.pending.values()):
            if not fut.done():
                fut.set_result(Decision("deny", why))

    def state(self, busy: bool | None = None) -> dict[str, Any]:
        a = self.agent
        return {
            "type": "state",
            "mode": a.mode.value,
            "session_id": a.session_id,
            "todos": list(a.todos),
            "usage": {
                "prompt": a.usage.prompt_tokens,
                "completion": a.usage.completion_tokens,
                "context_pct": min(99, int(100 * a.estimate_tokens() / max(a.context_window, 1))),
            },
            "busy": self.busy if busy is None else busy,
        }

    def wire(self, ev: Any) -> dict[str, Any]:
        data = event_to_dict(ev)
        if isinstance(ev, ToolStart):
            data["args"] = public_args(ev.args)
            data["title"] = describe_call(ev.name, ev.args)
        return data

    async def run_turn(self, text: str, display: str | None = None) -> None:
        await self.send({"type": "user", "text": display or text})
        try:
            async with aclosing(self.agent.run(text)) as events:
                async for ev in events:
                    if not await self.send(self.wire(ev)):
                        self.agent.interrupt()
                        break
                    if isinstance(ev, TodoUpdate | ModeChanged | UsageUpdate | TurnDone):
                        await self.send(self.state(busy=not isinstance(ev, TurnDone)))
        except asyncio.CancelledError:
            self.agent.interrupt()
            raise
        except Exception:
            log.exception("agent turn failed")
            await self.send(
                {"type": "notice", "level": "error", "text": "Internal error while running the agent."}
            )
            await self.send({"type": "done", "stop_reason": "error"})
        finally:
            await self.send(self.state(busy=False))

    def rate_limited(self) -> bool:
        now = time.monotonic()
        while self._stamps and now - self._stamps[0] > 60:
            self._stamps.popleft()
        if len(self._stamps) >= self.cfg.prompts_per_minute:
            return True
        self._stamps.append(now)
        return False

    @property
    def busy(self) -> bool:
        return bool(self.turn and not self.turn.done())

    async def notice(self, text: str, level: str = "warn") -> None:
        await self.send({"type": "notice", "level": level, "text": text})

    async def handle(self, msg: dict[str, Any]) -> None:
        kind = msg.get("type")
        if kind == "prompt":
            text = msg.get("text")
            if not isinstance(text, str) or not text.strip():
                return await self.notice("Empty prompt.")
            if len(text) > self.cfg.max_prompt_chars:
                return await self.notice(
                    f"Prompt too long (limit {self.cfg.max_prompt_chars} characters).", "error"
                )
            if self.busy:
                return await self.notice("The agent is working. Interrupt it first.")
            if self.rate_limited():
                return await self.notice("Rate limit reached; wait a moment.", "error")
            self.turn = asyncio.create_task(self.run_turn(text))
        elif kind == "permission":
            fut = self.pending.get(str(msg.get("id")))
            behavior, feedback = msg.get("behavior"), msg.get("feedback", "")
            if fut is None or fut.done() or behavior not in _DECISIONS or not isinstance(feedback, str):
                return await self.notice("Unknown or expired approval request.")
            fut.set_result(Decision(behavior, feedback[:2000]))
        elif kind == "interrupt":
            self.agent.interrupt()
            self.deny_all_pending()
        elif kind == "mode":
            await self.set_mode(msg.get("mode"))
        elif kind in {"command", "resume", "new"}:
            line = {"resume": f"/resume {msg.get('id', '')}", "new": "/clear"}.get(kind) or msg.get("line")
            if not isinstance(line, str) or not line.startswith("/") or len(line) > 2000:
                return await self.notice("Invalid command.")
            await self.command(line.strip())
        elif kind == "ping":
            await self.send({"type": "pong"})
        else:
            await self.notice("Unknown message type.")

    async def set_mode(self, mode: Any) -> None:
        if mode == "cycle":
            self.agent.policy.cycle_mode()
        else:
            try:
                self.agent.policy.set_mode(Mode(str(mode)))
            except (ValueError, ToolError):
                return await self.notice("That permission mode is not available in the browser.", "error")
        await self.send({"type": "mode", "mode": self.agent.mode.value})
        await self.send(self.state())

    async def command(self, line: str) -> None:
        name = line.split(" ", 1)[0].lower()
        if self.busy and name not in CommandSafeWhileBusy:
            return await self.notice("Interrupt the agent before running that command.")
        result = await dispatch(self.agent, line)
        await self.send(
            {
                "type": "command_result",
                "command": name,
                "output": result.output,
                "is_error": result.is_error,
                "action": result.action,
            }
        )
        if result.action == "resumed":
            await self.send({"type": "history", "messages": history_for_client(self.agent.messages)})
        elif result.action == "prompt" and result.prompt:
            self.turn = asyncio.create_task(self.run_turn(result.prompt, display=line))
        elif result.action == "exit":
            await self.notice("Close the browser tab to leave.", "info")
        await self.send(self.state())

    async def close(self) -> None:
        self.agent.interrupt()
        self.deny_all_pending("Connection closed.")
        if self.turn and not self.turn.done():
            self.turn.cancel()
            try:
                await self.turn
            except (asyncio.CancelledError, Exception):
                pass


# ----------------------------------------------------------------------------- app assembly
def build_router(cfg: WebConfig) -> APIRouter:
    router = APIRouter(prefix="/api/agent")
    limiter = AuthLimiter()
    state: dict[str, Any] = {"connections": 0, "probe": None}

    def probe() -> CodeAgent:
        if state["probe"] is None:
            assert cfg.agent_factory is not None
            state["probe"] = cfg.agent_factory(None)
        return state["probe"]

    def client_key(request: Request) -> str:
        return request.client.host if request.client else "unknown"

    def require_auth(request: Request) -> None:
        key = client_key(request)
        if limiter.blocked(key):
            raise HTTPException(429, "Too many failed attempts")
        header = request.headers.get("authorization", "")
        if not header.lower().startswith("bearer ") or not _safe_equal(header[7:].strip(), cfg.token):
            limiter.fail(key)
            raise HTTPException(401, "Unauthorized", headers={"WWW-Authenticate": "Bearer"})

    @router.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/info")
    async def info(request: Request) -> JSONResponse:
        require_auth(request)
        agent = await asyncio.to_thread(probe)
        store = cfg.store or agent.store or SessionStore()
        sessions = [
            {"id": s.id, "title": s.title, "updated": s.updated, "turns": s.turns}
            for s in store.list(str(cfg.root))[:30]
        ]
        return JSONResponse(
            {
                "version": VERSION,
                "model": agent.llm.model,
                "cwd": str(cfg.root),
                "modes": ["default", "acceptEdits", "plan"],
                "commands": [{"name": c.name, "help": c.help, "usage": c.usage} for c in list_commands()],
                "sessions": sessions,
            }
        )

    @router.get("/files")
    async def files(request: Request, q: str = "") -> JSONResponse:
        require_auth(request)
        agent = await asyncio.to_thread(probe)
        found = await asyncio.to_thread(mention_candidates, agent.ws, q[:200], 30)
        return JSONResponse({"files": found})

    @router.delete("/sessions/{session_id}", status_code=204)
    async def delete_session(request: Request, session_id: str) -> Response:
        require_auth(request)
        agent = await asyncio.to_thread(probe)
        store = cfg.store or agent.store or SessionStore()
        try:
            store.delete(session_id)
        except ValueError:
            raise HTTPException(400, "Invalid session id") from None
        return Response(status_code=204)

    @router.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        origin = ws.headers.get("origin")
        if origin is not None and origin not in cfg.allowed_origins:
            await ws.close(code=4403)
            return
        key = ws.client.host if ws.client else "unknown"
        if limiter.blocked(key):
            await ws.close(code=4429)
            return
        if state["connections"] >= cfg.max_connections:
            await ws.close(code=4429)
            return
        await ws.accept()
        state["connections"] += 1
        conn: Connection | None = None
        try:
            try:
                first = json.loads(await asyncio.wait_for(ws.receive_text(), 10))
            except (TimeoutError, ValueError):
                await ws.close(code=4401)
                return
            if (
                not isinstance(first, dict)
                or first.get("type") != "auth"
                or not isinstance(first.get("token"), str)
                or not _safe_equal(first["token"], cfg.token)
            ):
                limiter.fail(key)
                await ws.close(code=4401)
                return
            conn = await asyncio.to_thread(Connection, ws, cfg)  # agent setup may probe the model server
            agent = conn.agent
            store = cfg.store or agent.store or SessionStore()
            await conn.send(
                {
                    "type": "ready",
                    "version": VERSION,
                    "model": agent.llm.model,
                    "cwd": str(cfg.root),
                    "mode": agent.mode.value,
                    "session_id": agent.session_id,
                    "warnings": list(getattr(agent.settings, "warnings", []) or []),
                    "commands": [{"name": c.name, "help": c.help, "usage": c.usage} for c in list_commands()],
                    "sessions": [
                        {"id": s.id, "title": s.title, "updated": s.updated, "turns": s.turns}
                        for s in store.list(str(cfg.root))[:30]
                    ],
                }
            )
            while True:
                raw = await ws.receive_text()
                if len(raw) > MAX_WS_MESSAGE:
                    await conn.notice("Message too large.", "error")
                    continue
                try:
                    msg = json.loads(raw)
                except ValueError:
                    await conn.notice("Malformed message.", "error")
                    continue
                if isinstance(msg, dict):
                    await conn.handle(msg)
        except WebSocketDisconnect:
            pass
        except Exception:
            log.exception("websocket handler failed")
        finally:
            state["connections"] -= 1
            if conn:
                await conn.close()

    return router


def create_app(cfg: WebConfig) -> FastAPI:
    app = FastAPI(title="zcoder agent", version=VERSION, docs_url=None, redoc_url=None, openapi_url=None)
    app.include_router(build_router(cfg))
    if cfg.frontend_dir and cfg.frontend_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(cfg.frontend_dir), html=True), name="agent-frontend")
    app.add_middleware(SecurityHeaders)
    app.add_middleware(HostGuard, allowed=cfg.allowed_hosts)
    return app


def serve(root: Path, *, host: str = "127.0.0.1", port: int = 8421, allow_remote: bool = False) -> int:
    import sys

    if not is_loopback(host) and not allow_remote:
        print(
            f"error: refusing to bind {host}; use --allow-remote (and put TLS in front) to expose the agent",
            file=sys.stderr,
        )
        return 1
    try:
        import uvicorn
    except ImportError:
        print("error: the web GUI needs uvicorn:  pip install 'uvicorn[standard]' fastapi", file=sys.stderr)
        return 1
    try:  # without a WebSocket implementation uvicorn answers the upgrade with 404 and the GUI cannot connect
        import websockets  # noqa: F401
    except ImportError:
        try:
            import wsproto  # noqa: F401
        except ImportError:
            print("error: the web GUI needs a WebSocket library:  pip install websockets", file=sys.stderr)
            return 1
    token = os.getenv("ZCODER_WEB_TOKEN") or generate_token()
    try:
        cfg = WebConfig(root=root, token=token, host=host, port=port)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    shown = f"[{host}]" if ":" in host else host
    print(f"ZCoder agent web UI → http://{shown}:{port}/#token={token}")
    print("Open the full link once; the token is kept only in that browser tab. Press Ctrl+C to stop.")
    if not is_loopback(host):
        print(
            "WARNING: non-loopback bind. Anyone with the token can run commands as you; terminate TLS in front.",
            file=sys.stderr,
        )
    uvicorn.run(
        create_app(cfg),
        host=host,
        port=port,
        log_level="warning",
        server_header=False,
        ws_max_size=MAX_WS_MESSAGE,
    )
    return 0
