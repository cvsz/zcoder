"""Python client library for communicating with zGPU LLM Servers."""

from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any

log = logging.getLogger(__name__)


class ZGPUClient:
    """Client for querying zGPU RPC acceleration services for LLM generation."""

    def __init__(self, endpoint_url: str = "http://127.0.0.1:8880/rpc", timeout: float = 15.0):
        self.endpoint_url = endpoint_url
        self.timeout = timeout

    def health(self) -> dict[str, Any]:
        req_data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "system.health", "params": {}}).encode(
            "utf-8"
        )
        req = urllib.request.Request(
            self.endpoint_url, data=req_data, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8")).get("result", {})

    def generate(self, prompt: str, max_tokens: int = 16) -> dict[str, Any]:
        req_data = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "llm.generate",
                "params": {"prompt": prompt, "max_tokens": max_tokens},
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint_url, data=req_data, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8")).get("result", {})
