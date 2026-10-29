import json
from http.client import HTTPConnection
from http.server import HTTPServer
from threading import Thread
from unittest.mock import MagicMock, patch

import pytest

from zgpu.cluster.network_pool import NetworkCPUPool
from zgpu.cluster.worker.cpu_worker import CPUComputeEngine, CPUWorkerHTTPHandler, run_cpu_worker


@pytest.fixture
def authenticated_worker():
    class Handler(CPUWorkerHTTPHandler):
        auth_token = "t" * 32

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_authenticated_pool_worker_http_round_trip(authenticated_worker):
    host, port = authenticated_worker.server_address
    pool = NetworkCPUPool()
    pool.register_node("worker", f"http://{host}:{port}", token="t" * 32)
    assert pool.ping_nodes() == {"worker": True}
    assert pool.dispatch_remote_gemm("worker", [[2.0]], [[3.0]]) == [[6.0]]

    pool.register_node("wrong-token", f"http://{host}:{port}", token="x" * 32)
    assert pool.ping_nodes()["wrong-token"] is False

    connection = HTTPConnection(host, port, timeout=2)
    try:
        connection.request("POST", "/", body="{}", headers={"Authorization": "Bearer é"})
        response = connection.getresponse()
        assert response.status == 401
        assert json.loads(response.read())["error"]["message"] == "Unauthorized"
    finally:
        connection.close()


def test_worker_redirect_is_rejected_before_forwarding_token(authenticated_worker):
    forwarded = []

    class RedirectingHandler(CPUWorkerHTTPHandler):
        def do_POST(self):
            self.send_response(302)
            self.send_header("Location", "/capture")
            self.end_headers()

        def do_GET(self):
            forwarded.append(self.headers.get("Authorization"))
            self._send_json({"result": {"matrix": [[6.0]]}})

    authenticated_worker.RequestHandlerClass = RedirectingHandler
    host, port = authenticated_worker.server_address
    pool = NetworkCPUPool()
    pool.register_node("worker", f"http://{host}:{port}", token="t" * 32)
    with pytest.raises(ValueError, match="redirect"):
        pool.dispatch_remote_gemm("worker", [[2.0]], [[3.0]])
    assert forwarded == []


@pytest.mark.parametrize("token", ["short", "t" * 513, "t" * 32 + "\n", "é" * 32, " " * 32])
def test_worker_pool_rejects_unsafe_tokens(token):
    with pytest.raises(ValueError, match="worker token"):
        NetworkCPUPool().register_node("worker", "http://127.0.0.1:9200", token=token)


def test_cpu_compute_engine_gemm():
    A = [[1.0, 2.0], [3.0, 4.0]]
    B = [[5.0, 6.0], [7.0, 8.0]]
    # C[0][0] = 1*5 + 2*7 = 19
    # C[0][1] = 1*6 + 2*8 = 22
    # C[1][0] = 3*5 + 4*7 = 43
    # C[1][1] = 3*6 + 4*8 = 50
    out = CPUComputeEngine.gemm_chunk(A, B)
    assert out[0][0] == 19.0
    assert out[0][1] == 22.0
    assert out[1][0] == 43.0
    assert out[1][1] == 50.0


def test_cpu_worker_http_handler_gemm():
    handler = CPUWorkerHTTPHandler.__new__(CPUWorkerHTTPHandler)
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler.wfile = MagicMock()

    req_body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "compute.gemm",
            "params": {"A": [[1.0, 1.0]], "B": [[2.0], [2.0]]},
        }
    ).encode("utf-8")

    handler.rfile = MagicMock()
    handler.rfile.read.return_value = req_body
    handler.headers = {"Content-Length": str(len(req_body))}
    handler.do_POST()

    written_data = b"".join(call.args[0] for call in handler.wfile.write.call_args_list)
    res = json.loads(written_data.decode("utf-8"))
    assert res["id"] == 1
    assert res["result"]["matrix"] == [[4.0]]


def test_cpu_worker_requires_bearer_token_when_configured():
    handler = CPUWorkerHTTPHandler.__new__(CPUWorkerHTTPHandler)
    handler.auth_token = "t" * 32
    handler.headers = {"Content-Length": "0"}
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler.wfile = MagicMock()
    handler.rfile = MagicMock()
    handler.rfile.read.return_value = b"{}"

    handler.do_POST()

    handler.send_response.assert_called_once_with(401)
    assert b"Unauthorized" in b"".join(call.args[0] for call in handler.wfile.write.call_args_list)


def test_cpu_worker_refuses_non_loopback_bind_without_long_token(monkeypatch):
    monkeypatch.delenv("ZGPU_CPU_WORKER_TOKEN", raising=False)
    with pytest.raises(ValueError, match=r"non-loopback.*require"):
        run_cpu_worker(host="0.0.0.0", port=0, token=None)  # nosec B104


def test_cpu_worker_rejects_non_finite_and_oversized_compute_inputs():
    with pytest.raises(ValueError, match="finite"):
        CPUComputeEngine.gemm_chunk([[float("nan")]], [[1.0]])

    with pytest.raises(ValueError, match="compute limit"):
        CPUComputeEngine.gemm_chunk(
            [[1.0] * 500 for _ in range(5)],
            [[1.0] * 500 for _ in range(500)],
        )


def test_network_pool_hybrid_powerup():
    pool = NetworkCPUPool()
    pool.register_node("node_alpha", "http://192.168.1.50:9200", token="t" * 32)

    A = [[1.0 for _ in range(8)] for _ in range(8)]
    B = [[2.0 for _ in range(8)] for _ in range(8)]

    # Mock remote worker response for CPU portion (4x8) @ (8x8) -> 4x8 of 16.0
    cpu_mock_chunk = [[16.0 for _ in range(8)] for _ in range(4)]

    with patch.object(pool, "dispatch_remote_gemm", return_value=cpu_mock_chunk):
        out = pool.hybrid_gemm_powerup(A, B, gpu_fraction=0.5)
        assert len(out) == 8
        assert len(out[0]) == 8
        # GPU half (first 4 rows) should be 16.0, CPU half (last 4 rows) should be 16.0
        for r in range(8):
            for c in range(8):
                assert pytest.approx(out[r][c], rel=1e-3) == 16.0


def test_network_pool_only_accepts_local_worker_urls():
    pool = NetworkCPUPool()
    for url in (
        "http://example.com:9200",
        "http://127.0.0.1:9200/path",
        "http://user:password@192.168.1.10:9200",
        "https://192.168.1.10:9200",
    ):
        with pytest.raises(ValueError):
            pool.register_node("unsafe", url)

    with pytest.raises(ValueError, match="require an authentication token"):
        pool.register_node("unauthenticated", "http://192.168.1.10:9200")
    pool.register_node("local", "http://192.168.1.10:9200", token="t" * 32)
    assert pool.nodes["local"].url == "http://192.168.1.10:9200"
    assert pool._request_headers(pool.nodes["local"])["Authorization"] == f"Bearer {'t' * 32}"
