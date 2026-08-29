"""Public API contract tests for the tenant-scoped durable job queue."""

from __future__ import annotations

from dataclasses import replace

import pytest

from zcoder.api.public.v1 import PublicAPIV1Router
from zcoder.domain.models.tenant import EnterpriseRole, IdempotencyConflictError, RequestContext
from zcoder.services.agent_runtime import Job, JobStatus


def operator_context() -> RequestContext:
    return RequestContext(
        principal_id="operator-1",
        organization_id="org-1",
        project_id="project-1",
        role=EnterpriseRole.OPERATOR,
    )


class FakeTenantJobStore:
    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}
        self.job_organizations: dict[str, str] = {}
        self.idempotency_records: dict[tuple[str, str], tuple[str, str]] = {}
        self.enqueue_calls: list[tuple[RequestContext, Job, str | None, str | None]] = []

    def enqueue_job(
        self,
        ctx: RequestContext,
        job: Job,
        *,
        idempotency_key: str | None = None,
        request_fingerprint: str | None = None,
    ) -> Job:
        if idempotency_key:
            record_key = (ctx.organization_id, idempotency_key)
            existing = self.idempotency_records.get(record_key)
            if existing is not None:
                if existing[0] != request_fingerprint:
                    raise IdempotencyConflictError("Idempotency key reused with a different request payload")
                existing_job = self.jobs[existing[1]]
                if ctx.project_id is not None and existing_job.project_id != ctx.project_id:
                    raise IdempotencyConflictError(
                        "Idempotency key is already associated with a different project scope"
                    )
                return existing_job
        self.enqueue_calls.append((ctx, job, idempotency_key, request_fingerprint))
        self.jobs[job.id] = job
        self.job_organizations[job.id] = ctx.organization_id
        if idempotency_key:
            self.idempotency_records[(ctx.organization_id, idempotency_key)] = (
                request_fingerprint or "",
                job.id,
            )
        return job

    def get_job(self, ctx: RequestContext, job_id: str) -> Job | None:
        job = self.jobs.get(job_id)
        if job is None or self.job_organizations.get(job_id) != ctx.organization_id:
            return None
        return job

    def list_jobs(self, ctx: RequestContext, limit: int, offset: int) -> tuple[list[Job], int]:
        jobs = [
            job for job in self.jobs.values() if self.job_organizations.get(job.id) == ctx.organization_id
        ]
        jobs.sort(key=lambda job: job.created_at, reverse=True)
        return jobs[offset : offset + limit], len(jobs)

    def cancel_job(self, ctx: RequestContext, job_id: str) -> Job | None:
        job = self.get_job(ctx, job_id)
        if job is None:
            return None
        cancelled = replace(job, status=JobStatus.CANCELLED, updated_at=job.updated_at + 1)
        self.jobs[job_id] = cancelled
        return cancelled


def test_post_job_persists_ready_job_and_reuses_idempotent_result() -> None:
    store = FakeTenantJobStore()
    router = PublicAPIV1Router(job_store=store)
    ctx = operator_context()

    status, body = router.handle_request(
        "POST",
        "/api/v1/jobs",
        ctx,
        payload={
            "task": "Run tests",
            "runtime": "fake",
            "model": "claude-sonnet-5",
            "budget_usd": 1.25,
            "metadata": {"source": "api"},
        },
        idempotency_key="job-create-1",
        request_id="req-create-1",
    )

    assert status == 201
    assert body["status"] == "READY"
    assert body["organization_id"] == "org-1"
    assert body["project_id"] == "project-1"
    assert body["task"] == "Run tests"
    assert body["request_id"] == "req-create-1"
    job = store.jobs[body["id"]]
    assert job.status == JobStatus.READY
    assert job.metadata == {"source": "api"}
    assert len(store.enqueue_calls) == 1
    assert store.enqueue_calls[0][0] == ctx
    assert store.enqueue_calls[0][2] == "job-create-1"
    assert isinstance(store.enqueue_calls[0][3], str)

    replay_status, replay_body = router.handle_request(
        "POST",
        "/api/v1/jobs",
        ctx,
        payload={
            "task": "Run tests",
            "runtime": "fake",
            "model": "claude-sonnet-5",
            "budget_usd": 1.25,
            "metadata": {"source": "api"},
        },
        idempotency_key="job-create-1",
    )

    assert replay_status == 201
    assert replay_body["id"] == body["id"]
    assert len(store.enqueue_calls) == 1


