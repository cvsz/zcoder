"""FastAPI REST server exposing ZCoder Public API v1 and control plane."""

from __future__ import annotations

import logging
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

from zcoder import __version__  # noqa: E402
from zcoder.api.auth import (  # noqa: E402
    AuthenticationUnavailable,
    RequestAuthenticationError,
    authenticate_request,
    parse_cors_origins,
)
from zcoder.api.public.v1 import (  # noqa: E402
    JobQueueUnavailable,
    PublicAPIV1Router,
)


class _LazyEnterpriseJobStore:
    """Load the tenant store on first queue request, not during app import."""

    def __init__(self, dsn: str | None = None) -> None:
        self._dsn = (dsn or os.environ.get("DATABASE_URL", "")).strip()
        self._store: Any | None = None

    def _get_store(self) -> Any:
        if not self._dsn:
            raise JobQueueUnavailable("DATABASE_URL is not configured")
        if self._store is None:
            try:
                from zcoder.infrastructure.stores.enterprise_postgres import EnterprisePostgresStore

                self._store = EnterprisePostgresStore(dsn=self._dsn)
            except Exception as exc:
                raise JobQueueUnavailable("Enterprise PostgreSQL store is unavailable") from exc
        return self._store

    def enqueue_job(self, ctx: Any, job: Any, **kwargs: Any) -> Any:
        return self._get_store().enqueue_job(ctx, job, **kwargs)

    def get_job(self, ctx: Any, job_id: str) -> Any:
        return self._get_store().get_job(ctx, job_id)

    def list_jobs(self, ctx: Any, limit: int, offset: int) -> tuple[list[Any], int]:
        return self._get_store().list_jobs(ctx, limit, offset)

    def cancel_job(self, ctx: Any, job_id: str) -> Any:
        return self._get_store().cancel_job(ctx, job_id)


app = FastAPI(
    title="ZCoder Public API & Control Plane",
    description="REST API interface for ZCoder autonomous engineering workflows, jobs, and tools.",
    version=__version__,
)

CORS_ORIGINS = parse_cors_origins(os.environ.get("ZCODER_CORS_ORIGINS"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = PublicAPIV1Router(job_store=_LazyEnterpriseJobStore())
logger = logging.getLogger(__name__)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "zcoder-api-server", "version": __version__}


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
    supplied_request_id = request.headers.get("X-Request-Id", "")
    request_id = (
        supplied_request_id
        if 0 < len(supplied_request_id) <= 128
        and all(character.isprintable() for character in supplied_request_id)
        else f"req_{uuid.uuid4().hex[:12]}"
    )

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
        except (ValueError, UnicodeDecodeError):
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "INVALID_JSON",
                        "message": "Request body must contain valid JSON",
                        # request_id is validated above (isprintable + length ≤ 128,
                        # or freshly generated via uuid), so echoing it back in the
                        # error response is safe.
                        "request_id": request_id,
                    }
                },
            )
        if not isinstance(payload, dict):
            return JSONResponse(
                status_code=422,
                content={
                    "error": {
                        "code": "INVALID_REQUEST_BODY",
                        "message": "Request JSON body must be an object",
                        # request_id is validated above (isprintable + length ≤ 128,
                        # or freshly generated via uuid), so echoing it back in the
                        # error response is safe.
                        "request_id": request_id,
                    }
                },
            )

    # Only request metadata is read from headers; tenant identity comes from
    # the verified bearer-token claims in `ctx`.
    idempotency_key = request.headers.get("Idempotency-Key")

    try:
        status_code, body = router.handle_request(
            method=method,
            path=full_path,
            ctx=ctx,
            payload=payload,
            query_params=query_params,
            idempotency_key=idempotency_key,
            request_id=request_id,
        )
    except Exception:
        logger.exception("Unhandled public API dispatcher failure request_id=%s", request_id)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected server error occurred",
                    "request_id": request_id,
                }
            },
        )

    # Defensive: ensure the response body is a plain dict so no exception
    # internals can leak into the HTTP response. router.handle_request()
    # already sanitizes all exceptions into {"error": {...}} envelopes.
    if not isinstance(status_code, int) or isinstance(status_code, bool) or not 100 <= status_code <= 599:
        status_code = 500
    if not isinstance(body, dict):
        body = {"error": {"code": "INTERNAL_SERVER_ERROR", "message": "An unexpected server error occurred"}}

    # Do not forward exception details or arbitrary nested fields in 5xx responses.
    if status_code >= 500:
        error = body.get("error")
        error = error if isinstance(error, dict) else {}
        code = error.get("code")
        safe_messages = {
            "JOB_QUEUE_UNAVAILABLE": "The tenant-scoped durable queue is unavailable",
            "JOB_RUNTIME_UNAVAILABLE": (
                "Job submission is unavailable until a local execution adapter is configured"
            ),
            "WEBHOOK_REGISTRY_UNAVAILABLE": "Webhook registration is unavailable",
        }
        if not isinstance(code, str) or code not in safe_messages:
            code = "INTERNAL_SERVER_ERROR"
        message = safe_messages.get(code, "An unexpected server error occurred")
        body = {"error": {"code": code, "message": message, "request_id": request_id}}

    return JSONResponse(status_code=status_code, content=body)


def start():
    import uvicorn

    port = int(os.getenv("PORT", "8088"))
    host = os.getenv("HOST", "127.0.0.1")
    uvicorn.run("zcoder.api.server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    start()
