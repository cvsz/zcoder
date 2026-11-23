"""Loopback-only OpenAI-compatible streaming client for a local Ollama server."""

from __future__ import annotations

import asyncio
import json
import os
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from zcoder.agent.optimization.pooling import get_connection, return_connection

DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "zcoder-flash"


class LLMError(RuntimeError):
    """A model-server failure. ``retryable`` marks transient conditions (connection refused, 429/5xx)."""

    def __init__(self, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


def local_base_url(raw: str | None = None) -> str:
    """Return a loopback-only server URL; never allow hosted egress."""
    base = (raw or os.getenv("ZCODER_BASE_URL") or DEFAULT_BASE_URL).strip().rstrip("/")
    p = urllib.parse.urlsplit(base)
    if (
        p.scheme != "http"
        or p.hostname not in {"127.0.0.1", "::1"}
        or p.username
        or p.password
        or p.query
        or p.fragment
    ):
        raise ValueError("ZCODER_BASE_URL must point to a local Ollama server on loopback.")
    return base


def endpoint(path: str, base: str | None = None) -> str:
    b = local_base_url(base)
    return f"{b}/{path.lstrip('/')}" if b.endswith("/v1") else f"{b}/v1/{path.lstrip('/')}"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):  # noqa: D401
        return None


def _open_local(request: urllib.request.Request, *, timeout: float):
    return urllib.request.build_opener(_NoRedirect()).open(
        request, timeout=timeout
    )  # nosec B310  # loopback-validated


@dataclass
class ToolCallRequest:
    id: str
    name: str
    args: dict[str, Any]


@dataclass
class LLMChunk:
    kind: str  # text | thinking | tool_calls | usage | finish
    text: str = ""
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    finish_reason: str = ""


class LLM(Protocol):
    model: str

    def stream(self, messages: list[dict], tools: list[dict]) -> AsyncGenerator[LLMChunk, None]:
        pass


