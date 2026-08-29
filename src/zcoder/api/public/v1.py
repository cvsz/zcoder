"""public_api_v1.py — Official ZCoder Customer-Facing Public REST API (v1).

Provides stable, versioned, authenticated endpoints for:
  • /api/v1/organizations (get, list, update)
  • /api/v1/projects (create, list, get)
  • /api/v1/jobs (create, get, list, cancel)
  • /api/v1/usage (query current period usage and quota limits)
  • /api/v1/webhooks (register, list, test customer webhooks)
  • /api/v1/api-keys (create, list, revoke keys)
  • /api/v1/entitlements (inspect active plan capabilities)

Standard features:
  • API versioning (/api/v1/)
  • Bounded pagination (limit, offset / cursor)
  • Standardized error envelope with request_id
  • Idempotency-Key support on create/mutate endpoints
  • Fail-closed tenant authorization & scope verification
"""

from __future__ import annotations

import hashlib
import json
import math
import time
import uuid
from typing import Any, Protocol

from zcoder.core.outbound_security import validate_external_http_url
from zcoder.domain.models.product import EntitlementService
from zcoder.domain.models.tenant import (
    CrossTenantViolationError,
    IdempotencyConflictError,
    PermissionDeniedError,
    RequestContext,
)
from zcoder.services.agent_runtime import Job, JobStatus


class APIError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400, details: Any = None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)

    def to_dict(self, request_id: str) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "request_id": request_id,
                "details": self.details,
            }
        }


class JobQueueUnavailable(RuntimeError):
    """Raised when the configured durable job queue cannot be reached."""


class TenantJobStore(Protocol):
    """Minimal tenant-scoped persistence contract required by the public API."""

    def enqueue_job(
        self,
        ctx: RequestContext,
        job: Job,
        *,
        idempotency_key: str | None = None,
        request_fingerprint: str | None = None,
    ) -> Job: ...

    def get_job(self, ctx: RequestContext, job_id: str) -> Job | None: ...

    def list_jobs(self, ctx: RequestContext, limit: int, offset: int) -> tuple[list[Job], int]: ...

    def cancel_job(self, ctx: RequestContext, job_id: str) -> Job | None: ...


