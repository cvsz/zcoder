"""Optional, loopback-only llama.cpp server integration for local GGUF models."""

from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class LlamaCppError(RuntimeError):
    """The optional local model runtime failed or returned invalid data."""


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True)
class LlamaCppConfig:
    executable: Path
    model_path: Path
    alias: str = "zgpu-local-gguf"
    port: int = 8031
    context_size: int = 4096
    threads: int = max(1, min(os.cpu_count() or 1, 32))
    batch_size: int = 512
    gpu_layers: int = 0
    startup_timeout: float = 120.0

    @classmethod
    def from_environment(cls) -> LlamaCppConfig | None:
        executable_value = os.environ.get("ZGPU_LLAMA_SERVER_PATH", "").strip()
        model_value = os.environ.get("ZGPU_LLAMA_MODEL_PATH", "").strip()
        if not executable_value and not model_value:
            return None
        if not executable_value or not model_value:
            raise ValueError("Both ZGPU_LLAMA_SERVER_PATH and ZGPU_LLAMA_MODEL_PATH are required")

        try:
            executable = Path(executable_value).expanduser().resolve(strict=True)
            model_path = Path(model_value).expanduser().resolve(strict=True)
        except OSError as exc:
            raise ValueError("The configured local runtime or GGUF file does not exist") from exc
        if not executable.is_file() or (os.name == "posix" and not os.access(executable, os.X_OK)):
            raise ValueError("ZGPU_LLAMA_SERVER_PATH must point to an executable file")
        if not model_path.is_file() or model_path.suffix.lower() != ".gguf":
            raise ValueError("ZGPU_LLAMA_MODEL_PATH must point to an existing GGUF file")

        alias = os.environ.get("ZGPU_LLAMA_MODEL_ALIAS", "zgpu-local-gguf").strip()
        if not alias.startswith("zgpu-") or len(alias) > 128 or any(ord(char) < 33 for char in alias):
            raise ValueError("ZGPU_LLAMA_MODEL_ALIAS must be a zGPU-prefixed model name")
        config = cls(
            executable=executable,
            model_path=model_path,
            alias=alias,
            port=_positive_int_env("ZGPU_LLAMA_PORT", 8031, 65535),
            context_size=_range_int_env("ZGPU_LLAMA_CONTEXT_SIZE", 4096, 128, 262144),
            threads=_range_int_env("ZGPU_LLAMA_THREADS", max(1, min(os.cpu_count() or 1, 32)), 1, 512),
            batch_size=_range_int_env("ZGPU_LLAMA_BATCH_SIZE", 512, 1, 8192),
            gpu_layers=_range_int_env("ZGPU_LLAMA_GPU_LAYERS", 0, 0, 1000),
            startup_timeout=_range_float_env("ZGPU_LLAMA_STARTUP_TIMEOUT", 120.0, 5.0, 900.0),
        )
        return config

    def command(self, api_key_file: str) -> list[str]:
        return [
            str(self.executable),
            "--model",
            str(self.model_path),
            "--alias",
            self.alias,
            "--host",
            "127.0.0.1",
            "--port",
            str(self.port),
            "--api-key-file",
            api_key_file,
            "--ctx-size",
            str(self.context_size),
            "--threads",
            str(self.threads),
            "--batch-size",
            str(self.batch_size),
            "--n-gpu-layers",
            str(self.gpu_layers),
        ]