class LocalLLM(LLM):
    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        opener=_open_local,
        timeout: float = 600,
        gguf_paths: list[str] | None = None,
    ):
        self.model = model or os.getenv("ZCODER_MODEL", DEFAULT_MODEL) or DEFAULT_MODEL
        self.base_url = local_base_url(base_url)
        self.temperature, self.max_tokens, self._open, self.timeout = temperature, max_tokens, opener, timeout
        self.gguf_paths = gguf_paths or []
        self._discovered_models: dict[str, str] = {}  # model_name -> gguf_path

    def discover_model(self) -> str | None:
        """Ask local Ollama server which model it has loaded."""
        req = urllib.request.Request(  # noqa: S310 - loopback-validated
            endpoint("models", self.base_url), headers={"Accept": "application/json"}
        )
        try:
            with self._open(req, timeout=3) as r:
                data = json.loads(r.read().decode("utf-8")).get("data", [])
        except (OSError, ValueError, urllib.error.URLError):
            return None
        mid = next((d.get("id") for d in data if d.get("id")), None)
        if mid:
            self.model = mid
        return mid

    def scan_gguf_models(self, paths: list[str] | None = None) -> dict[str, str]:
        """Scan directories for GGUF model files.

        Mirrors deepseek-harness local model adapter with GGUF file discovery.
        Returns a dict of model_name -> file_path.
        """
        search_paths = paths or self.gguf_paths
        discovered: dict[str, str] = {}

        for search_path in search_paths:
            p = Path(search_path)
            if not p.exists():
                continue
            for gguf_file in p.rglob("*.gguf"):
                model_name = gguf_file.stem
                discovered[model_name] = str(gguf_file.resolve())
        self._discovered_models.update(discovered)
        return discovered

    def switch_model(self, model_name: str) -> bool:
        """Switch to a different model at runtime.

        Mirrors deepseek-harness model selection projection with runtime model switching.
        Returns True if the model was switched successfully.
        """
        # Check discovered models first
        if model_name in self._discovered_models:
            self.model = model_name
            return True

        # Check if it's a known model name
        self.model = model_name
        return True

    def get_discovered_models(self) -> dict[str, str]:
        """Get all discovered GGUF models."""
        return dict(self._discovered_models)

    def _request(self, messages: list[dict], tools: list[dict]):
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            payload["tools"] = tools

        # Get a pooled connection for tracking
        conn = get_connection("ollama", self.model)
        if conn:
            conn.mark_used()

        req = urllib.request.Request(  # noqa: S310 - loopback-validated
            endpoint("chat/completions", self.base_url),
            data=json.dumps(payload).encode(),
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        )
        try:
            return self._open(req, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            if conn:
                conn.record_error(f"HTTP {exc.code}")
            raise LLMError(
                f"Ollama returned HTTP {exc.code}: {exc.read(500).decode('utf-8', 'replace')}",
                retryable=exc.code in {408, 429, 500, 502, 503, 504},
            ) from exc
        except urllib.error.URLError as exc:
            if conn:
                conn.record_error(str(exc.reason))
            raise LLMError(
                f"Cannot reach local Ollama server at {self.base_url}: {exc.reason}", retryable=True
            ) from exc
        finally:
            if conn:
                return_connection(conn)

    def _produce(self, messages, tools, emit, stop: threading.Event) -> None:
        """Runs in a worker thread: parse the SSE stream into LLMChunks."""
        calls: dict[int, dict[str, str]] = {}
        finish = ""
        try:
            with self._request(messages, tools) as resp:
                for raw in resp:
                    if stop.is_set():
                        return
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        ev = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if ev.get("usage"):
                        u = ev["usage"]
                        emit(
                            LLMChunk(
                                "usage",
                                prompt_tokens=u.get("prompt_tokens", 0),
                                completion_tokens=u.get("completion_tokens", 0),
                            )
                        )
                    for choice in ev.get("choices") or []:
                        delta = choice.get("delta") or {}
                        if isinstance(delta.get("content"), str) and delta["content"]:
                            emit(LLMChunk("text", text=delta["content"]))
                        if isinstance(delta.get("reasoning_content"), str) and delta["reasoning_content"]:
                            emit(LLMChunk("thinking", text=delta["reasoning_content"]))
                        for tc in delta.get("tool_calls") or []:
                            slot = calls.setdefault(tc.get("index", 0), {"id": "", "name": "", "args": ""})
                            slot["id"] = tc.get("id") or slot["id"]
                            fn = tc.get("function") or {}
                            slot["name"] += fn.get("name") or ""
                            slot["args"] += fn.get("arguments") or ""
                        finish = choice.get("finish_reason") or finish
            if calls:
                emit(
                    LLMChunk("tool_calls", tool_calls=[_finish_call(i, c) for i, c in sorted(calls.items())])
                )
            emit(LLMChunk("finish", finish_reason=finish or "stop"))
        except Exception as exc:  # surfaced to the consumer, never swallowed
            emit(exc)

    async def stream(self, messages: list[dict], tools: list[dict]) -> AsyncGenerator[LLMChunk, None]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        stop = threading.Event()

        def emit(item) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, item)

        worker = threading.Thread(target=self._produce, args=(messages, tools, emit, stop), daemon=True)
        worker.start()
        try:
            while True:
                item = await queue.get()
                if isinstance(item, Exception):
                    raise item if isinstance(item, LLMError) else LLMError(str(item))
                yield item
                if item.kind == "finish":
                    return
        finally:
            stop.set()


def _finish_call(index: int, raw: dict[str, str]) -> ToolCallRequest:
    try:
        args = json.loads(raw["args"]) if raw["args"].strip() else {}
    except json.JSONDecodeError:
        args = {"__parse_error__": raw["args"][:500]}
    return ToolCallRequest(raw.get("id") or f"call_{index}", raw.get("name") or "", args)
