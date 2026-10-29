"""Opt-in bounded client for OpenAI-compatible embedding endpoints."""

from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit


class EmbeddingProviderError(RuntimeError):
    """A sanitized transport or response error from the embedding service."""


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class OpenAICompatibleEmbeddingProvider:
    """Request one validated vector at a time from an explicitly configured service."""

    MAX_RESPONSE_BYTES = 1_048_576
    MAX_REQUEST_BYTES = 1_048_576
    MAX_INPUT_CHARS = 262_144
    MAX_DIMENSIONS = 4096

    def __init__(self, base_url: str, model: str, api_key: str, *, timeout: float = 30.0):
        if not isinstance(base_url, str) or len(base_url) > 512:
            raise ValueError("base_url must contain at most 512 characters")
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("base_url must be an HTTP(S) URL without credentials, query, or fragment")
        if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("HTTP is allowed only for a loopback embedding provider")
        if len(parsed.path) > 128 or ".." in parsed.path.split("/"):
            raise ValueError("base_url API path is invalid")
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError("base_url must contain a valid port") from exc
        if port == 0:
            raise ValueError("base_url port must be between 1 and 65535")
        if not isinstance(model, str) or not model.strip() or len(model) > 512:
            raise ValueError("model must contain 1 to 512 characters")
        if not isinstance(api_key, str) or not api_key.strip() or len(api_key) > 8192:
            raise ValueError("api_key must contain 1 to 8192 characters")
        if any(character in api_key for character in "\r\n\x00"):
            raise ValueError("api_key must not contain newline or NUL characters")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0.1 <= timeout <= 60:
            raise ValueError("timeout must be between 0.1 and 60 seconds")

        host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
        origin = f"{parsed.scheme}://{host}{f':{port}' if port is not None else ''}"
        self.base_url = f"{origin}{parsed.path.rstrip('/')}/embeddings"
        self.model = model.strip()
        self._api_key = api_key.strip()
        self.timeout = float(timeout)
        self._opener = urllib.request.build_opener(_RejectRedirects())

    def embed(self, text: str) -> list[float]:
        if not isinstance(text, str) or not text.strip() or len(text) > self.MAX_INPUT_CHARS:
            raise EmbeddingProviderError("embedding input must contain 1 to 262144 characters")
        try:
            body = json.dumps(
                {"model": self.model, "input": text}, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        except (TypeError, ValueError, UnicodeEncodeError) as exc:
            raise EmbeddingProviderError("embedding input must be valid Unicode text") from exc
        if len(body) > self.MAX_REQUEST_BYTES:
            raise EmbeddingProviderError("embedding request exceeded 1 MiB")

        request = urllib.request.Request(
            self.base_url,
            data=body,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "User-Agent": "zGPU-embeddings/1.0",
            },
            method="POST",
        )
        try:
            response = self._opener.open(request, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            exc.close()
            raise EmbeddingProviderError(f"embedding service returned HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise EmbeddingProviderError("could not reach the configured embedding service") from exc

        if response.geturl() != request.full_url:
            response.close()
            raise EmbeddingProviderError("embedding service redirected the request")
        chunks = []
        size = 0
        deadline = time.monotonic() + self.timeout
        try:
            while size <= self.MAX_RESPONSE_BYTES:
                if time.monotonic() >= deadline:
                    raise EmbeddingProviderError("embedding service response timed out")
                chunk = response.read(min(65_536, self.MAX_RESPONSE_BYTES + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
        except (TimeoutError, OSError) as exc:
            raise EmbeddingProviderError("embedding service response could not be read") from exc
        finally:
            response.close()
        if size > self.MAX_RESPONSE_BYTES:
            raise EmbeddingProviderError("embedding service response exceeded 1 MiB")
        raw = b"".join(chunks)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EmbeddingProviderError("embedding service returned invalid JSON") from exc
        data = payload.get("data") if isinstance(payload, dict) else None
        vector = (
            data[0].get("embedding")
            if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict)
            else None
        )
        if not isinstance(vector, list) or not 1 <= len(vector) <= self.MAX_DIMENSIONS:
            raise EmbeddingProviderError("embedding service returned an invalid vector")
        normalized = []
        try:
            for value in vector:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise EmbeddingProviderError("embedding service returned non-numeric vector values")
                numeric = float(value)
                if not math.isfinite(numeric) or abs(numeric) > 1_000_000:
                    raise EmbeddingProviderError(
                        "embedding service returned non-finite or out-of-range vector values"
                    )
                normalized.append(numeric)
        except OverflowError as exc:
            raise EmbeddingProviderError("embedding service returned out-of-range vector values") from exc
        if not any(normalized):
            raise EmbeddingProviderError("embedding service returned a zero vector")
        return normalized
