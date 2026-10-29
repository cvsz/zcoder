"""Network CPU Worker Node for zGPU Distributed Computing Grid.

Listens on HTTP/JSON-RPC for partitioned matrix multiplication chunks, token projections,
and vector embeddings dispatched from the primary zGPU host, returning computed float tensors.
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import logging
import math
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from zgpu.runtime.network_policy import validate_worker_token

logging.basicConfig(level=logging.INFO, format="%(asctime)s [CPU-Worker] %(message)s")
log = logging.getLogger("zGPU-CPU-Worker")


class CPUComputeEngine:
    """Multi-threaded / vectorized CPU compute kernels."""

    MAX_OUTPUT_ELEMENTS = 262_144
    MAX_MULTIPLY_OPERATIONS = 1_000_000
    MAX_ABS_VALUE = 1e12

    @classmethod
    def _matrix(cls, value: Any, name: str) -> list[list[float]]:
        if (
            not isinstance(value, list)
            or not value
            or any(not isinstance(row, list) or not row for row in value)
        ):
            raise ValueError(f"{name} must be a non-empty rectangular matrix")
        width = len(value[0])
        if len(value) * width > cls.MAX_OUTPUT_ELEMENTS or any(len(row) != width for row in value):
            raise ValueError(f"{name} has invalid dimensions or exceeds the supported element limit")

        matrix = []
        for row in value:
            converted = []
            for item in row:
                if isinstance(item, bool) or not isinstance(item, (int, float)):
                    raise ValueError(f"{name} values must be finite numbers")
                number = float(item)
                if not math.isfinite(number) or abs(number) > cls.MAX_ABS_VALUE:
                    raise ValueError(f"{name} values must be finite and within the supported range")
                converted.append(number)
            matrix.append(converted)
        return matrix

    @staticmethod
    def gemm_chunk(A: list[list[float]], B: list[list[float]]) -> list[list[float]]:
        """Compute standard matrix multiplication A @ B on CPU."""
        A = CPUComputeEngine._matrix(A, "A")
        B = CPUComputeEngine._matrix(B, "B")
        M = len(A)
        K = len(A[0])
        N = len(B[0])
        if len(B) != K:
            raise ValueError("A columns must equal B rows")
        if (
            M * N > CPUComputeEngine.MAX_OUTPUT_ELEMENTS
            or M * K * N > CPUComputeEngine.MAX_MULTIPLY_OPERATIONS
        ):
            raise ValueError("GEMM request exceeds the supported compute limit")

        # Transpose B for cache-friendly contiguous row access on CPU
        B_T = [[B[r][c] for r in range(len(B))] for c in range(N)]

        out = [[0.0 for _ in range(N)] for _ in range(M)]
        for i in range(M):
            row_a = A[i]
            for j in range(N):
                row_b = B_T[j]
                # Dot product
                dot = 0.0
                for k in range(K):
                    dot += row_a[k] * row_b[k]
                out[i][j] = dot

        return out

    @classmethod
    def vector_norm_chunk(
        cls, X: list[list[float]], weights: list[float], eps: float = 1e-5
    ) -> list[list[float]]:
        """Compute RMSNorm on CPU chunk."""
        X = cls._matrix(X, "X")
        weights = cls._matrix([weights], "weights")[0]
        if len(X[0]) != len(weights) or any(len(row) != len(weights) for row in X):
            raise ValueError("Each X row must match the weights dimension")
        if isinstance(eps, bool) or not isinstance(eps, (int, float)) or not math.isfinite(eps) or eps <= 0:
            raise ValueError("eps must be a finite positive number")
        if len(X) * len(weights) > cls.MAX_MULTIPLY_OPERATIONS:
            raise ValueError("RMSNorm request exceeds the supported compute limit")
        out = []
        dim = len(weights)
        for row in X:
            var = sum(v * v for v in row) / dim
            inv_rms = 1.0 / math.sqrt(var + eps)
            out.append([v * inv_rms * w for v, w in zip(row, weights, strict=False)])
        return out


class CPUWorkerHTTPHandler(BaseHTTPRequestHandler):
    MAX_REQUEST_BYTES = 1_048_576
    auth_token: str | None = None

    def do_GET(self):
        if self.path in ("/", "/health", "/status"):
            resp = {
                "ok": True,
                "node_type": "network_cpu_worker",
                "status": "ready",
                "cores_available": 16,
                "timestamp": time.time(),
            }
            self._send_json(resp)
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        if self.auth_token is not None:
            provided = self.headers.get("Authorization", "")
            expected = f"Bearer {self.auth_token}"
            if not hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8")):
                self._send_json(
                    {"jsonrpc": "2.0", "id": None, "error": {"code": -32001, "message": "Unauthorized"}},
                    status=401,
                )
                return
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length < 0 or length > self.MAX_REQUEST_BYTES:
                raise ValueError("Request body must be at most 1 MiB")
            body = self.rfile.read(length).decode("utf-8")
            payload = json.loads(body) if body else {}
            if not isinstance(payload, dict):
                raise ValueError("Request body must be a JSON object")
            params = payload.get("params", {})
            if not isinstance(params, dict):
                raise ValueError("params must be a JSON object")
        except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._send_json(
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}}, status=400
            )
            return

        method = payload.get("method")
        req_id = payload.get("id")

        t0 = time.perf_counter()
        try:
            if method == "compute.gemm":
                result = CPUComputeEngine.gemm_chunk(params.get("A", []), params.get("B", []))
                resp_payload = {"jsonrpc": "2.0", "id": req_id, "result": {"matrix": result}}

            elif method == "compute.rmsnorm":
                result = CPUComputeEngine.vector_norm_chunk(params.get("X", []), params.get("weights", []))
                resp_payload = {"jsonrpc": "2.0", "id": req_id, "result": {"matrix": result}}

            elif method == "worker.ping":
                resp_payload = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"status": "pong", "time": time.time()},
                }

            else:
                self._send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32601, "message": "Method not supported"},
                    },
                    status=400,
                )
                return
        except (TypeError, ValueError, OverflowError, IndexError, ZeroDivisionError) as exc:
            self._send_json(
                {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32602, "message": str(exc)}}, status=400
            )
            return

        if method in {"compute.gemm", "compute.rmsnorm"}:
            resp_payload["result"]["latency_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)
        self._send_json(resp_payload)

    def _send_json(self, data: Any, status: int = 200):
        body_bytes = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body_bytes)))
        self.end_headers()
        self.wfile.write(body_bytes)

    def log_message(self, format, *args):
        pass


def run_cpu_worker(host: str = "127.0.0.1", port: int = 9200, token: str | None = None):
    token = token if token is not None else os.environ.get("ZGPU_CPU_WORKER_TOKEN")
    try:
        is_loopback = host == "localhost" or ipaddress.ip_address(host).is_loopback
    except ValueError:
        is_loopback = False
    if not is_loopback and (not isinstance(token, str) or len(token) < 32):
        raise ValueError("non-loopback CPU workers require ZGPU_CPU_WORKER_TOKEN with at least 32 characters")
    validate_worker_token(token)

    class ConfiguredCPUWorkerHTTPHandler(CPUWorkerHTTPHandler):
        auth_token = token

    server = HTTPServer((host, port), ConfiguredCPUWorkerHTTPHandler)
    log.info("zGPU Network CPU Worker listening on http://%s:%d/", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9200
    run_cpu_worker(port=port)
