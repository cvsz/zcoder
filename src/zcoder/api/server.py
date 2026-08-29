"""FastAPI REST server exposing ZCoder Public API v1 and control plane."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Ensure root src is in path for alias modules
src_path = Path(__file__).resolve().parent.parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from zcoder.api.auth import (  # noqa: E402
    AuthenticationUnavailable,
    RequestAuthenticationError,
    authenticate_request,
    parse_cors_origins,
)
from zcoder.api.public.v1 import PublicAPIV1Router  # noqa: E402

app = FastAPI(
    title="ZCoder Public API & Control Plane",
    description="REST API interface for ZCoder autonomous engineering workflows, jobs, and tools.",
    version="1.41.0",
)

CORS_ORIGINS = parse_cors_origins(os.environ.get("ZCODER_CORS_ORIGINS"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = PublicAPIV1Router()


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "zcoder-api-server", "version": "1.41.0"}


@app.get("/metrics")
def metrics():
    from zcoder.infrastructure.observability.otel import get_metrics

    return Response(
        content=get_metrics().prometheus_exposition(),
        media_type="text/plain; version=0.0.4",
    )


@app.get("/health/live")
def liveness():
    return {"status": "alive"}


_db_probe_store: Any | None = None


def _get_db_store() -> Any:
    global _db_probe_store
    if _db_probe_store is None:
        from zcoder.infrastructure.stores.postgres import PostgresControlPlaneStore

        _db_probe_store = PostgresControlPlaneStore()
    return _db_probe_store


def check_database_ready() -> bool:
    """Best-effort DB connectivity probe; fail-closed on any error."""
    try:
        store = _get_db_store()
        return bool(store.health_check())
    except Exception:
        return False


@app.get("/health/ready")
def readiness():
    if not check_database_ready():
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ready"}


@app.api_route("/api/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def handle_v1_api(request: Request, path: str):
    method = request.method
    full_path = f"/api/v1/{path}"
    request_id = request.headers.get("X-Request-Id") or f"req_{uuid.uuid4().hex[:12]}"

    try:
        ctx = authenticate_request(request.headers)
    except AuthenticationUnavailable as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": "AUTHENTICATION_UNAVAILABLE",
                    "message": exc.message,
                    "request_id": request_id,
                }
            },
        )
    except RequestAuthenticationError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": "UNAUTHENTICATED",
                    "message": exc.message,
                    "request_id": request_id,
                }
            },
        )

    # Extract query params
    query_params = dict(request.query_params)

    # Extract JSON payload if present
    payload = {}
    if method in ("POST", "PUT", "PATCH"):
        try:
            payload = await request.json()
        except Exception:
            payload = {}

    # Only request metadata is read from headers; tenant identity comes from
    # the verified bearer-token claims in `ctx`.
    idempotency_key = request.headers.get("Idempotency-Key")

    status_code, body = router.handle_request(
        method=method,
        path=full_path,
        ctx=ctx,
        payload=payload,
        query_params=query_params,
        idempotency_key=idempotency_key,
        request_id=request_id,
    )

    return JSONResponse(status_code=status_code, content=body)


def start():
    import uvicorn

    port = int(os.getenv("PORT", "8088"))
    host = os.getenv("HOST", "127.0.0.1")
    uvicorn.run("zcoder.api.server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    start()
