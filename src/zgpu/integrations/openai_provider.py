"""Optional, server-side OpenAI-compatible model provider adapter."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit


class OpenAIProviderError(RuntimeError):
    """A sanitized transport or protocol error from a configured model provider."""

    def __init__(self, message: str):
        super().__init__(f"zGPU model provider: {message}")


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class OpenAICompatibleProvider:
    """Connect to one explicitly configured OpenAI-compatible service."""

    MAX_RESPONSE_BYTES = 8_388_608
    MAX_STREAM_SECONDS = 180.0
    MAX_PACKET_BYTES = 262_144

    def __init__(self, base_url: str, api_key: str, *, timeout: float = 30.0):
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
        ):
            raise ValueError("base_url must be an HTTP(S) API URL without credentials, query, or fragment")
        if len(parsed.path) > 128 or ".." in parsed.path.split("/"):
            raise ValueError("base_url API path is invalid")
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError("base_url must contain a valid port") from exc
        if port == 0:
            raise ValueError("base_url port must be between 1 and 65535")
        if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("HTTP is allowed only for a loopback model provider")
        if not isinstance(api_key, str) or not api_key.strip() or len(api_key) > 8192:
            raise ValueError("api_key must contain 1 to 8192 characters")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0.1 <= timeout <= 60:
            raise ValueError("timeout must be between 0.1 and 60 seconds")

        host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
        origin = f"{parsed.scheme}://{host}{f':{port}' if port is not None else ''}"
        prefix = parsed.path.rstrip("/")
        self.base_url = f"{origin}{prefix}"
        self._api_key = api_key.strip()
        self.timeout = float(timeout)
        self._models: dict[str, str] = {}
        self._opener = urllib.request.build_opener(_RejectRedirects())

    def list_models(self) -> list[dict[str, Any]]:
        payload = self._request_json("GET", "/models")
        models = payload.get("data")
        if not isinstance(models, list) or len(models) > 1000:
            raise OpenAIProviderError("provider returned an invalid model list")
        aliases: dict[str, str] = {}
        result = []
        for entry in models:
            if not isinstance(entry, dict):
                raise OpenAIProviderError("provider returned an invalid model entry")
            upstream_id = entry.get("id")
            if not isinstance(upstream_id, str) or not upstream_id or len(upstream_id) > 512:
                raise OpenAIProviderError("provider returned an invalid model identifier")
            try:
                encoded_id = upstream_id.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise OpenAIProviderError("provider returned an invalid model identifier") from exc
            alias = f"zgpu-remote-{hashlib.sha256(encoded_id).hexdigest()[:16]}"
            if alias in aliases:
                raise OpenAIProviderError("provider returned duplicate model identifiers")
            aliases[alias] = upstream_id
            result.append({"id": alias, "object": "model", "created": 0, "owned_by": "zgpu"})
        self._models = aliases
        return result

    def create_completion(
        self,
        payload: dict[str, Any],
        event_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any] | None:
        alias = payload.get("model")
        upstream_id = self._models.get(alias) if isinstance(alias, str) else None
        if upstream_id is None:
            self.list_models()
            upstream_id = self._models.get(alias) if isinstance(alias, str) else None
        if upstream_id is None:
            raise OpenAIProviderError("the selected model is no longer available")

        upstream_payload = dict(payload)
        upstream_payload["model"] = upstream_id
        try:
            raw_payload = json.dumps(upstream_payload, separators=(",", ":"), allow_nan=False).encode("utf-8")
        except (TypeError, ValueError, UnicodeEncodeError) as exc:
            raise OpenAIProviderError("request must contain valid finite JSON values") from exc
        if len(raw_payload) > 1_048_576:
            raise OpenAIProviderError("request exceeded 1 MiB")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=raw_payload,
            headers=self._headers(stream=payload.get("stream") is True),
            method="POST",
        )
        try:
            response = self._opener.open(request, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            exc.close()
            raise OpenAIProviderError(f"provider rejected the request with HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise OpenAIProviderError("could not reach the configured provider") from exc

        if response.geturl() != request.full_url:
            response.close()
            raise OpenAIProviderError("provider redirected the request")
        if payload.get("stream") is True:
            if event_callback is None:
                response.close()
                raise OpenAIProviderError("streaming requires an event callback")
            self._stream(response, alias, event_callback)
            return None

        try:
            raw = self._read_bounded(
                response, self.MAX_RESPONSE_BYTES, time.monotonic() + self.MAX_STREAM_SECONDS
            )
        finally:
            response.close()
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OpenAIProviderError("provider returned invalid JSON") from exc
        if not isinstance(result, dict) or not isinstance(result.get("choices"), list):
            raise OpenAIProviderError("provider returned an invalid completion")
        result["model"] = alias
        return result

    def _request_json(self, method: str, path: str) -> dict[str, Any]:
        request = urllib.request.Request(f"{self.base_url}{path}", headers=self._headers(), method=method)
        try:
            response = self._opener.open(request, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            exc.close()
            raise OpenAIProviderError(f"provider rejected model discovery with HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise OpenAIProviderError("could not reach the configured provider") from exc
        if response.geturl() != request.full_url:
            response.close()
            raise OpenAIProviderError("provider redirected model discovery")
        try:
            raw = self._read_bounded(response, 1_048_576, time.monotonic() + self.timeout)
        finally:
            response.close()
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OpenAIProviderError("provider returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise OpenAIProviderError("provider returned an invalid response")
        return payload

    def _stream(self, response, alias: str, event_callback: Callable[[dict[str, Any]], None]) -> None:
        deadline = time.monotonic() + self.MAX_STREAM_SECONDS
        consumed = 0
        completed = False
        try:
            while time.monotonic() < deadline:
                line = response.readline(self.MAX_PACKET_BYTES + 1)
                if not line:
                    break
                consumed += len(line)
                if len(line) > self.MAX_PACKET_BYTES or consumed > self.MAX_RESPONSE_BYTES:
                    raise OpenAIProviderError("provider stream exceeded its size limit")
                line = line.strip()
                if not line or not line.startswith(b"data:"):
                    continue
                data = line[5:].strip()
                if data == b"[DONE]":
                    completed = True
                    break
                try:
                    event = json.loads(data.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise OpenAIProviderError("provider returned an invalid stream event") from exc
                if not isinstance(event, dict):
                    raise OpenAIProviderError("provider returned an invalid stream event")
                event["model"] = alias
                event_callback(event)
            if not completed:
                raise OpenAIProviderError("provider stream ended without a completion marker")
        except TimeoutError as exc:
            raise OpenAIProviderError("provider stream timed out") from exc
        finally:
            response.close()

    @staticmethod
    def _read_bounded(response, max_bytes: int, deadline: float) -> bytes:
        chunks = []
        size = 0
        while size <= max_bytes:
            if time.monotonic() >= deadline:
                raise OpenAIProviderError("provider response timed out")
            chunk = response.read(min(65_536, max_bytes + 1 - size))
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
            size += len(chunk)
        raise OpenAIProviderError("provider response exceeded its size limit")

    def _headers(self, *, stream: bool = False) -> dict[str, str]:
        return {
            "Accept": "text/event-stream" if stream else "application/json",
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "User-Agent": "zGPU-openai-provider/1.0",
        }


class ProviderPool:
    """Expose several optional model providers through one model namespace."""

    def __init__(self, providers: list[Any]):
        self.providers = [provider for provider in providers if provider is not None]
        self._routes: dict[str, Any] = {}

    def list_models(self) -> list[dict[str, Any]]:
        routes: dict[str, Any] = {}
        models = []
        for provider in self.providers:
            for model in provider.list_models():
                model_id = model.get("id") if isinstance(model, dict) else None
                if not isinstance(model_id, str) or not model_id or model_id in routes:
                    raise OpenAIProviderError(
                        "configured providers returned invalid or duplicate model identifiers"
                    )
                routes[model_id] = provider
                models.append(model)
        self._routes = routes
        return models

    def create_completion(
        self,
        payload: dict[str, Any],
        event_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any] | None:
        alias = payload.get("model")
        provider = self._routes.get(alias) if isinstance(alias, str) else None
        if provider is None:
            self.list_models()
            provider = self._routes.get(alias) if isinstance(alias, str) else None
        if provider is None:
            raise OpenAIProviderError("the selected model is no longer available")
        return provider.create_completion(payload, event_callback=event_callback)
