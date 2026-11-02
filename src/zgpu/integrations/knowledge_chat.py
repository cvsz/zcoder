"""Optional, server-side client for a knowledge service's chat API.

This adapter uses an HTTP contract only; callers must keep the API token
outside browser code.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlsplit


class KnowledgeChatError(RuntimeError):
    """An upstream knowledge service HTTP, transport, or protocol error."""

    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        super().__init__(f"zGPU Knowledge: {message}")


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class KnowledgeChatClient:
    """Call chat session and streaming endpoints without third-party deps."""

    MAX_RESPONSE_BYTES = 1_048_576
    MAX_STREAM_BYTES = 8_388_608
    MAX_PACKET_BYTES = 262_144

    def __init__(
        self,
        base_url: str,
        api_token: str,
        *,
        api_prefix: str = "/api",
        timeout: float = 15.0,
        max_stream_seconds: float = 300.0,
    ):
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
        if (
            not isinstance(api_prefix, str)
            or not api_prefix.startswith("/")
            or "?" in api_prefix
            or "#" in api_prefix
        ):
            raise ValueError("api_prefix must be an absolute URL path")
        api_prefix = api_prefix.rstrip("/")
        if len(api_prefix) > 128 or ".." in api_prefix.split("/"):
            raise ValueError("api_prefix is invalid")
        if not isinstance(api_token, str) or not api_token.strip() or len(api_token) > 8192:
            raise ValueError("api_token must be a non-empty token of at most 8192 characters")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0.1 <= timeout <= 60:
            raise ValueError("timeout must be between 0.1 and 60 seconds")
        if (
            isinstance(max_stream_seconds, bool)
            or not isinstance(max_stream_seconds, (int, float))
            or not 1 <= max_stream_seconds <= 1800
        ):
            raise ValueError("max_stream_seconds must be between 1 and 1800 seconds")

        host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
        origin = f"{parsed.scheme}://{host}{f':{port}' if port is not None else ''}"
        self.base_url = f"{origin}{api_prefix}"
        self._api_token = api_token.strip()
        self.timeout = float(timeout)
        self.max_stream_seconds = float(max_stream_seconds)

    def _open(self, request: urllib.request.Request):
        return urllib.request.build_opener(_RejectRedirects()).open(request, timeout=self.timeout)

    def _request_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers=self._headers(json_body=True),
            method="POST",
        )
        try:
            with self._open(request) as response:
                if response.geturl() != request.full_url:
                    raise KnowledgeChatError(
                        502, "REDIRECT_REJECTED", "Knowledge service redirected the request"
                    )
                raw = response.read(self.MAX_RESPONSE_BYTES + 1)
                status = getattr(response, "status", 200)
        except urllib.error.HTTPError as exc:
            raw, status = exc.read(self.MAX_RESPONSE_BYTES + 1), exc.code
        except urllib.error.URLError as exc:
            raise KnowledgeChatError(
                502, "UPSTREAM_UNAVAILABLE", "Could not reach knowledge service"
            ) from exc
        except TimeoutError as exc:
            raise KnowledgeChatError(504, "UPSTREAM_TIMEOUT", "Knowledge service request timed out") from exc

        result = self._decode_object(raw)
        if status >= 400:
            raise KnowledgeChatError(status, "UPSTREAM_ERROR", f"request failed with status {status}")
        return result

    def create_chat_session(self, *, persona_id: int | None = None, project_id: str | None = None) -> str:
        """Create a session and return its upstream identifier."""
        payload: dict[str, Any] = {}
        if persona_id is not None:
            if isinstance(persona_id, bool) or not isinstance(persona_id, int) or persona_id < 0:
                raise ValueError("persona_id must be a non-negative integer")
            payload["persona_id"] = persona_id
        if project_id is not None:
            if not isinstance(project_id, str) or not project_id or len(project_id) > 256:
                raise ValueError("project_id must contain 1 to 256 characters")
            payload["project_id"] = project_id
        result = self._request_json("/chat/create-chat-session", payload)
        session_id = result.get("chat_session_id")
        if not isinstance(session_id, str) or not session_id or len(session_id) > 256:
            raise KnowledgeChatError(
                502, "INVALID_UPSTREAM_RESPONSE", "Knowledge service returned an invalid session identifier"
            )
        return session_id

    def stream_message(
        self,
        message: str,
        chat_session_id: str,
        *,
        parent_message_id: int | None = None,
        include_citations: bool = True,
    ) -> Iterator[dict[str, Any]]:
        """Yield bounded JSON packets from the newline-delimited chat stream."""
        if not isinstance(message, str) or not message.strip() or len(message) > 100_000:
            raise ValueError("message must contain 1 to 100000 characters")
        if not isinstance(chat_session_id, str) or not chat_session_id or len(chat_session_id) > 256:
            raise ValueError("chat_session_id must contain 1 to 256 characters")
        if parent_message_id is not None and (
            isinstance(parent_message_id, bool)
            or not isinstance(parent_message_id, int)
            or parent_message_id < 0
        ):
            raise ValueError("parent_message_id must be a non-negative integer or None")
        if not isinstance(include_citations, bool):
            raise ValueError("include_citations must be a boolean")

        payload = {
            "message": message,
            "chat_session_id": chat_session_id,
            "parent_message_id": parent_message_id,
            "origin": "api",
            "include_citations": include_citations,
        }
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/send-chat-message",
            data=body,
            headers=self._headers(json_body=True),
            method="POST",
        )
        try:
            response = self._open(request)
        except urllib.error.HTTPError as exc:
            exc.close()
            raise KnowledgeChatError(
                exc.code, "UPSTREAM_ERROR", f"request failed with status {exc.code}"
            ) from exc
        except urllib.error.URLError as exc:
            raise KnowledgeChatError(
                502, "UPSTREAM_UNAVAILABLE", "Could not reach knowledge service"
            ) from exc
        except TimeoutError as exc:
            raise KnowledgeChatError(504, "UPSTREAM_TIMEOUT", "Knowledge service request timed out") from exc

        if response.geturl() != request.full_url:
            response.close()
            raise KnowledgeChatError(502, "REDIRECT_REJECTED", "Knowledge service redirected the request")
        yield from self._iter_packets(response)

    def _iter_packets(self, response) -> Iterator[dict[str, Any]]:
        start = time.monotonic()
        consumed = 0
        try:
            while True:
                if time.monotonic() - start > self.max_stream_seconds:
                    raise KnowledgeChatError(
                        504, "UPSTREAM_STREAM_TIMEOUT", "Knowledge chat stream exceeded its time limit"
                    )
                try:
                    line = response.readline(self.MAX_PACKET_BYTES + 1)
                except TimeoutError as exc:
                    raise KnowledgeChatError(
                        504, "UPSTREAM_TIMEOUT", "Knowledge chat stream timed out"
                    ) from exc
                if not line:
                    return
                consumed += len(line)
                if consumed > self.MAX_STREAM_BYTES:
                    raise KnowledgeChatError(
                        502, "UPSTREAM_STREAM_TOO_LARGE", "Knowledge chat stream exceeded 8 MiB"
                    )
                if len(line) > self.MAX_PACKET_BYTES:
                    raise KnowledgeChatError(
                        502, "UPSTREAM_PACKET_TOO_LARGE", "Knowledge chat packet exceeded 256 KiB"
                    )
                line = line.strip()
                if (
                    not line
                    or line.startswith(b":")
                    or line.startswith(b"event:")
                    or line.startswith(b"data:")
                ):
                    continue
                try:
                    packet = json.loads(line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise KnowledgeChatError(
                        502, "INVALID_UPSTREAM_STREAM", "Knowledge service returned an invalid chat packet"
                    ) from exc
                if not isinstance(packet, dict):
                    raise KnowledgeChatError(
                        502, "INVALID_UPSTREAM_STREAM", "Knowledge chat packet must be a JSON object"
                    )
                yield packet
        finally:
            response.close()

    def _headers(self, *, json_body: bool) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._api_token}",
            "User-Agent": "zGPU-knowledge-adapter/1.0",
        }
        if json_body:
            headers["Content-Type"] = "application/json"
        return headers

    def _decode_object(self, raw: bytes) -> dict[str, Any]:
        if len(raw) > self.MAX_RESPONSE_BYTES:
            raise KnowledgeChatError(
                502, "UPSTREAM_RESPONSE_TOO_LARGE", "Knowledge service response exceeded 1 MiB"
            )
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise KnowledgeChatError(
                502, "INVALID_UPSTREAM_RESPONSE", "Knowledge service returned invalid JSON"
            ) from exc
        if not isinstance(result, dict):
            raise KnowledgeChatError(
                502, "INVALID_UPSTREAM_RESPONSE", "Knowledge service response must be a JSON object"
            )
        return result
