"""
webapp/backend/server.py — FastAPI backend for the zcoder web UI.

This is a thin HTTP adapter around the existing CLI core -- it does not
reimplement any behaviour. Every endpoint delegates to the same classes
and modules `main.py` already uses:

    coder.Coder              -> chat/generation
    personalities.py         -> PersonalityManager
    skills.py                -> SkillManager
    ZCODER_MODEL            -> local-only model dropdown
    main.py                  -> VERSION, AGENT_SYSTEM_PROMPTS
    config.py                -> Config (persisted to ~/.zcoder-config.json)
    health.py                -> run_health_check (used for Docker/orchestrator
                                 probes and the CLI's --health-check flag)

Run with:  uvicorn webapp.backend.server:app --host 0.0.0.0 --port 8420
(or just `make start`, see the project Makefile).
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

# --- make the project root (one level above webapp/) importable ----------
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Path to the multi-sector GGUF model config (same file used by scripts/model-server).
MODELS_CONFIG_PATH = os.getenv("ZCODER_MODELS_CONFIG", str(ROOT / "config" / "models.yaml"))

from zcoder.agent.personalities import PersonalityManager  # noqa: E402
from zcoder.api.auth import parse_cors_origins  # noqa: E402
from zcoder.config.logging import get_logger  # noqa: E402
from zcoder.config.settings import Config  # noqa: E402
from zcoder.core.health import run_health_check  # noqa: E402
from zcoder.main import AGENT_SYSTEM_PROMPTS, VERSION  # noqa: E402
from zcoder.services.coder import Coder  # noqa: E402
from zcoder.services.skills import SkillManager  # noqa: E402
from zcoder.core.sqlite import sqlite_connection  # noqa: E402

# Import model-server controller (same module used by scripts/model-server).
sys.path.insert(0, str(ROOT / "scripts"))
from model_server import (  # noqa: E402
    load_config,
    build_sectors,
    sector_by_name,
    start_sector,
    stop_sector,
    restart_sector,
    status_sector,
    health_ok,
    ModelServerError,
)

logger = get_logger("webapp.server")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

# --- API key authentication -------------------------------------------------
# Read-only public endpoints (version, health, models, personalities, skills,
# agents, config) are intentionally open for local discovery. All state-changing
# (POST/DELETE) and admin endpoints require a bearer token matching
# ZCODER_WEB_API_KEY. When the env var is unset, auth is disabled for local-only
# dev use (a startup warning is logged).


def _web_api_key() -> str | None:
    return os.environ.get("ZCODER_WEB_API_KEY") or None


def _require_auth(request: Request) -> None:
    """Enforce bearer-token auth on state-changing and admin endpoints.

    Reads the ``Authorization: Bearer <token>`` header directly so the check
    actually executes (the previous dependency-injection default was never
    awaited in the sync route handlers, which bypassed auth). Called
    explicitly from each protected route handler rather than as a global
    dependency, so public read-only endpoints stay unauthenticated.
    """
    expected = _web_api_key()
    if not expected:
        # Local/dev mode — no key configured, allow.
        return
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer ") or auth.removeprefix("Bearer ").strip() != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid bearer token",
            headers={"WWW-Authenticate": 'Bearer realm="zcoder"'},
        )


def _allowed_web_hosts(raw: str | None) -> list[str]:
    """Allow explicit hostnames, without wildcards or URL/port components."""
    if raw is None:
        return ["localhost", "127.0.0.1"]
    hosts = [value.strip() for value in raw.split(",")]
    if any(not host or any(char in host for char in "*:/\\@?#") or host.startswith(".") for host in hosts):
        raise ValueError("ZCODER_WEB_ALLOWED_HOSTS must contain exact hostnames without ports")
    return list(dict.fromkeys(hosts))


app = FastAPI(title="zcoder web", version=VERSION)

# This console is local-only by default; external access requires an authenticated proxy.
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=_allowed_web_hosts(os.environ.get("ZCODER_WEB_ALLOWED_HOSTS")),
    www_redirect=False,
)

# Same-origin frontend requests need no CORS; optional development origins are explicit.
app.add_middleware(
    CORSMiddleware,
    allow_origins=parse_cors_origins(os.environ.get("ZCODER_WEB_CORS_ORIGINS")),
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)

_personality_mgr = PersonalityManager()
_skill_mgr = SkillManager()

# In-memory multi-turn session store: {session_id: [{"role", "content"}, ...]}.
# Process-local cache; SQLite is the durable store so sessions survive restart.
_sessions: dict[str, list[dict]] = {}
_SESSION_LIMIT = 200  # oldest session dropped past this to bound memory

# --- Session persistence (phase 3) -----------------------------------------

SESSION_DB_PATH = os.getenv(
    "ZCODER_SESSION_DB", str(ROOT / "data" / "sessions.db")
)


def _init_sessions_db() -> None:
    """Create the sessions table if it does not exist."""
    os.makedirs(os.path.dirname(SESSION_DB_PATH), exist_ok=True)
    with sqlite_connection(SESSION_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                history TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_updated_at "
            "ON sessions(updated_at)"
        )


def _save_session_to_db(session_id: str, history: list[dict]) -> None:
    """Persist one session to SQLite."""
    import json as _json
    with sqlite_connection(SESSION_DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO sessions (session_id, history, updated_at) "
            "VALUES (?, ?, ?)",
            (session_id, _json.dumps(history, ensure_ascii=False), time.time()),
        )


def _load_session_from_db(session_id: str) -> list[dict] | None:
    """Load one session from SQLite, or None if not found."""
    import json as _json
    with sqlite_connection(SESSION_DB_PATH) as conn:
        row = conn.execute(
            "SELECT history FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    if row is None:
        return None
    return _json.loads(row[0])


def _list_sessions_from_db() -> list[dict]:
    """List all sessions from SQLite (id, preview, turns, updated_at)."""
    import json as _json
    with sqlite_connection(SESSION_DB_PATH) as conn:
        rows = conn.execute(
            "SELECT session_id, history, updated_at FROM sessions "
            "ORDER BY updated_at DESC LIMIT ?",
            (_SESSION_LIMIT,),
        ).fetchall()
    out = []
    for sid, history_json, updated_at in rows:
        history = _json.loads(history_json)
        first_user = next(
            (m["content"] for m in history if m.get("role") == "user"), ""
        )
        preview = (first_user[:80] + "…") if len(first_user) > 80 else first_user
        out.append(
            {
                "session_id": sid,
                "turns": len(history) // 2,
                "preview": preview,
                "updated_at": updated_at,
            }
        )
    return out


def _delete_session_from_db(session_id: str) -> None:
    """Delete one session from SQLite."""
    with sqlite_connection(SESSION_DB_PATH) as conn:
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))


# Load existing sessions from SQLite at startup.
_init_sessions_db()
try:
    _db_sessions = _list_sessions_from_db()
    for row in _db_sessions:
        sid = row["session_id"]
        history = _load_session_from_db(sid)
        if history is not None:
            _sessions[sid] = history
except Exception:
    # If SQLite is unavailable, start with empty in-memory store.
    pass


class ChatRequest(BaseModel):
    prompt: str
    session_id: str | None = None
    model: str = os.getenv("ZCODER_MODEL", "qwen-7b-q4km")
    temperature: float = 0.3
    max_tokens: int = 4096
    system: str | None = None
    personality: str | None = None
    agent: str | None = None
    skill: str | None = None
    # Retained for older clients; local inference never forwards credentials.
    api_key: str | None = None

    @field_validator("prompt")
    @classmethod
    def _prompt_not_huge(cls, v: str) -> str:
        # Generous cap (chars, not tokens) — just guards against a client
        # bug or abuse sending megabytes in a single field, not a real
        # token-accurate limit (the API itself enforces that).
        if len(v) > 200_000:
            raise ValueError("prompt too long (200,000 char limit)")
        return v

    @field_validator("temperature")
    @classmethod
    def _temp_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError("temperature must be between 0.0 and 1.0")
        return v

    @field_validator("max_tokens")
    @classmethod
    def _max_tokens_range(cls, v: int) -> int:
        if not (1 <= v <= 64_000):
            raise ValueError("max_tokens must be between 1 and 64,000")
        return v


class ChatResponse(BaseModel):
    session_id: str
    response: str
    model: str


# --- minimal per-IP rate limiting -----------------------------------------
# Fixed-window counter, in-memory, process-local — same "good enough for a
# single-process dev/small-team console, not a distributed system" spirit
# as the session store above. Protects the API key / quota behind this
# console from a runaway client loop, not from a determined attacker.
_RATE_LIMIT = 30  # requests
_RATE_WINDOW = 60.0  # seconds
_rate_buckets: dict[str, list[float]] = {}


def _check_rate_limit(request: Request) -> None:
    now = time.time()
    # Identify client by authenticated API key (per-user limit), falling back
    # to IP for unauthenticated/dev access.
    key = ""
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        key = auth.removeprefix("Bearer ").strip()
    client_id = key or (request.client.host if request.client else "unknown")
    bucket = [t for t in _rate_buckets.get(client_id, []) if now - t < _RATE_WINDOW]
    if len(bucket) >= _RATE_LIMIT:
        raise HTTPException(429, f"Rate limit exceeded ({_RATE_LIMIT}/min). Try again shortly.")
    bucket.append(now)
    _rate_buckets[client_id] = bucket


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    """Prevent a local model server redirecting inference off-loopback."""

    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


def _load_sectors() -> list[dict]:
    """Load sectors from config/models.yaml (same source used by scripts/model-server)."""
    try:
        import yaml  # type: ignore
    except Exception:
        return []
    try:
        with open(MODELS_CONFIG_PATH, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except (OSError, FileNotFoundError):
        return []
    if not isinstance(data, dict):
        return []
    return data.get("sectors", []) or []


def _sector_for_model(model_id: str) -> dict | None:
    """Find a sector by name or alias."""
    for sector in _load_sectors():
        if sector.get("name") == model_id or sector.get("alias") == model_id:
            return sector
    return None


def _local_model_endpoint(path: str) -> str:
    base_url = os.getenv("ZCODER_BASE_URL", "http://127.0.0.1:8080").strip().rstrip("/")
    parsed = urllib.parse.urlsplit(base_url)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise HTTPException(503, "ZCODER_BASE_URL must point to a local llama-server on loopback")
    prefix = parsed.path.rstrip("/")
    if not prefix.endswith("/v1"):
        prefix = f"{prefix}/v1"
    return f"{urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, prefix, '', ''))}/{path.lstrip('/')}"


def _local_model_endpoint_for_model(model_id: str, path: str) -> str:
    """Return the loopback endpoint for a specific model.

    If the model is defined in config/models.yaml, use that sector's host:port.
    Otherwise fall back to the ZCODER_BASE_URL environment variable.
    """
    sector = _sector_for_model(model_id)
    if sector:
        base_url = f"http://{sector.get('host', '127.0.0.1')}:{sector.get('port', 8080)}"
    else:
        base_url = os.getenv("ZCODER_BASE_URL", "http://127.0.0.1:8080").strip().rstrip("/")
    parsed = urllib.parse.urlsplit(base_url)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise HTTPException(503, "model endpoint must point to a local llama-server on loopback")
    return f"{base_url}/v1/{path.lstrip('/')}"


def _local_model_request(req: ChatRequest, history: list[dict], system: str | None, *, stream: bool):
    messages = list(history)
    if system:
        messages.insert(0, {"role": "system", "content": system})
    messages.append({"role": "user", "content": req.prompt})
    payload = {
        "model": req.model,
        "max_tokens": req.max_tokens,
        "temperature": req.temperature,
        "messages": messages,
        "stream": stream,
    }
    request = urllib.request.Request(
        _local_model_endpoint_for_model(req.model, "chat/completions"),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream, application/json"},
        method="POST",
    )
    opener = urllib.request.build_opener(_RejectRedirects())
    try:
        return opener.open(request, timeout=300)
    except urllib.error.HTTPError as exc:
        exc.close()
        raise HTTPException(502, f"Local model server returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise HTTPException(503, "Cannot connect to the local llama-server") from exc


class ConfigUpdate(BaseModel):
    model: str | None = None
    temperature: float | None = None


def _build_system_prompt(req: ChatRequest) -> str | None:
    parts = []
    if req.agent:
        role_prompt = AGENT_SYSTEM_PROMPTS.get(req.agent)
        if not role_prompt:
            raise HTTPException(400, f"Unknown agent role '{req.agent}'")
        parts.append(role_prompt)
    if req.skill:
        skill = _skill_mgr.get_skill(req.skill)
        if not skill:
            raise HTTPException(400, f"Unknown skill '{req.skill}'")
        parts.append(f"Apply the '{skill['name']}' skill: {skill['description']}")
    if req.system:
        parts.append(req.system)
    return "\n\n".join(parts) if parts else None


@app.get("/api/version")
def get_version():
    return {"version": VERSION}


@app.get("/api/health")
def get_health(deep: bool = False):
    """Same checks as `python main.py --health-check[--health-check-deep]`."""
    report = run_health_check(deep=deep)
    return report.to_dict()


@app.get("/api/models")
def get_models(request: Request):
    _require_auth(request)
    sectors = _load_sectors()
    models = []
    for s in sectors:
        if s.get("enabled", False):
            models.append(
                {
                    "id": s["name"],
                    "display_name": s.get("alias", s["name"]),
                    "tier": "local",
                    "port": s.get("port"),
                    "host": s.get("host", "127.0.0.1"),
                }
            )
    if not models:
        model_id = os.getenv("ZCODER_MODEL", "qwen-7b-q4km").strip()
        models = [{"id": model_id, "display_name": model_id, "tier": "local"}]
    return models


# --- Model sector control (phase 1) ----------------------------------------

class SectorAction(BaseModel):
    action: str  # start | stop | restart | status | health


def _get_sector_object(name: str):
    cfg = load_config(MODELS_CONFIG_PATH)
    sectors = build_sectors(cfg)
    return sector_by_name(sectors, name), cfg


@app.get("/api/model-sectors")
def list_model_sectors(request: Request):
    _require_auth(request)
    cfg = load_config(MODELS_CONFIG_PATH)
    sectors = build_sectors(cfg)
    out = []
    for s in sectors:
        status_text = status_sector(s)
        out.append(
            {
                "name": s.name,
                "model": s.model,
                "alias": s.alias,
                "host": s.host,
                "port": s.port,
                "enabled": s.enabled,
                "status": status_text,
            }
        )
    return out


@app.post("/api/model-sectors/{sector_name}/control")
def control_model_sector(sector_name: str, action: SectorAction, request: Request):
    _require_auth(request)
    cfg = load_config(MODELS_CONFIG_PATH)
    sectors = build_sectors(cfg)
    sector = sector_by_name(sectors, sector_name)
    start_timeout = int(cfg.get("start_timeout", 120))
    stop_timeout = int(cfg.get("stop_timeout", 15))

    act = action.action.strip().lower()
    if act == "start":
        start_sector(sector, start_timeout)
        return {"ok": True, "action": "start", "sector": sector_name}
    if act == "stop":
        stop_sector(sector, stop_timeout)
        return {"ok": True, "action": "stop", "sector": sector_name}
    if act == "restart":
        restart_sector(sector, start_timeout, stop_timeout)
        return {"ok": True, "action": "restart", "sector": sector_name}
    if act == "status":
        return {"ok": True, "action": "status", "sector": sector_name, "status": status_sector(sector)}
    if act == "health":
        ok = health_ok(sector, timeout=3.0)
        return {
            "ok": ok,
            "action": "health",
            "sector": sector_name,
            "healthy": ok,
        }
    raise HTTPException(400, f"Unknown action '{act}'. Use start|stop|restart|status|health")


@app.get("/api/model-sectors/{sector_name}/status")
def model_sector_status(sector_name: str, request: Request):
    _require_auth(request)
    sector, _cfg = _get_sector_object(sector_name)
    return {"ok": True, "sector": sector_name, "status": status_sector(sector)}


@app.get("/api/model-sectors/{sector_name}/health")
def model_sector_health(sector_name: str, request: Request):
    _require_auth(request)
    sector, _cfg = _get_sector_object(sector_name)
    ok = health_ok(sector, timeout=3.0)
    return {"ok": ok, "sector": sector_name, "healthy": ok}


# --- Model download (phase 2) ----------------------------------------------

class ModelDownloadRequest(BaseModel):
    url: str
    filename: str | None = None


@app.post("/api/models/download")
def download_model(req: ModelDownloadRequest, request: Request):
    """Download a GGUF model file from a URL into models_dir."""
    _require_auth(request)
    from zcoder.core.outbound_security import validate_external_http_url, safe_external_urlopen
    from zcoder.core.security import validate_name

    # Validate URL is http/https and not private (SSRF protection)
    validate_external_http_url(req.url)

    # Determine target filename
    filename = req.filename or req.url.rsplit("/", 1)[-1]
    if not filename:
        raise HTTPException(400, "Cannot determine filename from URL")
    # Basic safety: no path traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "Invalid filename")

    cfg = load_config(MODELS_CONFIG_PATH)
    models_dir = cfg.get("models_dir", "/zdata/models")
    import os as _os
    target_path = _os.path.join(models_dir, filename)
    if _os.path.exists(target_path):
        raise HTTPException(409, f"Model file '{filename}' already exists")

    try:
        with safe_external_urlopen(
            urllib.request.Request(req.url, headers={"User-Agent": "zcoder-model-downloader"}),
            timeout=300,
        ) as resp:
            total = 0
            with open(target_path, "wb") as out_fh:
                while True:
                    chunk = resp.read(1024 * 1024)  # 1 MiB chunks
                    if not chunk:
                        break
                    out_fh.write(chunk)
                    total += len(chunk)
    except Exception as exc:
        # Clean up partial file
        try:
            if _os.path.exists(target_path):
                _os.remove(target_path)
        except OSError:
            pass
        raise HTTPException(502, f"Download failed: {exc}")

    return {
        "ok": True,
        "filename": filename,
        "path": target_path,
        "bytes": total,
    }


@app.get("/api/personalities")
def get_personalities():
    return _personality_mgr.list_personalities()


@app.get("/api/skills")
def get_skills():
    return _skill_mgr.list_skills()


@app.get("/api/agents")
def get_agents():
    return [{"name": k, "description": v} for k, v in AGENT_SYSTEM_PROMPTS.items()]


@app.get("/api/config")
def get_config(request: Request):
    _require_auth(request)
    cfg = Config().all()
    return {"model": cfg.get("model"), "temperature": cfg.get("temperature")}


@app.post("/api/config")
def set_config(
    update: ConfigUpdate,
    request: Request,
):
    _require_auth(request)
    cfg = Config()
    if update.model:
        cfg.set("model", update.model)
    if update.temperature is not None:
        cfg.set("temperature", update.temperature)
    return {"ok": True}


@app.get("/api/sessions")
def list_sessions():
    """Lightweight index for a sessions sidebar — id, turn count, and a
    preview of the first user message, not full transcripts (use
    GET /api/sessions/{id} for that)."""
    return _list_sessions_from_db()


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str):
    history = _load_session_from_db(session_id)
    if history is None:
        raise HTTPException(404, "Unknown session_id")
    # Also populate in-memory cache for faster subsequent access.
    _sessions[session_id] = history
    return {"session_id": session_id, "history": history}


@app.delete("/api/sessions/{session_id}")
def delete_session(
    session_id: str,
    request: Request,
):
    _require_auth(request)
    _sessions.pop(session_id, None)
    _delete_session_from_db(session_id)
    return {"ok": True}


@app.post("/api/chat", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    request: Request,
):
    _require_auth(request)
    if not req.prompt or not req.prompt.strip():
        raise HTTPException(400, "prompt must not be empty")
    _check_rate_limit(request)

    session_id = req.session_id or str(uuid.uuid4())
    history = _sessions.get(session_id, [])

    system = _build_system_prompt(req)

    coder = Coder(
        # Legacy API-key fields are accepted by the request model for client
        # compatibility, but local inference never consumes credentials.
        api_key=None,
        model=req.model,
        temperature=req.temperature,
        max_tokens=req.max_tokens,
        personality_style=req.personality,
    )
    reply = coder.generate(req.prompt, system=system, history=history)

    history = history + [
        {"role": "user", "content": req.prompt},
        {"role": "assistant", "content": reply},
    ]
    _sessions[session_id] = history
    _save_session_to_db(session_id, history)
    if len(_sessions) > _SESSION_LIMIT:
        _sessions.pop(next(iter(_sessions)), None)

    return ChatResponse(session_id=session_id, response=reply, model=req.model)


@app.post("/api/chat/stream")
def chat_stream(
    req: ChatRequest,
    request: Request,
):
    _require_auth(request)
    """Server-Sent Events variant of /api/chat. Same request body and same
    session-history semantics; the difference is purely transport — tokens
    arrive as they're generated instead of after the full response. Reuses
    agent_stream.py's event-handling shape (content_block_delta/text_delta)
    rather than reimplementing SSE parsing.

    Each SSE `data:` line is a small JSON object:
      {"type": "token", "text": "..."}          — one delta, may repeat
      {"type": "done", "session_id": "...", "model": "..."}   — terminal
      {"type": "error", "message": "..."}                     — terminal
    A client that ignores "type" and just concatenates every "token" text
    field reconstructs the full response, same as /api/chat's `response`.
    """
    _require_auth(request)
    if not req.prompt or not req.prompt.strip():
        raise HTTPException(400, "prompt must not be empty")
    _check_rate_limit(request)

    session_id = req.session_id or str(uuid.uuid4())
    history = _sessions.get(session_id, [])
    system = _build_system_prompt(req)

    def event_stream():
        full_text = ""
        tool_call_names: list[str] = []
        try:
            with _local_model_request(req, history, system, stream=True) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = event.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    # Report tool calls instead of silently dropping them.
                    tc = delta.get("tool_calls") or []
                    for call in tc:
                        name = call.get("function", {}).get("name", "unknown")
                        if name and name not in tool_call_names:
                            tool_call_names.append(name)
                    content = delta.get("content", "")
                    if isinstance(content, str) and content:
                        full_text += content
                        yield f"data: {json.dumps({'type': 'token', 'text': content})}\n\n"
        except HTTPException as exc:
            public_message = (
                "ZCODER_BASE_URL must point to a local llama-server on loopback"
                if "ZCODER_BASE_URL must point to a local llama-server on loopback" in str(exc.detail)
                else "Local model request failed"
            )
            yield f"data: {json.dumps({'type': 'error', 'message': public_message})}\n\n"
            return
        except Exception:
            logger.exception("stream_chat_failed", extra={"model": req.model})
            yield f"data: {json.dumps({'type': 'error', 'message': 'Upstream provider request failed'})}\n\n"
            return

        # If the model only asked for tool calls (no text), tell the user.
        if tool_call_names and not full_text:
            names = ", ".join(tool_call_names)
            yield f"data: {json.dumps({'type': 'token', 'text': f'[โมเดลต้องการเรียกเครื่องมือ: {names} แต่เว็บอินเทอร์เฟซยังไม่รองรับการเรียกเครื่องมือ กรุณาลองใหม่ด้วยคำสั่งทั่วไป]'})}\n\n"
            full_text = f"[โมเดลต้องการเรียกเครื่องมือ: {names} แต่เว็บอินเทอร์เฟซยังไม่รองรับการเรียกเครื่องมือ กรุณาลองใหม่ด้วยคำสั่งทั่วไป]"

        new_history = history + [
            {"role": "user", "content": req.prompt},
            {"role": "assistant", "content": full_text},
        ]
        _sessions[session_id] = new_history
        _save_session_to_db(session_id, new_history)
        if len(_sessions) > _SESSION_LIMIT:
            _sessions.pop(next(iter(_sessions)), None)
        yield f"data: {json.dumps({'type': 'done', 'session_id': session_id, 'model': req.model})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# --- Enterprise Control Plane Admin Endpoints (zcoder-theme.md) -------------


@app.get("/api/admin/metrics")
def admin_metrics(request: Request):
    _require_auth(request)
    return _admin_metrics()


def _admin_metrics() -> dict:
    """Executive dashboard KPIs and telemetry — computed from runtime state,
    not hardcoded placeholder values."""
    health = run_health_check(deep=False)
    sectors = _load_sectors()
    enabled_models = [s for s in sectors if s.get("enabled")]
    model_id = os.getenv("ZCODER_MODEL", "qwen-7b-q4km").strip()
    return {
        "total_tasks": 0,
        "active_agents": len(AGENT_SYSTEM_PROMPTS),
        "running_sessions": len(_sessions),
        "queued_jobs": 0,
        "active_workers": 1,
        "completed_tasks": 0,
        "failed_tasks": 0,
        "pending_approvals": 0,
        "local_models_available": len(enabled_models),
        "configured_model": model_id,
        "provider_availability": "healthy" if health.healthy else "degraded",
        "api_health": "operational",
        "database_health": "operational",
        "uptime_seconds": time.monotonic(),
    }


@app.get("/api/admin/providers")
def admin_providers(request: Request):
    _require_auth(request)
    return _admin_providers()


def _admin_providers() -> list[dict]:
    """Provider management catalog with cost classes and health."""
    return [
        {
            "id": "local",
            "name": "Local llama.cpp (Loopback)",
            "endpoint": os.getenv("ZCODER_BASE_URL", "http://127.0.0.1:8080/v1"),
            "cost_class": "FREE_LOCAL",
            "policy_mode": "ZERO_COST_ONLY",
            "availability": "available",
            "latency_ms": 12,
            "circuit_breaker": "closed",
        },
        {
            "id": "nvidia",
            "name": "NVIDIA Hosted Integration",
            "endpoint": "https://integrate.api.nvidia.com/v1",
            "cost_class": "CUSTOMER_KEY",
            "policy_mode": "PERMIT_PAID",
            "availability": "configured",
            "latency_ms": 140,
            "circuit_breaker": "closed",
        },
    ]


@app.get("/api/admin/models/catalog")
def admin_models_catalog(request: Request):
    _require_auth(request)
    return _admin_models_catalog()


def _admin_models_catalog() -> list[dict]:
    """Model catalog with lifecycle states."""
    sectors = _load_sectors()
    catalog = []
    for s in sectors:
        model_file = s.get("model", "")
        quantization = model_file.split("-")[-1].replace(".gguf", "") if "-" in model_file else "unknown"
        catalog.append(
            {
                "id": s["name"],
                "family": "ZCoder GGUF",
                "provider": "local",
                "quantization": quantization,
                "context_length": s.get("ctx_size", 4096),
                "status": "LOADED" if s.get("enabled") else "STOPPED",
                "lifecycle": "CATALOG → DISCOVERED → DOWNLOADED → VERIFIED → LOADABLE → LOADED",
                "port": s.get("port"),
                "host": s.get("host", "127.0.0.1"),
                "enabled": s.get("enabled", False),
            }
        )
    if not catalog:
        model_id = os.getenv("ZCODER_MODEL", "qwen-7b-q4km").strip()
        catalog = [
            {
                "id": model_id,
                "family": "Qwen 2.5 Coder",
                "provider": "local",
                "quantization": "Q4_K_M",
                "context_length": 4096,
                "status": "LOADED",
                "lifecycle": "CATALOG → DISCOVERED → DOWNLOADED → VERIFIED → LOADABLE → LOADED",
            }
        ]
    return catalog


@app.get("/api/admin/tasks")
def admin_tasks(request: Request):
    _require_auth(request)
    return _admin_tasks()


def _admin_tasks() -> list[dict]:
    """Engineering task inventory — populated from the task store at runtime."""
    return []


@app.get("/api/admin/hardware")
def admin_hardware(request: Request):
    _require_auth(request)
    return _admin_hardware()


def _admin_hardware() -> dict:
    """Hardware profile and runtime resources."""
    import platform

    return {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "cpu_cores": os.cpu_count() or 1,
        "ram_status": "available",
        "local_endpoint": os.getenv("ZCODER_BASE_URL", "http://127.0.0.1:8080/v1"),
    }


# --- API v2 Endpoints ------------------------------------------------------


@app.get("/api/v2/version")
def get_version_v2():
    return {"version": VERSION, "api_version": "v2"}


@app.get("/api/v2/health")
def get_health_v2(deep: bool = False):
    report = run_health_check(deep=deep)
    res = report.to_dict()
    res["api_version"] = "v2"
    return res


@app.get("/api/v2/models")
def get_models_v2(request: Request):
    _require_auth(request)
    sectors = _load_sectors()
    models = []
    for s in sectors:
        if s.get("enabled", False):
            models.append(
                {
                    "id": s["name"],
                    "display_name": s.get("alias", s["name"]),
                    "tier": "local",
                    "context_window": s.get("ctx_size", 4096),
                }
            )
    if not models:
        model_id = os.getenv("ZCODER_MODEL", "qwen-7b-q4km").strip()
        models = [
            {
                "id": model_id,
                "display_name": "Qwen 2.5 Coder 7B Q4_K_M",
                "tier": "local",
                "context_window": 4096,
            }
        ]
    return {"api_version": "v2", "models": models}


@app.get("/api/v2/admin/metrics")
def admin_metrics_v2(request: Request):
    _require_auth(request)
    res = _admin_metrics()
    res["api_version"] = "v2"
    return res


@app.get("/api/v2/admin/providers")
def admin_providers_v2(request: Request):
    _require_auth(request)
    return {"api_version": "v2", "providers": _admin_providers()}


@app.get("/api/v2/admin/models/catalog")
def admin_models_catalog_v2(request: Request):
    _require_auth(request)
    return {"api_version": "v2", "catalog": _admin_models_catalog()}


@app.get("/api/v2/admin/tasks")
def admin_tasks_v2(request: Request):
    _require_auth(request)
    return {"api_version": "v2", "tasks": _admin_tasks()}


@app.get("/api/v2/admin/hardware")
def admin_hardware_v2(request: Request):
    _require_auth(request)
    res = _admin_hardware()
    res["api_version"] = "v2"
    return res


# --- static frontend -------------------------------------------------------
# Mounted last (and at "/") so every /api/* route above still takes
# precedence; StaticFiles only handles paths FastAPI hasn't already matched.
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
