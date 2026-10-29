"""Automated Local Network Discovery for GPU & CPU Compute Nodes.

Discovers active compute nodes across local subnets using UDP broadcast beaconing
and concurrent TCP/HTTP port probing (ports 8880 [zGPU/LLM], 9000 [Dashboard], 9200 [CPU Worker]).
"""

from __future__ import annotations

import ipaddress
import json
import logging
import socket
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

logging.basicConfig(level=logging.INFO, format="%(asctime)s [ClusterDiscovery] %(message)s")
log = logging.getLogger("zGPU-ClusterDiscovery")

DEFAULT_BEACON_PORT = 9998
DEFAULT_PROBE_PORTS = [8880, 9200, 9000]


@dataclass
class DiscoveredNode:
    ip: str
    port: int
    node_type: str  # "zgpu" or "network_cpu" or "cluster_node"
    status: str
    latency_ms: float
    capabilities: dict[str, Any]

    @property
    def url(self) -> str:
        return f"http://{self.ip}:{self.port}"


class ClusterBeaconBroadcaster:
    """UDP Broadcast beacon announcer advertising this machine's GPU/CPU compute capability."""

    def __init__(
        self, port: int = DEFAULT_BEACON_PORT, service_port: int = 9200, node_type: str = "network_cpu"
    ):
        self.port = port
        self.service_port = service_port
        self.node_type = node_type
        self.running = False
        self._thread: threading.Thread | None = None

    def start(self, interval_seconds: float = 3.0):
        self.running = True
        self._thread = threading.Thread(target=self._broadcast_loop, args=(interval_seconds,), daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=1.0)

    def _broadcast_loop(self, interval: float):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(0.5)

        beacon_payload = json.dumps(
            {
                "magic": "ZGPU_NODE_BEACON",
                "node_type": self.node_type,
                "service_port": self.service_port,
                "version": "1.0",
            }
        ).encode("utf-8")

        while self.running:
            try:
                sock.sendto(beacon_payload, ("<broadcast>", self.port))
            except Exception as e:
                log.debug("Beacon broadcast error: %s", e)
            time.sleep(interval)

        sock.close()


