"""zcoder-sdk — Official ZCoder Python SDK.

Provides a typed, async-capable client for interacting with the ZCoder API,
including job management, webhook registration, entitlement queries, and
credential management.

Example usage:

    from zcoder_sdk import ZCoderClient

    client = ZCoderClient(
        api_key="zck_...",
        organization_id="org_123",
        project_id="proj_456",
    )
    result = client.create_job("Refactor the login module")
    print(result["id"])
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from typing import Any

from zcoder.api.public.v1 import PublicAPIV1Router
from zcoder.domain.models.tenant import EnterpriseRole, RequestContext


class ZCoderSDKException(Exception):
    """Base exception for all SDK errors."""

    def __init__(self, message: str, status_code: int | None = None, details: Any = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class AuthenticationError(ZCoderSDKException):
    """Raised when authentication fails (401)."""

    def __init__(self, message: str = "Authentication failed", details: Any = None):
        super().__init__(message, status_code=401, details=details)


class RateLimitError(ZCoderSDKException):
    """Raised when rate limit is exceeded (429)."""

    def __init__(self, message: str = "Rate limit exceeded", details: Any = None):
        super().__init__(message, status_code=429, details=details)


class NotFoundError(ZCoderSDKException):
    """Raised when a resource is not found (404)."""

    def __init__(self, message: str = "Resource not found", details: Any = None):
        super().__init__(message, status_code=404, details=details)


class ValidationError(ZCoderSDKException):
    """Raised when request validation fails (422)."""

    def __init__(self, message: str = "Validation failed", details: Any = None):
        super().__init__(message, status_code=422, details=details)


class Job:
    """Represents a ZCoder job."""

    def __init__(
        self,
        id: str,
        task: str,
        status: str,
        model: str,
        created_at: float,
        updated_at: float,
        organization_id: str | None = None,
        project_id: str | None = None,
        budget_usd: float = 0.0,
        cost_usd: float = 0.0,
        metadata: dict[str, Any] | None = None,
        runtime: str = "direct",
        workspace: str = ".",
    ):
        self.id = id
        self.task = task
        self.status = status
        self.model = model
        self.created_at = created_at
        self.updated_at = updated_at
        self.organization_id = organization_id
        self.project_id = project_id
        self.budget_usd = budget_usd
        self.cost_usd = cost_usd
        self.metadata = metadata or {}
        self.runtime = runtime
        self.workspace = workspace

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Job:
        return cls(
            id=data["id"],
            task=data["task"],
            status=data["status"],
            model=data.get("model", ""),
            created_at=data.get("created_at", 0.0),
            updated_at=data.get("updated_at", 0.0),
            organization_id=data.get("organization_id"),
            project_id=data.get("project_id"),
            budget_usd=data.get("budget_usd", 0.0),
            cost_usd=data.get("cost_usd", 0.0),
            metadata=data.get("metadata", {}),
            runtime=data.get("runtime", "direct"),
            workspace=data.get("workspace", "."),
        )

    def __repr__(self) -> str:
        return f"Job(id={self.id!r}, status={self.status!r}, task={self.task[:30]!r})"


class PaginationResult:
    """Represents a paginated API response."""

    def __init__(
        self,
        items: list[Any],
        limit: int,
        offset: int,
        total: int,
        has_more: bool,
    ):
        self.items = items
        self.limit = limit
        self.offset = offset
        self.total = total
        self.has_more = has_more

    @property
    def next_offset(self) -> int:
        return self.offset + self.limit


class ZCoderClient:
    """Official Python SDK client for automating ZCoder jobs and retrieving artifacts.

    Provides:
        • Typed ZCoderClient with API key auth
        • Idempotency-Key support on task submission
        • Bounded pagination iterator
        • Standardized exception mapping (APIError, RateLimitError, AuthError)

    Example usage:

        client = ZCoderClient(
            api_key="zck_...",
            organization_id="org_123",
            project_id="proj_456",
        )
        job = client.create_job("Refactor the login module")
        print(job.id)
    """

    def __init__(
        self,
        api_key: str,
        organization_id: str,
        project_id: str | None = None,
        router: PublicAPIV1Router | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
    ):
        self.api_key = api_key
        self.organization_id = organization_id
        self.project_id = project_id
        self.base_url = base_url
        self.timeout = timeout
        self._router = router or PublicAPIV1Router()
        self._ctx = RequestContext(
            principal_id=f"apikey_{api_key[:8]}",
            organization_id=organization_id,
            project_id=project_id,
            role=EnterpriseRole.OPERATOR,
            authentication_method="apikey",
        )

    def get_entitlements(self) -> dict[str, Any]:
        """Fetch entitlements for the current organization.

        Returns:
            Dict containing entitlement information including version,
            limits, and enabled features.
        """
        status, body = self._router.handle_request("GET", "/api/v1/entitlements", self._ctx)
        if status == 401:
            raise AuthenticationError("Failed to fetch entitlements", body)
        if status != 200:
            raise ZCoderSDKException(f"Failed to fetch entitlements: {body}", status_code=status)
        return body["entitlements"]

    def create_job(
        self,
        task: str,
        model: str | None = None,
        budget_usd: float | None = None,
        metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> Job:
        """Create a new job.

        Args:
            task: The task description for the agent to execute.
            model: Optional model override.
            budget_usd: Optional budget limit in USD.
            metadata: Optional metadata dictionary.
            idempotency_key: Optional idempotency key for safe retries.

        Returns:
            A Job instance representing the created job.

        Raises:
            AuthenticationError: If authentication fails.
            RateLimitError: If rate limit is exceeded.
            ValidationError: If the request is invalid.
            ZCoderSDKException: For other errors.
        """
        payload: dict[str, Any] = {"task": task}
        if model is not None:
            payload["model"] = model
        if budget_usd is not None:
            payload["budget_usd"] = budget_usd
        if metadata is not None:
            payload["metadata"] = metadata

        status, body = self._router.handle_request(
            "POST",
            "/api/v1/jobs",
            self._ctx,
            payload=payload,
            idempotency_key=idempotency_key,
        )
        if status == 401:
            raise AuthenticationError("Failed to create job", body)
        if status == 429:
            raise RateLimitError("Rate limit exceeded creating job", body)
        if status == 422:
            raise ValidationError("Invalid job request", body)
        if status != 201:
            raise ZCoderSDKException(f"Job creation failed (HTTP {status}): {body}", status_code=status)
        return Job.from_dict(body)

    def get_job(self, job_id: str) -> Job:
        """Get a job by ID.

        Args:
            job_id: The ID of the job to retrieve.

        Returns:
            A Job instance.

        Raises:
            NotFoundError: If the job does not exist.
            AuthenticationError: If authentication fails.
        """
        status, body = self._router.handle_request("GET", f"/api/v1/jobs/{job_id}", self._ctx)
        if status == 401:
            raise AuthenticationError("Failed to get job", body)
        if status == 404:
            raise NotFoundError(f"Job {job_id} not found", body)
        if status != 200:
            raise ZCoderSDKException(f"Failed to get job (HTTP {status}): {body}", status_code=status)
        return Job.from_dict(body)

    def list_jobs(
        self,
        limit: int = 20,
        offset: int = 0,
    ) -> PaginationResult:
        """List jobs for the current organization/project.

        Args:
            limit: Maximum number of jobs to return (1-100).
            offset: Number of jobs to skip.

        Returns:
            A PaginationResult containing the jobs and pagination info.
        """
        status, body = self._router.handle_request(
            "GET",
            "/api/v1/jobs",
            self._ctx,
            query_params={"limit": limit, "offset": offset},
        )
        if status == 401:
            raise AuthenticationError("Failed to list jobs", body)
        if status != 200:
            raise ZCoderSDKException(f"Failed to list jobs (HTTP {status}): {body}", status_code=status)
        jobs = [Job.from_dict(j) for j in body.get("data", [])]
        pagination = body.get("pagination", {})
        return PaginationResult(
            items=jobs,
            limit=pagination.get("limit", limit),
            offset=pagination.get("offset", offset),
            total=pagination.get("total", 0),
            has_more=pagination.get("has_more", False),
        )

    def cancel_job(self, job_id: str) -> Job:
        """Cancel a job by ID.

        Args:
            job_id: The ID of the job to cancel.

        Returns:
            A Job instance representing the cancelled job.

        Raises:
            NotFoundError: If the job does not exist.
            AuthenticationError: If authentication fails.
        """
        status, body = self._router.handle_request("DELETE", f"/api/v1/jobs/{job_id}", self._ctx)
        if status == 401:
            raise AuthenticationError("Failed to cancel job", body)
        if status == 404:
            raise NotFoundError(f"Job {job_id} not found", body)
        if status != 200:
            raise ZCoderSDKException(f"Failed to cancel job (HTTP {status}): {body}", status_code=status)
        return Job.from_dict(body)

    def register_webhook(
        self,
        url: str,
        event_types: list[str] | None = None,
    ) -> dict[str, Any]:
        """Register a webhook for event notifications.

        Args:
            url: The webhook URL to receive notifications.
            event_types: Optional list of event types to subscribe to.

        Returns:
            A dict containing the webhook registration response.

        Raises:
            AuthenticationError: If authentication fails.
            ZCoderSDKException: For other errors.
        """
        payload: dict[str, Any] = {
            "url": url,
            "event_types": event_types or ["job.completed"],
        }
        status, body = self._router.handle_request("POST", "/api/v1/webhooks", self._ctx, payload=payload)
        if status == 401:
            raise AuthenticationError("Failed to register webhook", body)
        if status != 201:
            raise ZCoderSDKException(
                f"Webhook registration failed (HTTP {status}): {body}",
                status_code=status,
            )
        return body

    def iter_jobs(
        self,
        limit: int = 20,
        max_pages: int | None = None,
    ) -> Iterator[Job]:
        """Iterate over all jobs, handling pagination automatically.

        Args:
            limit: Number of jobs per page.
            max_pages: Maximum number of pages to fetch (None for unlimited).

        Yields:
            Job instances.
        """
        offset = 0
        pages_fetched = 0
        while True:
            result = self.list_jobs(limit=limit, offset=offset)
            yield from result.items
            pages_fetched += 1
            if not result.has_more:
                break
            if max_pages is not None and pages_fetched >= max_pages:
                break
            offset = result.next_offset

    # ── Async methods ──────────────────────────────────────────────────

    async def async_get_entitlements(self) -> dict[str, Any]:
        """Async version of get_entitlements."""
        return await asyncio.to_thread(self.get_entitlements)

    async def async_create_job(
        self,
        task: str,
        model: str | None = None,
        budget_usd: float | None = None,
        metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> Job:
        """Async version of create_job."""
        return await asyncio.to_thread(
            self.create_job,
            task,
            model=model,
            budget_usd=budget_usd,
            metadata=metadata,
            idempotency_key=idempotency_key,
        )

    async def async_get_job(self, job_id: str) -> Job:
        """Async version of get_job."""
        return await asyncio.to_thread(self.get_job, job_id)

    async def async_list_jobs(
        self,
        limit: int = 20,
        offset: int = 0,
    ) -> PaginationResult:
        """Async version of list_jobs."""
        return await asyncio.to_thread(self.list_jobs, limit=limit, offset=offset)

    async def async_cancel_job(self, job_id: str) -> Job:
        """Async version of cancel_job."""
        return await asyncio.to_thread(self.cancel_job, job_id)

    async def async_register_webhook(
        self,
        url: str,
        event_types: list[str] | None = None,
    ) -> dict[str, Any]:
        """Async version of register_webhook."""
        return await asyncio.to_thread(self.register_webhook, url, event_types=event_types)

    async def async_iter_jobs(
        self,
        limit: int = 20,
        max_pages: int | None = None,
    ) -> AsyncIterator[Job]:
        """Async iterator over all jobs, handling pagination automatically.

        Args:
            limit: Number of jobs per page.
            max_pages: Maximum number of pages to fetch (None for unlimited).

        Yields:
            Job instances.
        """
        offset = 0
        pages_fetched = 0
        while True:
            result = await self.async_list_jobs(limit=limit, offset=offset)
            for job in result.items:
                yield job
            pages_fetched += 1
            if not result.has_more:
                break
            if max_pages is not None and pages_fetched >= max_pages:
                break
            offset = result.next_offset

    # ── Async context manager ──────────────────────────────────────────

    async def __aenter__(self) -> ZCoderClient:
        """Enter async context manager."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit async context manager."""
        pass


__all__ = [
    "ZCoderClient",
    "ZCoderSDKException",
    "AuthenticationError",
    "RateLimitError",
    "NotFoundError",
    "ValidationError",
    "Job",
    "PaginationResult",
]
