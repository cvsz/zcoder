"""zGPU Mobile & Edge Client SDK.

Provides robust, typed Python and cross-platform client bindings for interacting
with the zGPU JSON-RPC inference server, cluster nodes, and compiler service.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any


class ZGPUSDKClient:
    """Client SDK for zGPU enterprise server, LLM engine, and cluster workers."""

    def __init__(self, base_url: str = "http://localhost:8880"):
        self.base_url = base_url.rstrip("/")
        self.rpc_url = f"{self.base_url}/rpc"

    def rpc_call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a JSON-RPC request against the zGPU server."""
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": 1,
        }
        req = urllib.request.Request(
            self.rpc_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("error"):
                    raise RuntimeError(f"zGPU RPC Error: {data['error']}")
                return data.get("result", {})
        except Exception as err:
            raise RuntimeError(f"Failed to communicate with zGPU server at {self.rpc_url}: {err}") from err

    def generate(self, prompt: str, model: str = "qwen2.5-coder-1.5b", max_tokens: int = 32) -> dict[str, Any]:
        """Generate text / code using zGPU LLM engine."""
        return self.rpc_call("generate", {"prompt": prompt, "model": model, "max_tokens": max_tokens})

    def list_models(self) -> list[dict[str, Any]]:
        """List available SIMT models."""
        res = self.rpc_call("list_models", {})
        return res.get("models", [])

    def compile_ast(self, source_code: str) -> dict[str, Any]:
        """Compile Python AST code into zISA binary instructions."""
        return self.rpc_call("compile", {"source": source_code})

    def health_check(self) -> dict[str, Any]:
        """Check cluster and server health status."""
        return self.rpc_call("health", {})
