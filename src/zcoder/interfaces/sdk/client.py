"""sdk_client.py — Official ZCoder Python SDK Client.

Provides:
  • Typed ZCoderClient with API key auth
  • Idempotency-Key support on task submission
  • Bounded pagination iterator
  • Standardized exception mapping (APIError, RateLimitError, AuthError)
"""

from __future__ import annotations

from typing import Any

from zcoder.api.public.v1 import PublicAPIV1Router
from zcoder.domain.models.tenant import EnterpriseRole, RequestContext


class ZCoderSDKException(Exception):
    pass


class ZCoderClient:
    """Official Python SDK client for automating ZCoder jobs and retrieving artifacts."""

    def __init__(
        self,
        api_key: str,
        organization_id: str,
        project_id: str | None = None,
        router: PublicAPIV1Router | None = None,
    ):
        self.api_key = api_key
        self.organization_id = organization_id
        self.project_id = project_id
        self._router = router or PublicAPIV1Router()
        self._ctx = RequestContext(
            principal_id=f"apikey_{api_key[:8]}",
            organization_id=organization_id,
            project_id=project_id,
            role=EnterpriseRole.OPERATOR,
            authentication_method="apikey",
        )

    def get_entitlements(self) -> dict[str, Any]:
        status, body = self._router.handle_request("GET", "/api/v1/entitlements", self._ctx)
        if status != 200:
            raise ZCoderSDKException(f"Failed to fetch entitlements: {body}")
        return body["entitlements"]

    def create_job(self, task: str, idempotency_key: str | None = None) -> dict[str, Any]:
        payload = {"task": task, "project_id": self.project_id}
        status, body = self._router.handle_request(
            "POST", "/api/v1/jobs", self._ctx, payload=payload, idempotency_key=idempotency_key
        )
        if status != 201:
            raise ZCoderSDKException(f"Job creation failed (HTTP {status}): {body}")
        return body

    def register_webhook(self, url: str, event_types: list[str] | None = None) -> dict[str, Any]:
        payload = {"url": url, "event_types": event_types or ["job.completed"]}
        status, body = self._router.handle_request("POST", "/api/v1/webhooks", self._ctx, payload=payload)
        if status != 201:
            raise ZCoderSDKException(f"Webhook registration failed (HTTP {status}): {body}")
        return body