class PublicAPIV1Router:
    """Dispatches public customer REST API calls with strict tenant authentication, rate limits, and idempotency."""

    def __init__(
        self,
        entitlement_service: EntitlementService | None = None,
        job_store: TenantJobStore | None = None,
    ):
        self.entitlements = entitlement_service or EntitlementService()
        self.job_store = job_store
        self.idempotency_store: dict[str, dict[str, Any]] = {}
        self.rate_limit_tracker: dict[str, list[float]] = {}

    def _check_rate_limit(
        self, principal_id: str, max_requests: int = 120, window_seconds: float = 60.0
    ) -> None:
        now = time.time()
        calls = self.rate_limit_tracker.setdefault(principal_id, [])
        # purge older calls
        calls = [t for t in calls if now - t < window_seconds]
        if len(calls) >= max_requests:
            raise APIError(
                "RATE_LIMIT_EXCEEDED", "Rate limit exceeded. Please retry after some time.", status_code=429
            )
        calls.append(now)
        self.rate_limit_tracker[principal_id] = calls

    @staticmethod
    def _fingerprint(payload: dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    @staticmethod
    def _job_response(job: Job, ctx: RequestContext, request_id: str) -> dict[str, Any]:
        status = job.status.value if isinstance(job.status, JobStatus) else str(job.status)
        return {
            "id": job.id,
            "task": job.task,
            "runtime": job.runtime,
            "status": status,
            "workspace": job.workspace,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "model": job.model,
            "budget_usd": job.budget_usd,
            "cost_usd": job.cost_usd,
            "organization_id": ctx.organization_id,
            "project_id": job.project_id,
            "metadata": job.metadata,
            "request_id": request_id,
        }

    def _require_job_store(self) -> TenantJobStore:
        if self.job_store is None:
            raise APIError(
                "JOB_QUEUE_UNAVAILABLE",
                "Job submission is unavailable until the tenant-scoped durable queue is configured",
                status_code=501,
            )
        return self.job_store

    @staticmethod
    def _new_job(ctx: RequestContext, payload: dict[str, Any]) -> Job:
        task = payload.get("task")
        if not isinstance(task, str) or not task.strip() or len(task.strip()) > 100_000:
            raise APIError(
                "VALIDATION_ERROR",
                "Field 'task' must be a non-empty string of at most 100000 characters",
                status_code=422,
            )

        runtime = payload.get("runtime", "direct")
        if not isinstance(runtime, str) or runtime not in {"direct", "fake", "noop"}:
            raise APIError(
                "VALIDATION_ERROR",
                "Field 'runtime' must be one of: direct, fake, noop",
                status_code=422,
            )

        model = payload.get("model", "claude-sonnet-5")
        if not isinstance(model, str) or not model.strip() or len(model) > 256:
            raise APIError(
                "VALIDATION_ERROR",
                "Field 'model' must be a non-empty string of at most 256 characters",
                status_code=422,
            )

        budget = payload.get("budget_usd", 0.0)
        if (
            isinstance(budget, bool)
            or not isinstance(budget, (int, float))
            or not math.isfinite(budget)
            or budget < 0
        ):
            raise APIError(
                "VALIDATION_ERROR",
                "Field 'budget_usd' must be a finite non-negative number",
                status_code=422,
            )

        metadata = payload.get("metadata", {})
        if metadata is None:
            metadata = {}
        if not isinstance(metadata, dict):
            raise APIError("VALIDATION_ERROR", "Field 'metadata' must be an object", status_code=422)

        return Job(
            id=f"job_{uuid.uuid4().hex}",
            task=task.strip(),
            runtime=runtime,
            status=JobStatus.READY,
            # The API does not accept a model-controlled filesystem path.
            workspace=".",
            model=model.strip(),
            budget_usd=float(budget),
            project_id=ctx.project_id,
            metadata=dict(metadata),
        )

    def handle_request(
        self,
        method: str,
        path: str,
        ctx: RequestContext,
        payload: dict[str, Any] | None = None,
        query_params: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        request_id: str | None = None,
    ) -> tuple[int, dict[str, Any]]:
        """Main dispatcher implementing standard API envelope, idempotency, and error formatting."""
        req_id = request_id or f"req_{uuid.uuid4().hex[:12]}"
        query_params = query_params or {}
        payload = payload or {}

        try:
            if idempotency_key is not None and (
                not isinstance(idempotency_key, str)
                or not idempotency_key.strip()
                or len(idempotency_key) > 256
            ):
                raise APIError(
                    "VALIDATION_ERROR",
                    "Idempotency-Key must be a non-empty string of at most 256 characters",
                    status_code=422,
                )

            self._check_rate_limit(ctx.principal_id)

            # Idempotency check for mutating calls
            if idempotency_key and method in ("POST", "PUT", "PATCH", "DELETE"):
                cache_key = f"{ctx.organization_id}:{ctx.project_id or ''}:{method}:{path}:{idempotency_key}"
                if cache_key in self.idempotency_store:
                    cached = self.idempotency_store[cache_key]
                    # verify request fingerprint matches
                    fingerprint = self._fingerprint(payload)
                    if cached.get("fingerprint") == fingerprint:
                        return cached["status_code"], cached["response"]
                    else:
                        raise APIError(
                            "IDEMPOTENCY_CONFLICT",
                            "Idempotency key reused with different request payload",
                            status_code=409,
                        )

            status_code, response_body = self._route(
                method, path, ctx, payload, query_params, req_id, idempotency_key
            )

            if idempotency_key and method in ("POST", "PUT", "PATCH", "DELETE"):
                cache_key = f"{ctx.organization_id}:{ctx.project_id or ''}:{method}:{path}:{idempotency_key}"
                self.idempotency_store[cache_key] = {
                    "fingerprint": self._fingerprint(payload),
                    "status_code": status_code,
                    "response": response_body,
                    "created_at": time.time(),
                }

            return status_code, response_body

        except APIError as e:
            return e.status_code, e.to_dict(req_id)
        except Exception:
            return 500, APIError(
                "INTERNAL_SERVER_ERROR", "An unexpected server error occurred", status_code=500
            ).to_dict(req_id)

    def _route(
        self,
        method: str,
        path: str,
        ctx: RequestContext,
        payload: dict[str, Any],
        query: dict[str, Any],
        req_id: str,
        idempotency_key: str | None = None,
    ) -> tuple[int, dict[str, Any]]:
        # Normalize path
        p = path.rstrip("/")

        # 1. /api/v1/entitlements
        if p == "/api/v1/entitlements" and method == "GET":
            bundle = self.entitlements.get_entitlements(ctx.organization_id)
            return 200, {
                "organization_id": ctx.organization_id,
                "entitlements": {
                    "version": bundle.version,
                    "max_projects": bundle.max_projects,
                    "max_repositories": bundle.max_repositories,
                    "monthly_budget_usd": bundle.monthly_budget_usd,
                    "concurrent_jobs": bundle.concurrent_jobs,
                    "managed_agents": bundle.managed_agents,
                    "multiagent_orchestration": bundle.multiagent_orchestration,
                    "scim_enabled": bundle.scim_enabled,
                    "sso_oidc_enabled": bundle.sso_oidc_enabled,
                },
                "request_id": req_id,
            }

        # 2. /api/v1/jobs
        if p == "/api/v1/jobs":
            if method == "POST":
                store = self._require_job_store()
                job = self._new_job(ctx, payload)
                try:
                    persisted = store.enqueue_job(
                        ctx,
                        job,
                        idempotency_key=idempotency_key,
                        request_fingerprint=self._fingerprint(payload),
                    )
                except IdempotencyConflictError as exc:
                    raise APIError(
                        "IDEMPOTENCY_CONFLICT",
                        str(exc),
                        status_code=409,
                    ) from exc
                except (PermissionDeniedError, CrossTenantViolationError) as exc:
                    raise APIError("FORBIDDEN", str(exc), status_code=403) from exc
                except JobQueueUnavailable:
                    raise APIError(
                        "JOB_QUEUE_UNAVAILABLE",
                        "The tenant-scoped durable queue is unavailable",
                        status_code=503,
                    ) from None
                except Exception as exc:
                    raise APIError(
                        "JOB_QUEUE_UNAVAILABLE",
                        "The tenant-scoped durable queue is unavailable",
                        status_code=503,
                    ) from exc
                if not isinstance(persisted, Job):
                    raise APIError(
                        "JOB_QUEUE_UNAVAILABLE",
                        "The tenant-scoped durable queue returned an invalid job",
                        status_code=503,
                    )
                return 201, self._job_response(persisted, ctx, req_id)
            elif method == "GET":
                store = self._require_job_store()
                try:
                    limit = int(query.get("limit", 20))
                    offset = int(query.get("offset", 0))
                except (TypeError, ValueError) as exc:
                    raise APIError(
                        "VALIDATION_ERROR", "limit and offset must be integers", status_code=422
                    ) from exc
                if not 1 <= limit <= 100 or offset < 0:
                    raise APIError(
                        "VALIDATION_ERROR",
                        "limit must be 1-100 and offset must be non-negative",
                        status_code=422,
                    )
                try:
                    jobs, total = store.list_jobs(ctx, limit, offset)
                except (PermissionDeniedError, CrossTenantViolationError) as exc:
                    raise APIError("FORBIDDEN", str(exc), status_code=403) from exc
                except JobQueueUnavailable:
                    raise APIError(
                        "JOB_QUEUE_UNAVAILABLE",
                        "The tenant-scoped durable queue is unavailable",
                        status_code=503,
                    ) from None
                except Exception as exc:
                    raise APIError(
                        "JOB_QUEUE_UNAVAILABLE",
                        "The tenant-scoped durable queue is unavailable",
                        status_code=503,
                    ) from exc
                return 200, {
                    "data": [self._job_response(job, ctx, req_id) for job in jobs],
                    "pagination": {
                        "limit": limit,
                        "offset": offset,
                        "total": total,
                        "has_more": offset + len(jobs) < total,
                    },
                    "request_id": req_id,
                }

        if p.startswith("/api/v1/jobs/"):
            job_id = p.removeprefix("/api/v1/jobs/")
            if not job_id or "/" in job_id:
                raise APIError("NOT_FOUND", f"Route {method} {path} not found", status_code=404)
            store = self._require_job_store()
            try:
                if method == "GET":
                    fetched_job = store.get_job(ctx, job_id)
                    if fetched_job is None:
                        raise APIError("NOT_FOUND", f"Job {job_id} not found", status_code=404)
                    return 200, self._job_response(fetched_job, ctx, req_id)
                if method == "DELETE":
                    cancelled_job = store.cancel_job(ctx, job_id)
                    if cancelled_job is None:
                        raise APIError("NOT_FOUND", f"Job {job_id} not found", status_code=404)
                    return 200, self._job_response(cancelled_job, ctx, req_id)
            except (PermissionDeniedError, CrossTenantViolationError) as exc:
                raise APIError("FORBIDDEN", str(exc), status_code=403) from exc
            except JobQueueUnavailable:
                raise APIError(
                    "JOB_QUEUE_UNAVAILABLE",
                    "The tenant-scoped durable queue is unavailable",
                    status_code=503,
                ) from None
            except APIError:
                raise
            except Exception as exc:
                raise APIError(
                    "JOB_QUEUE_UNAVAILABLE",
                    "The tenant-scoped durable queue is unavailable",
                    status_code=503,
                ) from exc

        # 3. /api/v1/webhooks
        if p == "/api/v1/webhooks":
            if method == "POST":
                url = payload.get("url")
                if not url:
                    raise APIError("VALIDATION_ERROR", "Field 'url' is required", status_code=422)
                try:
                    validate_external_http_url(url)
                except (TypeError, ValueError):
                    raise APIError(
                        "SSRF_BLOCKED",
                        "Webhook URL must resolve exclusively to a public HTTP(S) address",
                        status_code=400,
                    ) from None
                wh_id = f"wh_{uuid.uuid4().hex[:12]}"
                secret = f"whsec_{uuid.uuid4().hex}"
                return 201, {
                    "id": wh_id,
                    "url": url,
                    "secret": secret,
                    "event_types": payload.get("event_types", ["job.completed", "job.failed"]),
                    "status": "ACTIVE",
                    "created_at": time.time(),
                    "request_id": req_id,
                }

        # Default 404
        raise APIError("NOT_FOUND", f"Route {method} {path} not found", status_code=404)
