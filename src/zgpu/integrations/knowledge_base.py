"""Optional client for the authenticated zGPU Knowledge Base REST API."""

from __future__ import annotations

import json
import math
import mimetypes
import urllib.error
import urllib.request
import uuid
from pathlib import PurePosixPath
from typing import Any, ClassVar
from urllib.parse import quote, urlencode, urlsplit

from zgpu.integrations.document_loaders import MAX_UPLOAD_BYTES


class KnowledgeBaseError(RuntimeError):
    """A knowledge service HTTP, transport, or protocol error."""

    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        super().__init__(f"zGPU Knowledge Base: {message}")


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class KnowledgeBaseClient:
    """Use bounded HTTPS requests to a tenant-scoped knowledge service."""

    MAX_RESPONSE_BYTES = 1_048_576
    MAX_DOCUMENTS = 500
    MAX_TOP_K = 20
    MAX_EXCERPT_CHARS = 600
    ALLOWED_SUFFIXES: ClassVar[set[str]] = {".pdf", ".md", ".markdown", ".txt"}

    def __init__(self, base_url: str, api_key: str, *, timeout: float = 20.0):
        if not isinstance(base_url, str) or len(base_url) > 512:
            raise ValueError("base_url must be a URL of at most 512 characters")
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in {"http", "https"}
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
            port = parsed.port
        except ValueError as exc:
            raise ValueError("base_url must contain a valid port") from exc
        if port == 0:
            raise ValueError("base_url port must be between 1 and 65535")
        if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("HTTP is allowed only for a loopback knowledge endpoint")
        if not isinstance(api_key, str) or not api_key.strip() or len(api_key) > 8192:
            raise ValueError("api_key must be a non-empty key of at most 8192 characters")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0.1 <= timeout <= 60:
            raise ValueError("timeout must be between 0.1 and 60 seconds")

        host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
        origin = f"{parsed.scheme}://{host}{f':{port}' if port is not None else ''}"
        self.base_url = f"{origin}/api/v1"
        self._api_key = api_key.strip()
        self.timeout = float(timeout)

    def _open(self, request: urllib.request.Request):
        return urllib.request.build_opener(_RejectRedirects()).open(request, timeout=self.timeout)

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        body: bytes | None = None,
        content_type: str | None = None,
    ) -> dict[str, Any] | list[Any] | None:
        if payload is not None:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            content_type = "application/json"
        headers = {"Accept": "application/json", "X-API-Key": self._api_key}
        if content_type:
            headers["Content-Type"] = content_type
        request = urllib.request.Request(f"{self.base_url}{path}", data=body, headers=headers, method=method)
        try:
            with self._open(request) as response:
                if response.geturl() != request.full_url:
                    raise KnowledgeBaseError(
                        502, "REDIRECT_REJECTED", "Knowledge service redirected the request"
                    )
                raw = response.read(self.MAX_RESPONSE_BYTES + 1)
                status = getattr(response, "status", 200)
        except urllib.error.HTTPError as exc:
            try:
                raw, status = exc.read(self.MAX_RESPONSE_BYTES + 1), exc.code
            finally:
                exc.close()
        except urllib.error.URLError as exc:
            raise KnowledgeBaseError(
                502, "UPSTREAM_UNAVAILABLE", "Could not reach knowledge service"
            ) from exc
        except TimeoutError as exc:
            raise KnowledgeBaseError(504, "UPSTREAM_TIMEOUT", "Knowledge service request timed out") from exc
        except OSError as exc:
            raise KnowledgeBaseError(
                502, "UPSTREAM_UNAVAILABLE", "Could not reach knowledge service"
            ) from exc

        if len(raw) > self.MAX_RESPONSE_BYTES:
            raise KnowledgeBaseError(
                502, "UPSTREAM_RESPONSE_TOO_LARGE", "Knowledge service response exceeded 1 MiB"
            )
        if 300 <= status < 400:
            raise KnowledgeBaseError(502, "REDIRECT_REJECTED", "Knowledge service redirected the request")
        if status >= 400:
            raise KnowledgeBaseError(status, "UPSTREAM_ERROR", f"request failed with status {status}")
        if status == 204 or not raw:
            result = None
        else:
            try:
                result = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise KnowledgeBaseError(
                    502, "INVALID_UPSTREAM_RESPONSE", "Knowledge service returned invalid JSON"
                ) from exc
        if not isinstance(result, (dict, list, type(None))):
            raise KnowledgeBaseError(
                502, "INVALID_UPSTREAM_RESPONSE", "Knowledge service returned an invalid response"
            )
        return result

    @staticmethod
    def _object(value: Any, name: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise KnowledgeBaseError(
                502, "INVALID_UPSTREAM_RESPONSE", f"Knowledge service returned invalid {name}"
            )
        return value

    @staticmethod
    def _identifier(value: str) -> str:
        if not isinstance(value, str) or not value or len(value) > 256:
            raise ValueError("identifier must contain 1 to 256 characters")
        return quote(value, safe="")

    def health(self) -> dict[str, Any]:
        result = self._object(self._request("GET", "/health"), "health data")
        status = result.get("status")
        if status not in {"ok", "degraded"}:
            raise KnowledgeBaseError(
                502, "INVALID_UPSTREAM_RESPONSE", "Knowledge service returned invalid health data"
            )
        return {key: result.get(key) for key in ("status", "qdrant", "metadata_store", "scanner")}

    def list_documents(self) -> list[dict[str, Any]]:
        result = self._request("GET", "/documents")
        if not isinstance(result, list) or len(result) > self.MAX_DOCUMENTS:
            raise KnowledgeBaseError(
                502, "INVALID_UPSTREAM_RESPONSE", "Knowledge service returned an invalid document list"
            )
        documents = []
        for item in result:
            record = self._object(item, "document record")
            if not isinstance(record.get("id"), str) or not isinstance(record.get("name"), str):
                raise KnowledgeBaseError(
                    502, "INVALID_UPSTREAM_RESPONSE", "Knowledge service returned an invalid document"
                )
            size = record.get("size_bytes", 0)
            if isinstance(size, bool) or not isinstance(size, int) or size < 0:
                raise KnowledgeBaseError(
                    502, "INVALID_UPSTREAM_RESPONSE", "Knowledge service returned invalid document size"
                )
            documents.append(
                {
                    "id": record["id"][:256],
                    "name": record["name"][:255],
                    "status": str(record.get("status", "unknown"))[:32],
                    "size_bytes": size,
                    "chunk_count": (
                        max(0, record.get("chunk_count", 0))
                        if isinstance(record.get("chunk_count", 0), int)
                        and not isinstance(record.get("chunk_count", 0), bool)
                        else 0
                    ),
                    "created_at": str(record.get("created_at", ""))[:64],
                    "updated_at": str(record.get("updated_at", ""))[:64],
                    "error": str(record["error"])[:500] if isinstance(record.get("error"), str) else None,
                }
            )
        return documents

    def search(self, query: str, *, top_k: int = 5) -> list[dict[str, Any]]:
        if not isinstance(query, str) or not query.strip() or len(query) > 20_000:
            raise ValueError("query must contain 1 to 20000 characters")
        if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= self.MAX_TOP_K:
            raise ValueError(f"top_k must be between 1 and {self.MAX_TOP_K}")
        response = self._object(
            self._request("POST", "/search", payload={"query": query.strip(), "top_k": top_k}),
            "search response",
        )
        results = response.get("results")
        if not isinstance(results, list) or len(results) > top_k:
            raise KnowledgeBaseError(
                502, "INVALID_UPSTREAM_RESPONSE", "Knowledge service returned invalid search results"
            )
        normalized = []
        for item in results:
            source = self._object(item, "search result")
            identifier = source.get("document_id")
            title = source.get("document_name")
            text = source.get("text")
            score = source.get("score")
            if (
                not isinstance(identifier, str)
                or not isinstance(title, str)
                or not isinstance(text, str)
                or isinstance(score, bool)
                or not isinstance(score, (int, float))
                or not math.isfinite(score)
            ):
                raise KnowledgeBaseError(
                    502, "INVALID_UPSTREAM_RESPONSE", "Knowledge service returned invalid search result data"
                )
            normalized.append(
                {
                    "id": identifier[:256],
                    "title": title[:120],
                    "excerpt": text[: self.MAX_EXCERPT_CHARS],
                    "score": float(score),
                }
            )
        return normalized

    def ingest_file(self, filename: str, data: bytes) -> dict[str, Any]:
        self.validate_upload(filename, data)

        boundary = f"zgpu-{uuid.uuid4().hex}"
        quoted_name = filename.replace("\\", "\\\\").replace('"', '\\"')
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        body = (
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; filename="{quoted_name}"\r\n'
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode()
            + data
            + f"\r\n--{boundary}--\r\n".encode("ascii")
        )
        result = self._object(
            self._request(
                "POST",
                "/ingest/async",
                body=body,
                content_type=f"multipart/form-data; boundary={boundary}",
            ),
            "ingestion response",
        )
        document = self._object(result.get("document"), "ingested document")
        job = self._object(result.get("job"), "ingestion job")
        if not isinstance(document.get("id"), str) or not isinstance(job.get("id"), str):
            raise KnowledgeBaseError(
                502, "INVALID_UPSTREAM_RESPONSE", "Knowledge service returned an invalid ingestion job"
            )
        return {
            "document": {"id": document["id"][:256], "name": str(document.get("name", filename))[:255]},
            "job": {"id": job["id"][:256], "status": str(job.get("status", "queued"))[:32]},
        }

    @classmethod
    def validate_upload(cls, filename: str, data: bytes) -> None:
        if (
            not isinstance(filename, str)
            or not filename
            or len(filename) > 255
            or "/" in filename
            or "\\" in filename
            or any(ord(character) < 32 for character in filename)
            or PurePosixPath(filename).suffix.lower() not in cls.ALLOWED_SUFFIXES
        ):
            raise ValueError("filename must be a supported .pdf, .md, .markdown, or .txt name")
        if not isinstance(data, bytes) or not data:
            raise ValueError("uploaded file must not be empty")
        if len(data) > MAX_UPLOAD_BYTES:
            raise ValueError(f"uploaded file must be at most {MAX_UPLOAD_BYTES} bytes")

    def list_ingestion_jobs(self, *, limit: int = 100) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        result = self._request("GET", f"/ingest/jobs?{urlencode({'limit': limit})}")
        if not isinstance(result, list) or len(result) > limit:
            raise KnowledgeBaseError(
                502, "INVALID_UPSTREAM_RESPONSE", "Knowledge service returned invalid ingestion jobs"
            )
        jobs = []
        for item in result:
            job = self._object(item, "ingestion job")
            if not isinstance(job.get("id"), str) or not isinstance(job.get("document_id"), str):
                raise KnowledgeBaseError(
                    502, "INVALID_UPSTREAM_RESPONSE", "Knowledge service returned invalid job data"
                )
            jobs.append(
                {
                    "id": job["id"][:256],
                    "document_id": job["document_id"][:256],
                    "status": str(job.get("status", "unknown"))[:32],
                    "attempts": job.get("attempts", 0) if isinstance(job.get("attempts", 0), int) else 0,
                    "updated_at": str(job.get("updated_at", ""))[:64],
                    "error": str(job["error"])[:500] if isinstance(job.get("error"), str) else None,
                }
            )
        return jobs

    def get_ingestion_job(self, job_id: str) -> dict[str, Any]:
        result = self._object(
            self._request("GET", f"/ingest/jobs/{self._identifier(job_id)}"), "ingestion job"
        )
        if not isinstance(result.get("id"), str) or not isinstance(result.get("document_id"), str):
            raise KnowledgeBaseError(
                502, "INVALID_UPSTREAM_RESPONSE", "Knowledge service returned invalid job data"
            )
        return {
            "id": result["id"][:256],
            "document_id": result["document_id"][:256],
            "status": str(result.get("status", "unknown"))[:32],
            "attempts": result.get("attempts", 0) if isinstance(result.get("attempts", 0), int) else 0,
            "updated_at": str(result.get("updated_at", ""))[:64],
            "error": str(result["error"])[:500] if isinstance(result.get("error"), str) else None,
        }

    def cancel_ingestion_job(self, job_id: str) -> None:
        self._request("DELETE", f"/ingest/jobs/{self._identifier(job_id)}")
