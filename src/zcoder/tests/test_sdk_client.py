"""Tests for zcoder.interfaces.sdk - Python SDK client."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from zcoder.interfaces.sdk import (
    AuthenticationError,
    Job,
    NotFoundError,
    PaginationResult,
    RateLimitError,
    ValidationError,
    ZCoderClient,
    ZCoderSDKException,
)


class TestZCoderSDKException:
    """Tests for ZCoderSDKException."""

    def test_creation(self):
        err = ZCoderSDKException("Something went wrong")
        assert str(err) == "Something went wrong"
        assert err.status_code is None
        assert err.details == {}

    def test_creation_with_details(self):
        err = ZCoderSDKException("Failed", status_code=500, details={"code": "INTERNAL"})
        assert err.status_code == 500
        assert err.details == {"code": "INTERNAL"}


class TestAuthenticationError:
    """Tests for AuthenticationError."""

    def test_defaults(self):
        err = AuthenticationError("Invalid API key")
        assert err.status_code == 401
        assert str(err) == "Invalid API key"


class TestRateLimitError:
    """Tests for RateLimitError."""

    def test_defaults(self):
        err = RateLimitError("Too many requests")
        assert err.status_code == 429
        assert str(err) == "Too many requests"


class TestNotFoundError:
    """Tests for NotFoundError."""

    def test_defaults(self):
        err = NotFoundError("Job not found")
        assert err.status_code == 404
        assert str(err) == "Job not found"


class TestValidationError:
    """Tests for ValidationError."""

    def test_defaults(self):
        err = ValidationError("Invalid field")
        assert err.status_code == 422
        assert str(err) == "Invalid field"


class TestJob:
    """Tests for Job dataclass."""

    def test_creation(self):
        job = Job(
            id="job_123",
            task="Refactor code",
            status="READY",
            model="zcoder-pro",
            created_at=1000.0,
            updated_at=2000.0,
        )
        assert job.id == "job_123"
        assert job.task == "Refactor code"
        assert job.status == "READY"
        assert job.model == "zcoder-pro"
        assert job.created_at == 1000.0
        assert job.updated_at == 2000.0
        assert job.organization_id is None
        assert job.project_id is None
        assert job.budget_usd == 0.0
        assert job.cost_usd == 0.0
        assert job.metadata == {}
        assert job.runtime == "direct"
        assert job.workspace == "."

    def test_from_dict(self):
        data = {
            "id": "job_456",
            "task": "Write tests",
            "status": "COMPLETED",
            "model": "zcoder-flash",
            "created_at": 3000.0,
            "updated_at": 4000.0,
            "organization_id": "org_1",
            "project_id": "proj_1",
            "budget_usd": 0.05,
            "cost_usd": 0.03,
            "metadata": {"key": "value"},
            "runtime": "sandboxed",
            "workspace": "/tmp",
        }
        job = Job.from_dict(data)
        assert job.id == "job_456"
        assert job.task == "Write tests"
        assert job.status == "COMPLETED"
        assert job.model == "zcoder-flash"
        assert job.created_at == 3000.0
        assert job.updated_at == 4000.0
        assert job.organization_id == "org_1"
        assert job.project_id == "proj_1"
        assert job.budget_usd == 0.05
        assert job.cost_usd == 0.03
        assert job.metadata == {"key": "value"}
        assert job.runtime == "sandboxed"
        assert job.workspace == "/tmp"

    def test_repr(self):
        job = Job(
            id="job_789",
            task="A very long task description that should be truncated in repr",
            status="RUNNING",
            model="zcoder-pro",
            created_at=1.0,
            updated_at=2.0,
        )
        repr_str = repr(job)
        assert "job_789" in repr_str
        assert "RUNNING" in repr_str


class TestPaginationResult:
    """Tests for PaginationResult."""

    def test_creation(self):
        items = [{"id": "1"}, {"id": "2"}]
        result = PaginationResult(
            items=items,
            limit=10,
            offset=0,
            total=25,
            has_more=True,
        )
        assert result.items == items
        assert result.limit == 10
        assert result.offset == 0
        assert result.total == 25
        assert result.has_more is True
        assert result.next_offset == 10

    def test_next_offset(self):
        result = PaginationResult(
            items=[],
            limit=25,
            offset=50,
            total=100,
            has_more=False,
        )
        assert result.next_offset == 75


class TestZCoderClient:
    """Tests for ZCoderClient."""

    def test_creation(self):
        client = ZCoderClient(
            api_key="zck_abc123",
            organization_id="org_123",
            project_id="proj_456",
        )
        assert client.api_key == "zck_abc123"
        assert client.organization_id == "org_123"
        assert client.project_id == "proj_456"
        assert client.base_url is None
        assert client.timeout == 60.0

    def test_creation_with_base_url(self):
        client = ZCoderClient(
            api_key="key",
            organization_id="org",
            base_url="https://api.example.com",
            timeout=30.0,
        )
        assert client.base_url == "https://api.example.com"
        assert client.timeout == 30.0

    def test_create_job_success(self):
        router = MagicMock()
        router.handle_request.return_value = (
            201,
            {
                "id": "job_1",
                "task": "Test task",
                "status": "READY",
                "model": "zcoder-flash",
                "created_at": 1000.0,
                "updated_at": 1000.0,
            },
        )
        client = ZCoderClient(
            api_key="key",
            organization_id="org",
            router=router,
        )
        job = client.create_job("Test task")
        assert isinstance(job, Job)
        assert job.id == "job_1"
        assert job.task == "Test task"
        assert job.status == "READY"

    def test_create_job_with_options(self):
        router = MagicMock()
        router.handle_request.return_value = (
            201,
            {
                "id": "job_2",
                "task": "Task with options",
                "status": "READY",
                "model": "zcoder-pro",
                "created_at": 2000.0,
                "updated_at": 2000.0,
                "budget_usd": 1.0,
                "cost_usd": 0.0,
                "metadata": {"env": "test"},
            },
        )
        client = ZCoderClient(
            api_key="key",
            organization_id="org",
            router=router,
        )
        job = client.create_job(
            task="Task with options",
            model="zcoder-pro",
            budget_usd=1.0,
            metadata={"env": "test"},
            idempotency_key="idem-key-1",
        )
        assert job.id == "job_2"
        assert job.model == "zcoder-pro"
        assert job.budget_usd == 1.0
        assert job.metadata == {"env": "test"}

        # Verify the router was called with correct payload
        call_args = router.handle_request.call_args
        assert call_args[0][0] == "POST"
        assert call_args[0][1] == "/api/v1/jobs"
        kwargs = call_args[1]
        assert kwargs["payload"]["task"] == "Task with options"
        assert kwargs["payload"]["model"] == "zcoder-pro"
        assert kwargs["payload"]["budget_usd"] == 1.0
        assert kwargs["payload"]["metadata"] == {"env": "test"}
        assert kwargs["idempotency_key"] == "idem-key-1"

    def test_create_job_auth_error(self):
        router = MagicMock()
        router.handle_request.return_value = (401, {"error": "Invalid API key"})
        client = ZCoderClient(
            api_key="key",
            organization_id="org",
            router=router,
        )
        with pytest.raises(AuthenticationError):
            client.create_job("Test task")

    def test_create_job_rate_limit(self):
        router = MagicMock()
        router.handle_request.return_value = (429, {"error": "Rate limited"})
        client = ZCoderClient(
            api_key="key",
            organization_id="org",
            router=router,
        )
        with pytest.raises(RateLimitError):
            client.create_job("Test task")

    def test_create_job_validation_error(self):
        router = MagicMock()
        router.handle_request.return_value = (422, {"error": "Invalid task"})
        client = ZCoderClient(
            api_key="key",
            organization_id="org",
            router=router,
        )
        with pytest.raises(ValidationError):
            client.create_job("Test task")

    def test_get_job_success(self):
        router = MagicMock()
        router.handle_request.return_value = (
            200,
            {
                "id": "job_3",
                "task": "Get me",
                "status": "COMPLETED",
                "model": "zcoder-pro",
                "created_at": 3000.0,
                "updated_at": 4000.0,
            },
        )
        client = ZCoderClient(
            api_key="key",
            organization_id="org",
            router=router,
        )
        job = client.get_job("job_3")
        assert isinstance(job, Job)
        assert job.id == "job_3"
        assert job.status == "COMPLETED"

    def test_get_job_not_found(self):
        router = MagicMock()
        router.handle_request.return_value = (404, {"error": "Not found"})
        client = ZCoderClient(
            api_key="key",
            organization_id="org",
            router=router,
        )
        with pytest.raises(NotFoundError):
            client.get_job("nonexistent")

    def test_list_jobs(self):
        router = MagicMock()
        router.handle_request.return_value = (
            200,
            {
                "data": [
                    {
                        "id": "job_1",
                        "task": "Task 1",
                        "status": "COMPLETED",
                        "model": "zcoder-flash",
                        "created_at": 1000.0,
                        "updated_at": 1000.0,
                    },
                    {
                        "id": "job_2",
                        "task": "Task 2",
                        "status": "READY",
                        "model": "zcoder-pro",
                        "created_at": 2000.0,
                        "updated_at": 2000.0,
                    },
                ],
                "pagination": {
                    "limit": 20,
                    "offset": 0,
                    "total": 2,
                    "has_more": False,
                },
            },
        )
        client = ZCoderClient(
            api_key="key",
            organization_id="org",
            router=router,
        )
        result = client.list_jobs(limit=20, offset=0)
        assert isinstance(result, PaginationResult)
        assert len(result.items) == 2
        assert result.items[0].id == "job_1"
        assert result.items[1].id == "job_2"
        assert result.total == 2
        assert result.has_more is False

    def test_cancel_job_success(self):
        router = MagicMock()
        router.handle_request.return_value = (
            200,
            {
                "id": "job_4",
                "task": "To cancel",
                "status": "CANCELLED",
                "model": "zcoder-flash",
                "created_at": 4000.0,
                "updated_at": 5000.0,
            },
        )
        client = ZCoderClient(
            api_key="key",
            organization_id="org",
            router=router,
        )
        job = client.cancel_job("job_4")
        assert isinstance(job, Job)
        assert job.id == "job_4"
        assert job.status == "CANCELLED"

    def test_register_webhook(self):
        router = MagicMock()
        router.handle_request.return_value = (
            201,
            {
                "webhook_id": "wh_1",
                "url": "https://example.com/webhook",
                "event_types": ["job.completed"],
            },
        )
        client = ZCoderClient(
            api_key="key",
            organization_id="org",
            router=router,
        )
        result = client.register_webhook(
            "https://example.com/webhook",
            event_types=["job.completed", "job.failed"],
        )
        assert result["webhook_id"] == "wh_1"
        assert result["url"] == "https://example.com/webhook"

    def test_iter_jobs_single_page(self):
        router = MagicMock()
        router.handle_request.return_value = (
            200,
            {
                "data": [
                    {
                        "id": "job_1",
                        "task": "Task 1",
                        "status": "COMPLETED",
                        "model": "zcoder-flash",
                        "created_at": 1000.0,
                        "updated_at": 1000.0,
                    },
                    {
                        "id": "job_2",
                        "task": "Task 2",
                        "status": "COMPLETED",
                        "model": "zcoder-flash",
                        "created_at": 2000.0,
                        "updated_at": 2000.0,
                    },
                ],
                "pagination": {
                    "limit": 20,
                    "offset": 0,
                    "total": 2,
                    "has_more": False,
                },
            },
        )
        client = ZCoderClient(
            api_key="key",
            organization_id="org",
            router=router,
        )
        jobs = list(client.iter_jobs())
        assert len(jobs) == 2
        assert jobs[0].id == "job_1"
        assert jobs[1].id == "job_2"

    def test_iter_jobs_multiple_pages(self):
        router = MagicMock()
        # First page
        router.handle_request.side_effect = [
            (
                200,
                {
                    "data": [
                        {
                            "id": "job_1",
                            "task": "Task 1",
                            "status": "COMPLETED",
                            "model": "zcoder-flash",
                            "created_at": 1000.0,
                            "updated_at": 1000.0,
                        },
                    ],
                    "pagination": {
                        "limit": 1,
                        "offset": 0,
                        "total": 2,
                        "has_more": True,
                    },
                },
            ),
            # Second page
            (
                200,
                {
                    "data": [
                        {
                            "id": "job_2",
                            "task": "Task 2",
                            "status": "COMPLETED",
                            "model": "zcoder-flash",
                            "created_at": 2000.0,
                            "updated_at": 2000.0,
                        },
                    ],
                    "pagination": {
                        "limit": 1,
                        "offset": 1,
                        "total": 2,
                        "has_more": False,
                    },
                },
            ),
        ]
        client = ZCoderClient(
            api_key="key",
            organization_id="org",
            router=router,
        )
        jobs = list(client.iter_jobs(limit=1, max_pages=2))
        assert len(jobs) == 2
        assert jobs[0].id == "job_1"
        assert jobs[1].id == "job_2"


class TestAsyncClient:
    """Tests for async client methods and context manager."""

    @pytest.mark.asyncio
    async def test_async_create_job(self):
        router = MagicMock()
        router.handle_request.return_value = (
            201,
            {
                "id": "job_async_1",
                "task": "Async task",
                "status": "READY",
                "model": "zcoder-flash",
                "created_at": 1000.0,
                "updated_at": 1000.0,
            },
        )
        client = ZCoderClient(
            api_key="key",
            organization_id="org",
            router=router,
        )
        job = await client.async_create_job("Async task")
        assert isinstance(job, Job)
        assert job.id == "job_async_1"
        assert job.task == "Async task"
        assert job.status == "READY"

    @pytest.mark.asyncio
    async def test_async_get_job(self):
        router = MagicMock()
        router.handle_request.return_value = (
            200,
            {
                "id": "job_async_2",
                "task": "Get me async",
                "status": "COMPLETED",
                "model": "zcoder-pro",
                "created_at": 3000.0,
                "updated_at": 4000.0,
            },
        )
        client = ZCoderClient(
            api_key="key",
            organization_id="org",
            router=router,
        )
        job = await client.async_get_job("job_async_2")
        assert isinstance(job, Job)
        assert job.id == "job_async_2"
        assert job.status == "COMPLETED"

    @pytest.mark.asyncio
    async def test_async_list_jobs(self):
        router = MagicMock()
        router.handle_request.return_value = (
            200,
            {
                "data": [
                    {
                        "id": "job_async_1",
                        "task": "Task 1",
                        "status": "COMPLETED",
                        "model": "zcoder-flash",
                        "created_at": 1000.0,
                        "updated_at": 1000.0,
                    },
                ],
                "pagination": {
                    "limit": 20,
                    "offset": 0,
                    "total": 1,
                    "has_more": False,
                },
            },
        )
        client = ZCoderClient(
            api_key="key",
            organization_id="org",
            router=router,
        )
        result = await client.async_list_jobs(limit=20, offset=0)
        assert isinstance(result, PaginationResult)
        assert len(result.items) == 1
        assert result.items[0].id == "job_async_1"

    @pytest.mark.asyncio
    async def test_async_cancel_job(self):
        router = MagicMock()
        router.handle_request.return_value = (
            200,
            {
                "id": "job_async_4",
                "task": "To cancel",
                "status": "CANCELLED",
                "model": "zcoder-flash",
                "created_at": 4000.0,
                "updated_at": 5000.0,
            },
        )
        client = ZCoderClient(
            api_key="key",
            organization_id="org",
            router=router,
        )
        job = await client.async_cancel_job("job_async_4")
        assert isinstance(job, Job)
        assert job.id == "job_async_4"
        assert job.status == "CANCELLED"

    @pytest.mark.asyncio
    async def test_async_register_webhook(self):
        router = MagicMock()
        router.handle_request.return_value = (
            201,
            {
                "webhook_id": "wh_async_1",
                "url": "https://example.com/webhook",
                "event_types": ["job.completed"],
            },
        )
        client = ZCoderClient(
            api_key="key",
            organization_id="org",
            router=router,
        )
        result = await client.async_register_webhook(
            "https://example.com/webhook",
            event_types=["job.completed"],
        )
        assert result["webhook_id"] == "wh_async_1"
        assert result["url"] == "https://example.com/webhook"

    @pytest.mark.asyncio
    async def test_async_iter_jobs(self):
        router = MagicMock()
        router.handle_request.return_value = (
            200,
            {
                "data": [
                    {
                        "id": "job_async_1",
                        "task": "Task 1",
                        "status": "COMPLETED",
                        "model": "zcoder-flash",
                        "created_at": 1000.0,
                        "updated_at": 1000.0,
                    },
                    {
                        "id": "job_async_2",
                        "task": "Task 2",
                        "status": "COMPLETED",
                        "model": "zcoder-flash",
                        "created_at": 2000.0,
                        "updated_at": 2000.0,
                    },
                ],
                "pagination": {
                    "limit": 20,
                    "offset": 0,
                    "total": 2,
                    "has_more": False,
                },
            },
        )
        client = ZCoderClient(
            api_key="key",
            organization_id="org",
            router=router,
        )
        jobs = []
        async for job in client.async_iter_jobs():
            jobs.append(job)
        assert len(jobs) == 2
        assert jobs[0].id == "job_async_1"
        assert jobs[1].id == "job_async_2"

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        router = MagicMock()
        router.handle_request.return_value = (
            201,
            {
                "id": "job_ctx_1",
                "task": "Context manager task",
                "status": "READY",
                "model": "zcoder-flash",
                "created_at": 1000.0,
                "updated_at": 1000.0,
            },
        )
        async with ZCoderClient(
            api_key="key",
            organization_id="org",
            router=router,
        ) as client:
            job = await client.async_create_job("Context manager task")
            assert isinstance(job, Job)
            assert job.id == "job_ctx_1"
            assert job.task == "Context manager task"
