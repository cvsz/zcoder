"""
vLLM direct provider adapter for ZCoder.

Provides direct integration with vLLM inference engine for high-throughput
local model serving.
"""

from __future__ import annotations

import subprocess  # nosec B404  # required to run vLLM CLI without a shell
import time
from dataclasses import dataclass
from subprocess import Popen  # nosec
from typing import Any

import httpx

from zcoder.agent.ausi.adapters import (
    AdapterResult,
    BaseProviderAdapter,
    ProviderCapabilities,
    ProviderStatus,
)

# In-memory background task store for execute_background() — replaces the
# previous approach of returning a raw threading.Thread object (which was not
# serializable and could not be queried/cancelled).
_background_tasks: dict[str, dict] = {}


@dataclass
class VLLMConfig:
    """Configuration for vLLM server."""

    host: str = "127.0.0.1"
    port: int = 8000
    model: str = "meta-llama/Llama-3.1-8B-Instruct"
    tensor_parallel_size: int = 1
    gpu_memory_utilization: float = 0.9
    max_model_len: int = 8192
    dtype: str = "auto"
    trust_remote_code: bool = True
    enforce_eager: bool = False
    max_num_seqs: int = 256
    download_dir: str | None = None


class VLLMProvider(BaseProviderAdapter):
    """vLLM direct provider adapter.

    Wraps a local vLLM server for high-throughput inference.
    """

    _server_started: bool
    _client: httpx.Client | None
    _base_url: str
    _server_process: Popen | None

    def __init__(self, name: str, provider: str, config: VLLMConfig | None = None, **kwargs):
        super().__init__(name=name, provider=provider, **kwargs)
        self.config = config or VLLMConfig()
        self._server_started = False
        self._client = None
        self._base_url = f"http://{self.config.host}:{self.config.port}"
        self._server_process = None

    def start_server(self) -> bool:
        """Start the vLLM server if not already running."""
        if self._server_started:
            return True

        # Check if server is already running
        if self.health_check()["status"] == ProviderStatus.HEALTHY:
            self._server_started = True
            return True

        # Start vLLM server
        cmd = [
            "python",
            "-m",
            "vllm.entrypoints.openai.api_server",
            "--model",
            self.config.model,
            "--host",
            self.config.host,
            "--port",
            str(self.config.port),
            "--tensor-parallel-size",
            str(self.config.tensor_parallel_size),
            "--gpu-memory-utilization",
            str(self.config.gpu_memory_utilization),
            "--max-model-len",
            str(self.config.max_model_len),
            "--dtype",
            self.config.dtype,
            "--trust-remote-code" if self.config.trust_remote_code else "",
            "--enforce-eager" if self.config.enforce_eager else "",
            "--max-num-seqs",
            str(self.config.max_num_seqs),
        ]

        if self.config.download_dir:
            cmd.extend(["--download-dir", self.config.download_dir])

        # Filter empty strings
        cmd = [c for c in cmd if c]

        try:
            self._server_process = subprocess.Popen(  # nosec B603  # local vLLM server, argv list
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            # Wait for server to start
            for _ in range(30):  # Wait up to 30 seconds
                health = self.health_check()
                if health["status"] == ProviderStatus.HEALTHY:
                    self._server_started = True
                    return True

            return False
        except Exception:
            return False

    def stop_server(self) -> None:
        """Stop the vLLM server."""
        if self._server_process:
            self._server_process.terminate()
            try:
                self._server_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._server_process.kill()
                self._server_process.wait()
            self._server_process = None
            self._server_started = False

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=self._base_url,
                timeout=300.0,
            )
        return self._client

    def discover(self) -> list[dict[str, Any]]:
        """Discover available models and their capabilities."""
        try:
            self.start_server()
            client = self._get_client()
            response = client.get("/v1/models")
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])
        except Exception:
            # Fallback to config model
            return [
                {
                    "id": self.config.model,
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "vllm",
                }
            ]

    def health_check(self) -> dict[str, str]:
        """Check vLLM server health/availability."""
        try:
            client = self._get_client()
            response = client.get("/health", timeout=5.0)
            if response.status_code == 200:
                return {
                    "status": ProviderStatus.HEALTHY,
                    "details": "vLLM server responding",
                }
            else:
                return {
                    "status": ProviderStatus.DEGRADED,
                    "error": f"Health check returned {response.status_code}",
                }
        except httpx.ConnectError:
            return {
                "status": ProviderStatus.UNHEALTHY,
                "error": "Cannot connect to vLLM server",
            }
        except httpx.TimeoutException:
            return {
                "status": ProviderStatus.DEGRADED,
                "error": "Health check timeout",
            }
        except Exception as e:
            return {
                "status": ProviderStatus.UNHEALTHY,
                "error": str(e)[:200],
            }

    def list_models(self) -> list[dict[str, Any]]:
        return self.discover()

    def execute(self, prompt: str, model: str | None = None, **options) -> AdapterResult:
        """Execute a task on the provider.

        Args:
            prompt: The prompt/task to execute
            model: Model identifier (optional, may use default)
            **options: Provider-specific options (temperature, max_tokens, etc.)

        Returns:
            AdapterResult with success flag and response text
        """
        model = model or self.config.model

        self.start_server()
        client = self._get_client()

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": options.get("max_tokens", 4096),
            "temperature": options.get("temperature", 0.7),
            "top_p": options.get("top_p", 1.0),
            "stream": False,
        }

        try:
            response = client.post(
                "/v1/chat/completions",
                json=payload,
                timeout=300.0,
            )
            response.raise_for_status()
            data = response.json()

            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            return AdapterResult(
                success=True,
                text=content,
                model=model,
                provider=self.provider,
                raw=data,
            )
        except httpx.HTTPStatusError as e:
            return AdapterResult(
                success=False,
                text="",
                model=model,
                provider=self.provider,
                error=f"HTTP {e.response.status_code}: {e.response.text[:200]}",
            )
        except Exception as e:
            return AdapterResult(
                success=False,
                text="",
                model=model,
                provider=self.provider,
                error=str(e)[:200],
            )

    def execute_background(
        self, prompt: str, model: str | None = None, **options
    ) -> tuple[str, dict[str, Any]]:
        """Execute a task asynchronously.

        Returns:
            Tuple of (task_id, metadata) where metadata may contain
            initial status, estimated completion, etc.
        """
        import threading
        import uuid

        task_id = f"vllm-{uuid.uuid4().hex[:12]}"
        _background_tasks[task_id] = {
            "status": "running",
            "result": None,
            "error": None,
            "model": model or self.config.model,
            "provider": self.provider,
            "start_time": time.time(),
        }

        def _run():
            try:
                result = self.execute(prompt, model, **options)
                _background_tasks[task_id]["status"] = "completed"
                _background_tasks[task_id]["result"] = result
            except Exception as exc:  # noqa: BLE001
                _background_tasks[task_id]["status"] = "failed"
                _background_tasks[task_id]["error"] = str(exc)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

        return (
            task_id,
            {
                "task_id": task_id,
                "model": model or self.config.model,
                "provider": self.provider,
                "start_time": time.time(),
            },
        )

    def get_task_status(self, task_id: str) -> AdapterResult:
        """Check status of a background task.

        Args:
            task_id: The task identifier from execute_background()

        Returns:
            AdapterResult with current status and optionally partial results
        """
        task = _background_tasks.get(task_id)
        if not task:
            return AdapterResult(
                success=False,
                text="",
                model="",
                provider=self.provider,
                error="task not found",
            )

        if task["status"] == "completed":
            result = task["result"]
            text = result.text if result else ""
            return AdapterResult(
                success=result.success if result else False,
                text=text,
                model=task["model"],
                provider=self.provider,
                error=result.error if result and not result.success else None,
            )
        if task["status"] == "failed":
            return AdapterResult(
                success=False,
                text="",
                model=task["model"],
                provider=self.provider,
                error=task["error"] or "task failed",
            )
        # still running
        return AdapterResult(
            success=True,
            text="",
            model=task["model"],
            provider=self.provider,
            error=None,
        )

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a background task.

        Args:
            task_id: The task identifier from execute_background()

        Returns:
            True if cancellation was requested, False if task not found
            or already finished.
        """
        task = _background_tasks.get(task_id)
        if not task:
            return False
        if task["status"] == "running":
            task["status"] = "cancelled"
            return True
        return False

    def get_capabilities(self) -> ProviderCapabilities:
        caps = super().get_capabilities()
        caps.supports_discover = True
        caps.supports_health_check = True
        caps.supports_list_models = True
        caps.supports_execute = True
        caps.supports_execute_background = True
        caps.supports_get_task_status = True
        caps.supports_cancel_task = True
        caps.supports_get_capabilities = True
        return caps


class VLLMOfflineAdapter(BaseProviderAdapter):
    """vLLM offline adapter for local-only inference without server.

    Uses vLLM's Python API directly for inference without HTTP server.
    """

    def __init__(self, model: str, **kwargs):
        super().__init__(name="vllm-offline", provider="vllm-offline")
        self.model_name = model
        self._llm = None
        self._sampling_params = None
        self.capabilities = ProviderCapabilities(
            supports_discover=True,
            supports_health_check=True,
            supports_list_models=True,
            supports_execute=True,
            supports_execute_background=False,
            supports_get_task_status=False,
            supports_cancel_task=False,
            supports_get_capabilities=True,
        )

    def _get_default_model(self) -> str:
        return self.model_name

    def _load_model(self):
        pass
