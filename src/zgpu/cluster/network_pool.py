"""Network CPU Compute Pool & Work Stealing Dispatcher for zGPU.

Aggregates multiple remote CPU compute nodes over the network.
Partitions compute workloads between local zGPU Tensor Cores and remote network CPUs
to achieve maximum aggregated throughput ("powerup" burst mode).
"""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import time
import urllib.request
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from zgpu.kernels.llm_kernels import LLMKernels
from zgpu.runtime.network_policy import validate_worker_token
from zgpu.runtime.runtime import ZRuntime

log = logging.getLogger("zGPU-ClusterPool")


class _RejectWorkerRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("worker redirects are not accepted")


@dataclass
class NetworkNode:
    node_id: str
    url: str
    active: bool = True
    latency_ms: float = 0.0
    token: str | None = field(default=None, repr=False)


class NetworkCPUPool:
    """Manages a fleet of network CPU workers to augment local zGPU compute capacity."""

    def __init__(self, runtime: ZRuntime | None = None):
        self.runtime = runtime or ZRuntime()
        self.kernels = LLMKernels(self.runtime)
        self.nodes: dict[str, NetworkNode] = {}
        self._http = urllib.request.build_opener(urllib.request.ProxyHandler({}), _RejectWorkerRedirects())

    @staticmethod
    def _validate_worker_url(url: str) -> str:
        if not isinstance(url, str) or len(url) > 256:
            raise ValueError("worker URL must be a string of at most 256 characters")
        parsed = urlsplit(url)
        if parsed.scheme != "http" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("worker URL must be an HTTP URL without embedded credentials")
        try:
            address = ipaddress.ip_address(parsed.hostname)
            port = parsed.port or 80
        except ValueError as exc:
            raise ValueError("worker URL must use a literal local IP address and valid port") from exc
        if not (address.is_private or address.is_loopback or address.is_link_local) or not 1 <= port <= 65535:
            raise ValueError("worker URL must target a private, loopback, or link-local IP address")
        if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ValueError("worker URL must identify only the service origin")
        return f"http://{parsed.netloc}"

    @staticmethod
    def _read_json_response(response, expected_url: str) -> dict:
        final_url = response.geturl()
        if final_url != expected_url:
            raise ValueError("worker redirected the request; redirects are not accepted")
        raw = response.read(1_048_577)
        if len(raw) > 1_048_576:
            raise ValueError("worker response exceeds 1 MiB")
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("worker response must be a JSON object")
        return data

    def register_node(self, node_id: str, url: str, token: str | None = None):
        """Add a network CPU worker endpoint (e.g. http://192.168.1.100:9200)."""
        if not isinstance(node_id, str) or not node_id or len(node_id) > 128:
            raise ValueError("node_id must contain 1 to 128 characters")
        normalized_url = self._validate_worker_url(url)
        validate_worker_token(token)
        address = ipaddress.ip_address(urlsplit(normalized_url).hostname)
        if not address.is_loopback and (not isinstance(token, str) or len(token) < 32):
            raise ValueError("non-loopback workers require an authentication token of at least 32 characters")
        self.nodes[node_id] = NetworkNode(node_id=node_id, url=normalized_url, token=token)

    @staticmethod
    def configured_worker_token(node_id: str, url: str) -> str | None:
        """Read an optional token keyed by worker id or URL from server environment."""
        configured = os.environ.get("ZGPU_CLUSTER_WORKER_TOKENS", "")
        if not configured:
            return None
        try:
            tokens = json.loads(configured)
        except json.JSONDecodeError as exc:
            raise ValueError("ZGPU_CLUSTER_WORKER_TOKENS must be a JSON object") from exc
        if not isinstance(tokens, dict) or any(not isinstance(key, str) for key in tokens):
            raise ValueError("ZGPU_CLUSTER_WORKER_TOKENS must be a JSON object of worker keys to tokens")
        token = tokens.get(node_id, tokens.get(url))
        validate_worker_token(token)
        return token

    def remove_node(self, node_id: str):
        self.nodes.pop(node_id, None)

    def ping_nodes(self) -> dict[str, bool]:
        """Verify reachability of all registered network CPU workers."""
        status = {}
        for nid, node in list(self.nodes.items()):
            try:
                req_data = json.dumps(
                    {"jsonrpc": "2.0", "id": 1, "method": "worker.ping", "params": {}}
                ).encode("utf-8")
                req = urllib.request.Request(node.url, data=req_data, headers=self._request_headers(node))
                t0 = time.perf_counter()
                with self._http.open(req, timeout=2.0) as resp:
                    res = self._read_json_response(resp, node.url)
                    node.latency_ms = (time.perf_counter() - t0) * 1000.0
                    node.active = "result" in res
                    status[nid] = node.active
            except Exception:
                node.active = False
                status[nid] = False
        return status

    def dispatch_remote_gemm(
        self, node_id: str, A_chunk: list[list[float]], B: list[list[float]]
    ) -> list[list[float]]:
        """Dispatch a matrix multiplication chunk to a specific network CPU worker."""
        node = self.nodes.get(node_id)
        if not node or not node.active:
            raise RuntimeError(f"Node {node_id} is inactive or unreachable")

        req_data = json.dumps(
            {"jsonrpc": "2.0", "id": 10, "method": "compute.gemm", "params": {"A": A_chunk, "B": B}}
        ).encode("utf-8")

        req = urllib.request.Request(node.url, data=req_data, headers=self._request_headers(node))
        with self._http.open(req, timeout=10.0) as resp:
            data = self._read_json_response(resp, node.url)
            return data["result"]["matrix"]

    def hybrid_gemm_powerup(
        self,
        A: list[list[float]],
        B: list[list[float]],
        gpu_fraction: float = 0.5,
    ) -> list[list[float]]:
        """Hybrid heterogeneous parallel GEMM:
        Splits rows of A between local zGPU Tensor Cores and network CPU workers,
        merging the final output matrix seamlessly.
        """
        M = len(A)
        if M == 0:
            return []

        active_network_nodes = [n for n in self.nodes.values() if n.active]

        # Fallback to pure zGPU if no network CPU workers are active
        if not active_network_nodes or gpu_fraction >= 1.0:
            return self.kernels.gemm(A, B)

        # Calculate row split
        gpu_rows = max(1, int(M * gpu_fraction))
        # Align gpu_rows to multiple of 4 for Tensor Core tile alignment
        gpu_rows = (gpu_rows // 4) * 4
        if gpu_rows == 0:
            gpu_rows = min(4, M)

        a_gpu = A[:gpu_rows]
        a_network = A[gpu_rows:]

        # 1. Compute GPU slice on local zGPU Tensor Cores
        gpu_out = self.kernels.gemm(a_gpu, B)

        if not a_network:
            return gpu_out

        # 2. Compute network slice on remote CPU worker
        target_node = active_network_nodes[0]
        try:
            cpu_out = self.dispatch_remote_gemm(target_node.node_id, a_network, B)
        except Exception as e:
            log.warning("Remote worker failed (%s). Falling back to local zGPU.", e)
            cpu_out = self.kernels.gemm(a_network, B)

        # 3. Concatenate row outputs
        return gpu_out + cpu_out

    @staticmethod
    def _request_headers(node: NetworkNode) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if node.token is not None:
            headers["Authorization"] = f"Bearer {node.token}"
        return headers

    def auto_discover_and_powerup(
        self, subnet_prefix: str = "127.0.0", start_host: int = 1, end_host: int = 2
    ) -> int:
        """Scan local subnet and automatically register all discovered GPU and CPU nodes."""
        from zgpu.cluster.discovery.scanner import NetworkComputeScanner

        scanner = NetworkComputeScanner()
        discovered = scanner.scan_subnet(
            base_ip_prefix=subnet_prefix, start_host=start_host, end_host=end_host
        )
        registered = 0
        for node in discovered:
            node_id = f"{node.node_type}_{node.ip}_{node.port}"
            token = self.configured_worker_token(node_id, node.url)
            try:
                self.register_node(node_id, node.url, token=token)
            except ValueError as exc:
                if "require an authentication token" not in str(exc):
                    raise
                log.warning(
                    "Skipping discovered worker %s because no authentication token is configured", node_id
                )
                continue
            registered += 1
        return registered