def test_idempotency_replay_is_scoped_to_the_verified_project() -> None:
    store = FakeTenantJobStore()
    router = PublicAPIV1Router(job_store=store)
    first_ctx = operator_context()
    payload = {"task": "Run tests", "runtime": "fake"}

    first_status, first_body = router.handle_request(
        "POST",
        "/api/v1/jobs",
        first_ctx,
        payload=payload,
        idempotency_key="project-scoped-key",
    )
    assert first_status == 201

    second_status, second_body = router.handle_request(
        "POST",
        "/api/v1/jobs",
        replace(first_ctx, project_id="project-2"),
        payload=payload,
        idempotency_key="project-scoped-key",
    )

    assert second_status == 409
    assert second_body["error"]["code"] == "IDEMPOTENCY_CONFLICT"


@pytest.mark.parametrize("idempotency_key", ["", "   ", "k" * 257])
def test_invalid_idempotency_keys_are_rejected(idempotency_key: str) -> None:
    router = PublicAPIV1Router(job_store=FakeTenantJobStore())

    status, body = router.handle_request(
        "POST",
        "/api/v1/jobs",
        operator_context(),
        payload={"task": "Run tests"},
        idempotency_key=idempotency_key,
    )

    assert status == 422
    assert body["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("task", ["", "   ", 123, None])
def test_post_job_rejects_blank_or_non_string_tasks(task: object) -> None:
    router = PublicAPIV1Router(job_store=FakeTenantJobStore())

    status, body = router.handle_request(
        "POST", "/api/v1/jobs", operator_context(), payload={"task": task}, request_id="req-invalid"
    )

    assert status == 422
    assert body["error"]["code"] == "VALIDATION_ERROR"


def test_job_get_list_and_cancel_use_the_tenant_store() -> None:
    store = FakeTenantJobStore()
    ctx = operator_context()
    first = Job(
        id="job-1",
        task="first",
        status=JobStatus.READY,
        metadata={},
        created_at=1.0,
        updated_at=1.0,
    )
    second = Job(
        id="job-2",
        task="second",
        status=JobStatus.RUNNING,
        metadata={},
        created_at=2.0,
        updated_at=2.0,
    )
    store.jobs.update({first.id: first, second.id: second})
    store.job_organizations.update({first.id: "org-1", second.id: "org-1"})
    router = PublicAPIV1Router(job_store=store)

    get_status, get_body = router.handle_request("GET", "/api/v1/jobs/job-2", ctx, request_id="req-get")
    assert get_status == 200
    assert get_body["id"] == "job-2"
    assert get_body["status"] == "RUNNING"

    list_status, list_body = router.handle_request(
        "GET",
        "/api/v1/jobs",
        ctx,
        query_params={"limit": "1", "offset": "0"},
        request_id="req-list",
    )
    assert list_status == 200
    assert [item["id"] for item in list_body["data"]] == ["job-2"]
    assert list_body["pagination"] == {"limit": 1, "offset": 0, "total": 2, "has_more": True}

    cancel_status, cancel_body = router.handle_request(
        "DELETE", "/api/v1/jobs/job-2", ctx, request_id="req-cancel"
    )
    assert cancel_status == 200
    assert cancel_body["id"] == "job-2"
    assert cancel_body["status"] == "CANCELLED"


def test_job_routes_remain_truthful_when_no_durable_store_is_configured() -> None:
    router = PublicAPIV1Router()

    status, body = router.handle_request(
        "POST", "/api/v1/jobs", operator_context(), payload={"task": "run tests"}, request_id="req-no-store"
    )

    assert status == 501
    assert body["error"]["code"] == "JOB_QUEUE_UNAVAILABLE"
