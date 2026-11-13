"""
vLLM direct provider adapter for ZCoder.

Provides direct integration with vLLM inference engine for high-throughput
local model serving.
"""

from __future__ import annotations

import asyncio
import json
import subprocess  # nosec B404  # required to run vLLM CLI without a shell
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx

from zcoder.agent.ausi.adapters import (
    AdapterResult,
    BaseProviderAdapter,
    ProviderCapabilities,
    ProviderStatus,
)


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

    def __init__(self, config: VLLMConfig | None = None, **kwargs):
        super().__init__(name="vllm", provider="vllm")
        self.config = config or VLLMConfig()
        self._server_process: subprocess.Popen | None = None
        self._client: httpx.AsyncClient | None = None
        self._base_url = f"http://{self.config.host}:{self.config.port}"
        self.capabilities = ProviderCapabilities(
            supports_discover=True,
            supports_health_check=True,
            supports_list_models=True,
            supports_execute=True,
            supports_execute_background=True,
            supports_get_task_status=True,
            supports_cancel_task=True,
            supports_get_capabilities=True,
        )
        self._server_started = False

    def _get_default_model(self) -> str:
        return self.config.model

    async def start_server(self) -> bool:
        """Start the vLLM server if not already running."""
        if self._server_started:
            return True

        # Check if server is already running
        if await self.health_check()["status"] == ProviderStatus.HEALTHY:
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
                await asyncio.sleep(1)
                health = await self.health_check()
                if health["status"] == ProviderStatus.HEALTHY:
                    self._server_started = True
                    return True

            return False
        except Exception:
            return False

    async def stop_server(self) -> None:
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

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=300.0,
            )
        return self._client

    async def discover(self) -> list[dict[str, Any]]:
        """Discover available models."""
        try:
            await self.start_server()
            client = await self._get_client()
            response = await client.get("/v1/models")
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

    async def health_check(self) -> dict[str, str]:
        """Check vLLM server health."""
        try:
            client = await self._get_client()
            response = await client.get("/health", timeout=5.0)
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

    async def list_models(self) -> list[dict[str, Any]]:
        return await self.discover()

    async def execute(self, prompt: str, model: str | None = None, **options) -> AdapterResult:
        """Execute a prompt via vLLM."""
        model = model or self.config.model

        await self.start_server()
        client = await self._get_client()

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": options.get("max_tokens", 4096),
            "temperature": options.get("temperature", 0.7),
            "top_p": options.get("top_p", 1.0),
            "stream": False,
        }

        try:
            client = await self._get_client()
            response = await client.post(
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

    async def execute_stream(self, prompt: str, model: str | None = None, **options) -> AsyncIterator[str]:
        """Execute a prompt via vLLM with streaming."""
        model = model or self.config.model

        await self.start_server()
        client = await self._get_client()

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": options.get("max_tokens", 4096),
            "temperature": options.get("temperature", 0.7),
            "top_p": options.get("top_p", 1.0),
            "stream": True,
        }

        try:
            client = await self._get_client()
            async with client.stream(
                "POST",
                "/v1/chat/completions",
                json=payload,
                timeout=300.0,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue
        except Exception:
            # Yield error
            yield f"[ERROR: {str(Exception)[:200]}]"

    async def execute_background(
        self, prompt: str, model: str | None = None, **options
    ) -> tuple[str, dict[str, Any]]:
        """Execute a prompt asynchronously."""

        async def _run():
            result = await self.execute(prompt, model, **options)
            return result

        task = asyncio.create_task(_run())

        return (
            f"vllm-{id(task)}",
            {
                "task": task,
                "model": model or self.config.model,
                "provider": self.provider,
                "start_time": time.time(),
            },
        )

    async def get_task_status(self, task_id: str) -> AdapterResult:
        """Check background task status."""
        # Extract task from task_id if possible
        # This is a simplified implementation
        return AdapterResult(
            success=True,
            text="",
            model="",
            provider=self.provider,
            task_id=task_id,
        )

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a background task."""
        return False

    def get_capabilities(self) -> ProviderCapabilities:
        caps = super().get_capabilities()
        caps.supports_streaming = True
        caps.supports_function_calling = True
        caps.supports_structured_output = True
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
        if self._llm is None:
            try:
                from vllm import LLM, SamplingParams

                self._llm = LLM(model=self.model_name)
                self._sampling_params = SamplingParams(
                    temperature=0.7,
                    top_p=1.0,
                    max_tokens=4096,
                )
            except ImportError as e:
                raise RuntimeError("vLLM not installed. Install with: pip install vllm") from e

    async def discover(self) -> list[dict[str, Any]]:
        return [
            {
                "id": self.model_name,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "vllm-offline",
            }
        ]

    async def health_check(self) -> dict[str, str]:
        try:
            self._load_model()
            return {
                "status": ProviderStatus.HEALTHY,
                "details": "vLLM model loaded",
            }
        except Exception as e:
            return {
                "status": ProviderStatus.UNHEALTHY,
                "error": str(e)[:200],
            }

    async def list_models(self) -> list[dict[str, Any]]:
        return await self.discover()

    async def execute(self, prompt: str, model: str | None = None, **options) -> AdapterResult:
        self._load_model()

        from vllm import SamplingParams

        sampling_params = SamplingParams(
            temperature=options.get("temperature", 0.7),
            top_p=options.get("top_p", 1.0),
            max_tokens=options.get("max_tokens", 4096),
        )

        try:
            outputs = self._llm.generate([prompt], sampling_params)
            text = outputs[0].outputs[0].text if outputs else ""

            return AdapterResult(
                success=True,
                text=text,
                model=self.model_name,
                provider=self.provider,
            )
        except Exception as e:
            return AdapterResult(
                success=False,
                text="",
                model=self.model_name,
                provider=self.provider,
                error=str(e)[:200],
            )

    def get_capabilities(self) -> ProviderCapabilities:
        caps = super().get_capabilities()
        caps.supports_streaming = True
        return caps