class NetworkComputeScanner:
    """Scans and probes subnets and UDP beacons for network GPU & CPU acceleration nodes."""

    def __init__(self, probe_ports: list[int] | None = None, timeout: float = 0.8):
        ports = DEFAULT_PROBE_PORTS if probe_ports is None else probe_ports
        if (
            not ports
            or len(ports) > 16
            or any(
                isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535
                for port in ports
            )
        ):
            raise ValueError("probe_ports must contain 1 to 16 valid TCP ports")
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not 0.05 <= timeout <= 10:
            raise ValueError("timeout must be between 0.05 and 10 seconds")
        self.probe_ports = list(dict.fromkeys(ports))
        self.timeout = float(timeout)
        self.max_response_bytes = 65_536

    @staticmethod
    def _is_local_address(value: str) -> bool:
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            return False
        return address.is_private or address.is_loopback or address.is_link_local

    def _read_response(self, response) -> bytes:
        response_url = response.geturl()
        if isinstance(response_url, str):
            parsed = urlsplit(response_url)
            if parsed.scheme != "http" or not self._is_local_address(parsed.hostname or ""):
                raise ValueError("discovery redirect left the local network")
        raw = response.read(self.max_response_bytes + 1)
        if len(raw) > self.max_response_bytes:
            raise ValueError("discovery response exceeds 64 KiB")
        return raw

    def probe_node(self, ip: str, port: int) -> DiscoveredNode | None:
        """Probes an IP:Port for active zGPU or CPU worker JSON-RPC endpoints."""
        if (
            not self._is_local_address(ip)
            or isinstance(port, bool)
            or not isinstance(port, int)
            or not 1 <= port <= 65535
        ):
            return None
        url = f"http://{ip}:{port}"
        t0 = time.perf_counter()

        # Try health/status endpoints
        for endpoint in ("/health", "/status", "/api/telemetry"):
            try:
                req = urllib.request.Request(f"{url}{endpoint}", headers={"User-Agent": "zGPU-Scanner/1.0"})
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # nosec B310
                    latency = (time.perf_counter() - t0) * 1000.0
                    raw = self._read_response(resp).decode("utf-8")
                    data = json.loads(raw)
                    if not isinstance(data, dict):
                        continue
                    node_type = "network_cpu" if port == 9200 else "zgpu"
                    return DiscoveredNode(
                        ip=ip,
                        port=port,
                        node_type=node_type,
                        status="ready",
                        latency_ms=round(latency, 2),
                        capabilities=data,
                    )
            except Exception:
                continue

        # Try JSON-RPC system.health or worker.ping
        for method, node_type in [("worker.ping", "network_cpu"), ("system.health", "zgpu")]:
            try:
                t0 = time.perf_counter()
                payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": {}}).encode(
                    "utf-8"
                )
                req = urllib.request.Request(
                    f"{url}/rpc", data=payload, headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # nosec B310
                    latency = (time.perf_counter() - t0) * 1000.0
                    raw = self._read_response(resp).decode("utf-8")
                    data = json.loads(raw)
                    if not isinstance(data, dict):
                        continue
                    if "result" in data:
                        return DiscoveredNode(
                            ip=ip,
                            port=port,
                            node_type=node_type,
                            status="ready",
                            latency_ms=round(latency, 2),
                            capabilities=data.get("result", {}),
                        )
            except Exception:
                continue

        return None

    def scan_subnet(
        self, base_ip_prefix: str = "127.0.0", start_host: int = 1, end_host: int = 2
    ) -> list[DiscoveredNode]:
        """Concurrent multi-threaded subnet scan."""
        discovered: list[DiscoveredNode] = []
        if not isinstance(base_ip_prefix, str) or base_ip_prefix.count(".") != 2:
            raise ValueError("base_ip_prefix must contain exactly three IPv4 octets")
        try:
            prefix = [int(part) for part in base_ip_prefix.split(".")]
        except ValueError as exc:
            raise ValueError("base_ip_prefix must contain valid IPv4 octets") from exc
        if any(octet < 0 or octet > 255 for octet in prefix):
            raise ValueError("base_ip_prefix contains an invalid IPv4 octet")
        if (
            isinstance(start_host, bool)
            or isinstance(end_host, bool)
            or not isinstance(start_host, int)
            or not isinstance(end_host, int)
            or not 1 <= start_host <= end_host <= 254
            or end_host - start_host + 1 > 254
        ):
            raise ValueError("host range must be between 1 and 254 with at most 254 hosts")
        if not self._is_local_address(f"{base_ip_prefix}.1"):
            raise ValueError("subnet scans are restricted to private, loopback, or link-local IPv4 ranges")

        def check_host(ip: str):
            for port in self.probe_ports:
                node = self.probe_node(ip, port)
                if node:
                    discovered.append(node)

        with ThreadPoolExecutor(max_workers=min(32, end_host - start_host + 1)) as executor:
            list(
                executor.map(
                    check_host, (f"{base_ip_prefix}.{host}" for host in range(start_host, end_host + 1))
                )
            )

        return discovered

    def listen_beacons(
        self, duration_seconds: float = 2.0, port: int = DEFAULT_BEACON_PORT
    ) -> list[DiscoveredNode]:
        """Listens for UDP broadcast beacons sent by local compute workers."""
        discovered = []
        seen = set()

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("", port))  # nosec B104 - UDP beacon listener must bind to all interfaces for network discovery
        except Exception as e:
            log.debug("Could not bind UDP beacon listener: %s", e)
            return []

        sock.settimeout(0.5)
        t_end = time.time() + duration_seconds

        while time.time() < t_end:
            try:
                data, (sender_ip, _) = sock.recvfrom(2048)
                payload = json.loads(data.decode("utf-8"))
                if payload.get("magic") == "ZGPU_NODE_BEACON":
                    service_port = payload.get("service_port", 9200)
                    key = (sender_ip, service_port)
                    if key not in seen:
                        seen.add(key)
                        node = self.probe_node(sender_ip, service_port)
                        if node:
                            discovered.append(node)
            except TimeoutError:
                continue
            except Exception:
                break

        sock.close()
        return discovered
