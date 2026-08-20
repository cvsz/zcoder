"""FastAPI REST server exposing ZCoder Public API v1 and control plane."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Ensure root src is in path for alias modules
src_path = Path(__file__).resolve().parent.parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from zcoder.api.public.v1 import PublicAPIV1Router  # noqa: E402
from zcoder.domain.models.tenant import EnterpriseRole, RequestContext  # noqa: E402

app = FastAPI(
    title="ZCoder Public API & Control Plane",
    description="REST API interface for ZCoder autonomous engineering workflows, jobs, and tools.",
    version="1.40.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = PublicAPIV1Router()


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "zcoder-api-server", "version": "1.40.0"}


@app.api_route("/api/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def handle_v1_api(request: Request, path: str):
    method = request.method
    full_path = f"/api/v1/{path}"

    # Extract query params
    query_params = dict(request.query_params)

    # Extract JSON payload if present
    payload = {}
    if method in ("POST", "PUT", "PATCH"):
        try:
            payload = await request.json()
        except Exception:
            payload = {}

    # Extract headers for auth and idempotency
    org_id = request.headers.get("X-Organization-Id", "org_default")
    proj_id = request.headers.get("X-Project-Id", "proj_default")
    principal_id = request.headers.get("X-Principal-Id", "usr_admin")
    idempotency_key = request.headers.get("Idempotency-Key")
    request_id = request.headers.get("X-Request-Id")

    ctx = RequestContext(
        principal_id=principal_id,
        organization_id=org_id,
        project_id=proj_id,
        role=EnterpriseRole.ORG_ADMIN,
    )

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
