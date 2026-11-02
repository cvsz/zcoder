"""Optional, server-side client for the authenticated engineering jobs API.

The client keeps the zGPU core independent from an external engineering
service's deployment/runtime and provides a typed boundary for its job API.
"""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
import uuid
from typing import Any
from urllib.parse import quote, urlsplit


class EngineeringJobsError(RuntimeError):
    """An HTTP or structured API error returned by the engineering service."""

    def __init__(self, status: int, code: str, message: str, request_id: str | None = None):
        self.status = status
        self.code = code
        self.request_id = request_id
        super().__init__(f"zGPU Engineering: {message}")


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class EngineeringJobsClient:
    """Call job and entitlement endpoints over HTTPS."""

    MAX_RESPONSE_BYTES = 1_048_576

    def __init__(self, base_url: str, bearer_token: str, timeout: float = 10.0):
        if not isinstance(base_url, str) or len(base_url) > 512:
            raise ValueError("base_url must be a URL of at most 512 characters")
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError(
                "base_url must be an HTTP(S) origin without credentials, path, query, or fragment"
            )
        try:
            # Accessing .port validates malformed and out-of-range ports.
            port = parsed.port
        except ValueError as exc:
            raise ValueError("base_url must contain a valid port") from exc
        if port == 0:
            raise ValueError("base_url port must be between 1 and 65535")
        if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("HTTP is allowed only for a loopback engineering endpoint")
        if not isinstance(bearer_token, str) or not bearer_token.strip() or len(bearer_token) > 8192:
            raise ValueError("bearer_token must be a non-empty token of at most 8192 characters")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0.1 <= timeout <= 30:
            raise ValueError("timeout must be between 0.1 and 30 seconds")

        host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
        self.base_url = f"{parsed.scheme}://{host}{f':{port}' if port is not None else ''}"
        self._bearer_token = bearer_token.strip()
        self.timeout = float(timeout)

    def _open(self, request: urllib.request.Request):
        opener = urllib.request.build_opener(_RejectRedirects())
        return opener.open(request, timeout=self.timeout)

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._bearer_token}",
            "User-Agent": "zGPU-engineering-adapter/1.0",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        request = urllib.request.Request(f"{self.base_url}{path}", data=body, headers=headers, method=method)
        try:
            with self._open(request) as response:
                if response.geturl() != request.full_url:
                    raise EngineeringJobsError(
                        502, "REDIRECT_REJECTED", "Engineering endpoint redirected the request"
                    )
                raw = response.read(self.MAX_RESPONSE_BYTES + 1)
                status = getattr(response, "status", 200)
        except urllib.error.HTTPError as exc:
            raw = exc.read(self.MAX_RESPONSE_BYTES + 1)
            status = exc.code
        except urllib.error.URLError as exc:
            raise EngineeringJobsError(
                502, "UPSTREAM_UNAVAILABLE", "Could not reach engineering service"
            ) from exc
        except TimeoutError as exc:
            raise EngineeringJobsError(
                504, "UPSTREAM_TIMEOUT", "Engineering service request timed out"
            ) from exc

        if len(raw) > self.MAX_RESPONSE_BYTES:
            raise EngineeringJobsError(
                502, "UPSTREAM_RESPONSE_TOO_LARGE", "Engineering service response exceeded 1 MiB"
            )
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EngineeringJobsError(
                502, "INVALID_UPSTREAM_RESPONSE", "Engineering service returned invalid JSON"
            ) from exc
        if not isinstance(result, dict):
            raise EngineeringJobsError(
                502, "INVALID_UPSTREAM_RESPONSE", "Engineering service response must be a JSON object"
            )
        if status >= 400:
            error = result.get("error", {})
            if not isinstance(error, dict):
                error = {}
            raise EngineeringJobsError(
                status,
                str(error.get("code", "UPSTREAM_ERROR")),
                "request failed",
                str(error.get("request_id")) if error.get("request_id") else None,
            )
        return result

    def get_entitlements(self) -> dict[str, Any]:
        """Return entitlements visible to the bearer principal."""
        return self._request("GET", "/api/v1/entitlements")

    def list_jobs(self, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError("offset must be a non-negative integer")
        return self._request("GET", f"/api/v1/jobs?limit={limit}&offset={offset}")

    def get_job(self, job_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/jobs/{quote(self._identifier(job_id), safe='')}")

    def cancel_job(self, job_id: str, *, idempotency_key: str | None = None) -> dict[str, Any]:
        if idempotency_key is not None and (
            not isinstance(idempotency_key, str)
            or not idempotency_key.strip()
            or len(idempotency_key) > 256
            or any(ord(character) < 32 for character in idempotency_key)
        ):
            raise ValueError("idempotency_key must contain 1 to 256 printable characters")
        return self._request(
            "DELETE",
            f"/api/v1/jobs/{quote(self._identifier(job_id), safe='')}",
            idempotency_key=idempotency_key,
        )

    def submit_job(
        self,
        task: str,
        *,
        model: str | None = None,
        runtime: str = "direct",
        budget_usd: float = 0.0,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(task, str) or not task.strip() or len(task.strip()) > 100_000:
            raise ValueError("task must contain 1 to 100000 characters")
        if runtime not in {"direct", "fake", "noop"}:
            raise ValueError("runtime must be direct, fake, or noop")
        if model is not None and (not isinstance(model, str) or not model.strip() or len(model) > 256):
            raise ValueError("model must be omitted or contain 1 to 256 characters")
        if (
            isinstance(budget_usd, bool)
            or not isinstance(budget_usd, (int, float))
            or not math.isfinite(budget_usd)
            or budget_usd < 0
        ):
            raise ValueError("budget_usd must be a finite non-negative number")
        if idempotency_key is not None and (
            not isinstance(idempotency_key, str)
            or not idempotency_key.strip()
            or len(idempotency_key) > 256
            or any(ord(character) < 32 for character in idempotency_key)
        ):
            raise ValueError("idempotency_key must contain 1 to 256 printable characters")
        payload: dict[str, Any] = {
            "task": task.strip(),
            "runtime": runtime,
            "budget_usd": float(budget_usd),
        }
        if model is not None:
            payload["model"] = model.strip()
        return self._request(
            "POST",
            "/api/v1/jobs",
            payload=payload,
            idempotency_key=idempotency_key or str(uuid.uuid4()),
        )

    @staticmethod
    def _identifier(value: str) -> str:
        if not isinstance(value, str) or not value or len(value) > 256:
            raise ValueError("identifier must contain 1 to 256 characters")
        return value
