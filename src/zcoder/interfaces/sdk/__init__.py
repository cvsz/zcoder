"""zcoder.interfaces.sdk — Official ZCoder Python SDK.

Provides a typed, async-capable client for interacting with the ZCoder API,
including job management, webhook registration, entitlement queries, and
credential management.

Example usage:

    from zcoder.interfaces.sdk import ZCoderClient

    client = ZCoderClient(
        api_key="zck_...",
        organization_id="org_123",
        project_id="proj_456",
    )
    job = client.create_job("Refactor the login module")
    print(job.id)
"""

from zcoder.interfaces.sdk.client import (
    AuthenticationError,
    Job,
    NotFoundError,
    PaginationResult,
    RateLimitError,
    ValidationError,
    ZCoderClient,
    ZCoderSDKException,
)

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
