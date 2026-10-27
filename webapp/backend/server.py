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

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

# --- make the project root (one level above webapp/) importable ----------
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from zcoder.agent.personalities import PersonalityManager  # noqa: E402
from zcoder.api.auth import parse_cors_origins  # noqa: E402
from zcoder.config.logging import get_logger  # noqa: E402
from zcoder.config.settings import Config  # noqa: E402
from zcoder.core.health import run_health_check  # noqa: E402
from zcoder.main import AGENT_SYSTEM_PROMPTS, VERSION  # noqa: E402
from zcoder.services.coder import Coder  # noqa: E402
from zcoder.services.skills import SkillManager  # noqa: E402

logger = get_logger("webapp.server")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


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
# Process-local and non-persistent by design, same lifetime as the CLI's
# `--interactive` REPL history -- just reachable over HTTP instead of a
# terminal. Restarting the server clears all sessions.
_sessions: dict[str, list[dict]] = {}
_SESSION_LIMIT = 200  # oldest session dropped past this to bound memory


class ChatRequest(BaseModel):
    prompt: str
    session_id: str | None = None
    model: str = os.getenv("ZCODER_MODEL", "zqwen2.5-coder-7b-instruct-q4_k_m")
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


def _check_rate_limit(ip: str) -> None:
    now = time.time()
    bucket = [t for t in _rate_buckets.get(ip, []) if now - t < _RATE_WINDOW]
    if len(bucket) >= _RATE_LIMIT:
        raise HTTPException(429, f"Rate limit exceeded ({_RATE_LIMIT}/min). Try again shortly.")
    bucket.append(now)
    _rate_buckets[ip] = bucket


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    """Prevent a local model server redirecting inference off-loopback."""

    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
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
        _local_model_endpoint("chat/completions"),
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
def get_models():
    model_id = os.getenv("ZCODER_MODEL", "zqwen2.5-coder-7b-instruct-q4_k_m").strip()
    return [{"id": model_id, "display_name": model_id, "tier": "local"}]


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
def get_config():
    cfg = Config().all()
    return {"model": cfg.get("model"), "temperature": cfg.get("temperature")}


@app.post("/api/config")
def set_config(update: ConfigUpdate):
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
    out = []
    for sid, history in _sessions.items():
        first_user = next((m["content"] for m in history if m["role"] == "user"), "")
        out.append(
            {
                "session_id": sid,
                "turns": len(history) // 2,
                "preview": (first_user[:80] + "…") if len(first_user) > 80 else first_user,
            }
        )
    return out


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str):
    if session_id not in _sessions:
        raise HTTPException(404, "Unknown session_id")
    return {"session_id": session_id, "history": _sessions[session_id]}


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str):
    _sessions.pop(session_id, None)
    return {"ok": True}


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request):
    if not req.prompt or not req.prompt.strip():
        raise HTTPException(400, "prompt must not be empty")
    _check_rate_limit(request.client.host if request.client else "unknown")

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
    if len(_sessions) > _SESSION_LIMIT:
        _sessions.pop(next(iter(_sessions)), None)

    return ChatResponse(session_id=session_id, response=reply, model=req.model)


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest, request: Request):
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
    if not req.prompt or not req.prompt.strip():
        raise HTTPException(400, "prompt must not be empty")
    _check_rate_limit(request.client.host if request.client else "unknown")

    session_id = req.session_id or str(uuid.uuid4())
    history = _sessions.get(session_id, [])
    system = _build_system_prompt(req)

    def event_stream():
        full_text = ""
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
                    delta = (choices[0].get("delta") or {}).get("content", "")
                    if isinstance(delta, str) and delta:
                        full_text += delta
                        yield f"data: {json.dumps({'type': 'token', 'text': delta})}\n\n"
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

        new_history = history + [
            {"role": "user", "content": req.prompt},
            {"role": "assistant", "content": full_text},
        ]
        _sessions[session_id] = new_history
        if len(_sessions) > _SESSION_LIMIT:
            _sessions.pop(next(iter(_sessions)), None)
        yield f"data: {json.dumps({'type': 'done', 'session_id': session_id, 'model': req.model})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# --- static frontend -------------------------------------------------------
# Mounted last (and at "/") so every /api/* route above still takes
# precedence; StaticFiles only handles paths FastAPI hasn't already matched.
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