class LlamaCppServer:
    """Own one llama-server process and forward bounded OpenAI-compatible requests."""

    MAX_RESPONSE_BYTES = 8_388_608
    MAX_EVENT_BYTES = 262_144

    def __init__(self, config: LlamaCppConfig):
        self.config = config
        self.api_key = secrets.token_urlsafe(32)
        self.base_url = f"http://127.0.0.1:{config.port}"
        self._process: subprocess.Popen | None = None
        self._api_key_file: str | None = None
        self._opener = urllib.request.build_opener(_RejectRedirects())

    def start(self) -> None:
        if self._process is not None:
            raise LlamaCppError("The local model runtime has already been started")
        with socket.socket() as listener:
            try:
                listener.bind(("127.0.0.1", self.config.port))
            except OSError as exc:
                raise LlamaCppError("The configured local model port is unavailable") from exc

        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        try:
            descriptor, self._api_key_file = tempfile.mkstemp(prefix="zgpu-llama-", suffix=".key")
            with os.fdopen(descriptor, "w", encoding="ascii") as key_file:
                if os.name == "posix":
                    os.fchmod(key_file.fileno(), 0o600)
                key_file.write(self.api_key + "\n")
            self._process = subprocess.Popen(
                self.config.command(self._api_key_file),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                creationflags=creationflags,
                env=_runtime_environment(),
            )
        except OSError as exc:
            self._process = None
            self._remove_api_key_file()
            raise LlamaCppError("Could not start the configured local model runtime") from exc

        deadline = time.monotonic() + self.config.startup_timeout
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                self.stop()
                raise LlamaCppError("The local model runtime exited before becoming ready")
            try:
                request = urllib.request.Request(
                    f"{self.base_url}/health", headers={"Accept": "application/json"}
                )
                with self._opener.open(request, timeout=1.0) as response:
                    payload = json.loads(response.read(65_537).decode("utf-8"))
                if isinstance(payload, dict) and payload.get("status") == "ok":
                    return
            except (OSError, TimeoutError, urllib.error.URLError, UnicodeDecodeError, json.JSONDecodeError):
                time.sleep(0.25)
        self.stop()
        raise LlamaCppError("The local model runtime did not become ready before the startup timeout")

    def stop(self) -> None:
        process = self._process
        self._process = None
        if process is None or process.poll() is not None:
            self._remove_api_key_file()
            return
        try:
            process.terminate()
            try:
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5.0)
        except ProcessLookupError:
            pass
        finally:
            self._remove_api_key_file()

    def _remove_api_key_file(self) -> None:
        path = self._api_key_file
        self._api_key_file = None
        if path:
            with suppress(FileNotFoundError):
                os.unlink(path)

    def list_models(self) -> list[dict[str, Any]]:
        return [
            {
                "id": self.config.alias,
                "object": "model",
                "created": 0,
                "owned_by": "zgpu",
                "runtime": "native-local",
            }
        ]

    def create_completion(
        self,
        payload: dict[str, Any],
        event_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any] | None:
        if self._process is None or self._process.poll() is not None:
            raise LlamaCppError("The local model runtime is unavailable")
        body_payload = dict(payload)
        body_payload["model"] = self.config.alias
        if "max_completion_tokens" in body_payload:
            body_payload.setdefault("max_tokens", body_payload["max_completion_tokens"])
            body_payload.pop("max_completion_tokens", None)
        body = json.dumps(body_payload, separators=(",", ":")).encode("utf-8")
        if len(body) > 1_048_576:
            raise LlamaCppError("The local model request exceeded 1 MiB")
        headers = {
            "Accept": "text/event-stream" if payload.get("stream") is True else "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        request = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions", data=body, headers=headers, method="POST"
        )
        deadline = time.monotonic() + 180.0
        try:
            with self._opener.open(request, timeout=180.0) as response:
                if response.geturl() != request.full_url:
                    raise LlamaCppError("The local model runtime redirected a request")
                if payload.get("stream") is True:
                    if event_callback is None:
                        raise LlamaCppError("A callback is required for streaming completions")
                    self._read_stream(response, event_callback, deadline)
                    return None
                raw = self._read_bounded(response, self.MAX_RESPONSE_BYTES, deadline)
        except urllib.error.HTTPError as exc:
            exc.close()
            raise LlamaCppError("The local model runtime rejected the completion request") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise LlamaCppError("Could not reach the local model runtime") from exc
        if len(raw) > self.MAX_RESPONSE_BYTES:
            raise LlamaCppError("The local model response exceeded 8 MiB")
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LlamaCppError("The local model runtime returned invalid JSON") from exc
        if (
            not isinstance(result, dict)
            or not isinstance(result.get("choices"), list)
            or not result["choices"]
        ):
            raise LlamaCppError("The local model runtime returned an invalid completion")
        choice = result["choices"][0]
        if not isinstance(choice, dict) or not isinstance(choice.get("message"), dict):
            raise LlamaCppError("The local model runtime returned an invalid completion choice")
        if not isinstance(choice["message"].get("content"), str):
            raise LlamaCppError("The local model runtime returned a non-text completion")
        usage = result.get("usage")
        if not isinstance(usage, dict) or any(
            isinstance(usage.get(key), bool) or not isinstance(usage.get(key), int) or usage[key] < 0
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        ):
            raise LlamaCppError("The local model runtime did not return valid token usage")
        if usage["total_tokens"] != usage["prompt_tokens"] + usage["completion_tokens"]:
            raise LlamaCppError("The local model runtime returned inconsistent token usage")
        result["model"] = self.config.alias
        return result

    def _read_stream(
        self, response: Any, callback: Callable[[dict[str, Any]], None], deadline: float
    ) -> None:
        total_bytes = 0
        complete = False
        while True:
            _set_read_timeout(response, deadline)
            line = response.readline(self.MAX_EVENT_BYTES + 1)
            if not line:
                break
            total_bytes += len(line)
            if len(line) > self.MAX_EVENT_BYTES or total_bytes > self.MAX_RESPONSE_BYTES:
                raise LlamaCppError("The local model stream exceeded its size limit")
            if not line.startswith(b"data:"):
                continue
            data = line[5:].strip()
            if data == b"[DONE]":
                complete = True
                break
            try:
                event = json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise LlamaCppError("The local model stream contained invalid JSON") from exc
            if not isinstance(event, dict):
                raise LlamaCppError("The local model stream contained an invalid event")
            callback(event)
        if not complete:
            raise LlamaCppError("The local model stream ended before its completion marker")

    @staticmethod
    def _read_bounded(response: Any, maximum: int, deadline: float) -> bytes:
        chunks = []
        total = 0
        while total <= maximum:
            _set_read_timeout(response, deadline)
            chunk = response.read(min(65_536, maximum + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        return b"".join(chunks)


def _positive_int_env(name: str, default: int, maximum: int) -> int:
    return _range_int_env(name, default, 1, maximum)


def _range_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _range_float_env(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _runtime_environment() -> dict[str, str]:
    """Pass runtime and device variables without leaking unrelated credentials."""
    allowed = {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "LD_LIBRARY_PATH",
        "DYLD_LIBRARY_PATH",
        "CUDA_VISIBLE_DEVICES",
        "HIP_VISIBLE_DEVICES",
        "ROCR_VISIBLE_DEVICES",
        "GGML_VK_VISIBLE_DEVICES",
        "OMP_NUM_THREADS",
    }
    return {key: value for key, value in os.environ.items() if key in allowed}


def _set_read_timeout(response: Any, deadline: float) -> None:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise LlamaCppError("The local model request exceeded its 180 second timeout")
    raw = getattr(getattr(response, "fp", None), "raw", None)
    sock = getattr(raw, "_sock", None)
    if sock is not None and not sock._closed:
        sock.settimeout(remaining)
