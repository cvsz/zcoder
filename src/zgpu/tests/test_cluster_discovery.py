import json
import os
from unittest.mock import MagicMock, patch

import pytest

from zgpu.cluster.discovery.scanner import (
    DiscoveredNode,
    NetworkComputeScanner,
)
from zgpu.cluster.network_pool import NetworkCPUPool


def test_discovered_node_properties():
    node = DiscoveredNode(
        ip="192.168.1.100",
        port=9200,
        node_type="network_cpu",
        status="ready",
        latency_ms=1.5,
        capabilities={"cores": 8},
    )
    assert node.url == "http://192.168.1.100:9200"


def test_scanner_probe_node_success():
    scanner = NetworkComputeScanner()
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({"ok": True, "node_type": "network_cpu"}).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        node = scanner.probe_node("127.0.0.1", 9200)
        assert node is not None
        assert node.ip == "127.0.0.1"
        assert node.port == 9200
        assert node.node_type == "network_cpu"
        assert node.status == "ready"


def test_scanner_subnet_scan():
    scanner = NetworkComputeScanner(probe_ports=[9200])

    mock_node = DiscoveredNode(
        ip="127.0.0.1",
        port=9200,
        node_type="network_cpu",
        status="ready",
        latency_ms=2.0,
        capabilities={},
    )

    with patch.object(
        scanner, "probe_node", side_effect=lambda ip, port: mock_node if ip == "127.0.0.1" else None
    ):
        results = scanner.scan_subnet(base_ip_prefix="127.0.0", start_host=1, end_host=2)
        assert len(results) == 1
        assert results[0].ip == "127.0.0.1"


def test_scanner_rejects_public_targets_and_unbounded_scans():
    scanner = NetworkComputeScanner()
    assert scanner.probe_node("8.8.8.8", 9200) is None
    try:
        scanner.scan_subnet(base_ip_prefix="8.8.8", start_host=1, end_host=2)
    except ValueError as exc:
        assert "restricted" in str(exc)
    else:
        raise AssertionError("public subnet scan should be rejected")

    try:
        scanner.scan_subnet(base_ip_prefix="127.0.0", start_host=1, end_host=255)
    except ValueError as exc:
        assert "host range" in str(exc)
    else:
        raise AssertionError("invalid host range should be rejected")


def test_scanner_rejects_invalid_configuration():
    for ports, timeout in (([], 0.8), ([70000], 0.8), ([9200], 0), ([9200], 11)):
        try:
            NetworkComputeScanner(probe_ports=ports, timeout=timeout)
        except ValueError:
            continue
        raise AssertionError("invalid scanner configuration should be rejected")


def test_scanner_rejects_public_redirects_and_oversized_responses():
    scanner = NetworkComputeScanner()
    response = MagicMock()
    response.geturl.return_value = "http://8.8.8.8/health"
    with pytest.raises(ValueError, match="redirect"):
        scanner._read_response(response)

    response.geturl.return_value = "http://127.0.0.1/health"
    response.read.return_value = b"x" * (scanner.max_response_bytes + 1)
    with pytest.raises(ValueError, match="64 KiB"):
        scanner._read_response(response)


def test_network_pool_auto_discovery():
    pool = NetworkCPUPool()
    mock_nodes = [
        DiscoveredNode("192.168.1.10", 9200, "network_cpu", "ready", 1.2, {}),
        DiscoveredNode("192.168.1.20", 8880, "zgpu", "ready", 0.9, {}),
    ]

    tokens = {
        "network_cpu_192.168.1.10_9200": "a" * 32,
        "zgpu_192.168.1.20_8880": "b" * 32,
    }
    with (
        patch.dict(os.environ, {"ZGPU_CLUSTER_WORKER_TOKENS": json.dumps(tokens)}),
        patch("cluster.discovery.scanner.NetworkComputeScanner.scan_subnet", return_value=mock_nodes),
    ):
        count = pool.auto_discover_and_powerup(subnet_prefix="192.168.1", start_host=10, end_host=20)
        assert count == 2
        assert len(pool.nodes) == 2
        assert "network_cpu_192.168.1.10_9200" in pool.nodes
        assert "zgpu_192.168.1.20_8880" in pool.nodes
