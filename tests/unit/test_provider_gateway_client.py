"""Tests for the Coder provider-gateway client (streaming, auth, model discovery).

The mock gateway is a real in-process HTTP server on localhost so the tests
exercise genuine urllib request/response behaviour, including SSE parsing and
Authorization header forwarding. The remote-gateway (192.168.1.100) paths are
covered with a patched opener since that host is not reachable from this
environment.
"""

import http.server
import json
import threading
from unittest.mock import MagicMock, patch

import pytest

from zcoder.core.exceptions import AuthenticationError, TransientAPIError
from zcoder.services.coder import Coder


@pytest.fixture(autouse=True)
def fresh_breaker(monkeypatch):
    import zcoder.core.resilience as resilience

    monkeypatch.setattr(
        "zcoder.services.coder._default_breaker",
        resilience.CircuitBreaker(failure_threshold=10, reset_timeout=0.01),
    )


@pytest.fixture(autouse=True)
def no_openai_env(monkeypatch):
    """Keep OPENAI_* env from leaking into Coder constructors under test."""
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ZCODER_BASE_URL", raising=False)


class _GatewayHandler(http.server.BaseHTTPRequestHandler):
    """Mock OpenAI-compatible provider gateway driven by shared ``state``."""

    state = None

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_sse(self, chunks):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for chunk in chunks:
            self.wfile.write(f"data: {json.dumps(chunk)}\r\n\r\n".encode())
        self.wfile.write(b"data: [DONE]\r\n\r\n")

    def _authorized(self):
        expected = f"Bearer {self.state.get('expected_key')}"
        return self.headers.get("Authorization") == expected

    def do_POST(self):
        if not self.path.startswith("/v1/chat/completions"):
            self._send_json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError:
            payload = {}
        self.state["last_payload"] = payload
        self.state["last_headers"] = dict(self.headers)
        if self.state.get("auth_required") and not self._authorized():
            self._send_json(401, {"error": "invalid key"})
            return
        if self.state.get("http_status"):
            self._send_json(self.state["http_status"], {"error": "upstream"})
            return
        if payload.get("stream"):
            self._send_sse(
                self.state.get("stream_chunks", [{"choices": [{"delta": {"content": "default"}}]}])
            )
        else:
            self._send_json(
                200,
                {"choices": [{"message": {"content": self.state.get("completion", "ok")}}]},
            )

    def do_GET(self):
        if self.path == "/v1/models":
            if self.state.get("auth_required") and not self._authorized():
                self._send_json(401, {"error": "invalid key"})
                return
            self._send_json(200, {"data": self.state.get("models", [{"id": "model-a"}])})
        else:
            self._send_json(404, {"error": "not found"})

    def log_message(self, *args):
        pass  # keep test output quiet


def _make_handler(state):
    class Handler(_GatewayHandler):
        pass

    Handler.state = state
    return Handler


@pytest.fixture
def gateway_server():
    state = {
        "auth_required": False,
        "expected_key": None,
        "completion": "ok",
        "models": [{"id": "model-a"}, {"id": "model-b"}],
        "stream_chunks": [
            {"choices": [{"delta": {"content": "Hello"}}]},
            {"choices": [{"delta": {"content": "world"}}]},
        ],
    }
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(state))
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}/v1", state
    finally:
        server.shutdown()
        server.server_close()


class _FakeResp:
    """Context-manager iterable that stands in for an urllib response."""

    def __init__(self, lines):
        self._lines = lines

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __iter__(self):
        return iter(self._lines)


# -- streaming -------------------------------------------------------------


def test_streaming_yields_chunks_via_sse(gateway_server):
    base_url, state = gateway_server
    coder = Coder(model="zqwen", base_url=base_url)
    chunks = list(coder.generate("hi", stream=True))

    assert chunks == ["Hello", "world"]
    assert state["last_payload"]["stream"] is True
    # Loopback endpoint: no Authorization header is required or sent.
    assert state["last_headers"].get("Authorization") is None


def test_streaming_skips_non_data_and_done_lines(gateway_server):
    base_url, state = gateway_server
    state["stream_chunks"] = [
        ": this is a comment\n",
        {"choices": [{"delta": {"content": "keep"}}]},
        "data: [DONE]",
        "not an sse line",
        {"choices": [{"delta": {}}]},
    ]
    coder = Coder(model="zqwen", base_url=base_url)
    assert list(coder.generate("hi", stream=True)) == ["keep"]


def test_streaming_remote_sends_bearer_header():
    captured = {}

    def fake_open(req, timeout=None):
        captured["req"] = req
        lines = [
            b'data: {"choices":[{"delta":{"content":"ab"}}]}\r\n\r\n',
            b"data: [DONE]\r\n\r\n",
        ]
        return _FakeResp(lines)

    coder = Coder(model="zqwen", base_url="http://192.168.1.100:8080/v1", api_key="sk-remote")
    with patch("zcoder.services.coder._open_local", side_effect=fake_open):
        assert list(coder.generate("hi", stream=True)) == ["ab"]

    req = captured["req"]
    assert req.full_url == "http://192.168.1.100:8080/v1/chat/completions"
    assert req.get_header("Authorization") == "Bearer sk-remote"
    assert json.loads(req.data.decode())["stream"] is True


def test_streaming_remote_without_key_returns_config_error():
    # The remote-without-key check happens before the stream branch, so
    # generate returns the error string even when stream=True.
    coder = Coder(model="zqwen", base_url="http://192.168.1.100:8080/v1")
    result = coder.generate("hi", stream=True)
    assert "Remote provider gateway requires OPENAI_API_KEY" in result


def test_streaming_rejects_malformed_or_missing_authorization(gateway_server):
    base_url, state = gateway_server
    state["auth_required"] = True
    state["expected_key"] = "sk-expected"
    # No key supplied -> the gateway rejects the missing/malformed Authorization.
    # Streaming errors propagate when the generator is iterated.
    coder = Coder(model="zqwen", base_url=base_url)
    gen = coder.generate("hi", stream=True)
    with pytest.raises(AuthenticationError):
        next(gen)


def test_streaming_authorized_remote_receives_completion(gateway_server):
    base_url, state = gateway_server
    state["auth_required"] = True
    state["expected_key"] = "sk-expected"
    coder = Coder(model="zqwen", base_url=base_url, api_key="sk-expected")
    assert coder.generate("hi") == "ok"
    assert state["last_headers"].get("Authorization") == "Bearer sk-expected"


def test_streaming_timeout_is_surfaced(gateway_server):
    base_url, _ = gateway_server
    coder = Coder(model="zqwen", base_url=base_url)

    def boom(req, timeout=None):
        raise TimeoutError("connect timed out")

    with patch("zcoder.services.coder._open_local", side_effect=boom):
        gen = coder.generate("hi", stream=True)
        with pytest.raises(TransientAPIError):
            next(gen)


def test_streaming_provider_unavailable_is_surfaced(gateway_server):
    base_url, _ = gateway_server
    coder = Coder(model="zqwen", base_url=base_url)

    def boom(req, timeout=None):
        raise ConnectionError("refused")

    with patch("zcoder.services.coder._open_local", side_effect=boom):
        gen = coder.generate("hi", stream=True)
        with pytest.raises(TransientAPIError):
            next(gen)


# -- model discovery ---------------------------------------------------------


def test_list_models_returns_ids(gateway_server):
    base_url, _ = gateway_server
    coder = Coder(model="zqwen", base_url=base_url)
    assert coder.list_models() == ["model-a", "model-b"]


def test_list_models_adds_v1_path_when_omitted(gateway_server):
    base_url, _ = gateway_server
    base_without_v1 = base_url.removesuffix("/v1")
    coder = Coder(model="zqwen", base_url=base_without_v1)
    assert coder.list_models() == ["model-a", "model-b"]


def test_list_models_unauthorized_raises(gateway_server):
    base_url, state = gateway_server
    state["auth_required"] = True
    state["expected_key"] = "sk-expected"
    coder = Coder(model="zqwen", base_url=base_url)
    with pytest.raises(AuthenticationError):
        coder.list_models()


def test_list_models_authorized_returns_ids(gateway_server):
    base_url, state = gateway_server
    state["auth_required"] = True
    state["expected_key"] = "sk-expected"
    coder = Coder(model="zqwen", base_url=base_url, api_key="sk-expected")
    assert coder.list_models() == ["model-a", "model-b"]


def test_list_models_remote_without_key_returns_empty():
    coder = Coder(model="zqwen", base_url="http://192.168.1.100:8080/v1")
    assert coder.list_models() == []


def test_list_models_invalid_url_returns_empty():
    coder = Coder(model="zqwen", base_url="http://127.0.0.1:8080/v1?redirect=1")
    assert coder.list_models() == []


def test_list_models_provider_unavailable_raises(gateway_server):
    base_url, _ = gateway_server
    coder = Coder(model="zqwen", base_url=base_url)

    def boom(req, timeout=None):
        raise ConnectionError("refused")

    with patch("zcoder.services.coder._open_local", side_effect=boom):
        with pytest.raises(TransientAPIError):
            coder.list_models()


# -- gateway headers ----------------------------------------------------------


def test_gateway_headers_omits_authorization_without_key():
    coder = Coder(model="zqwen", base_url="http://127.0.0.1:8080/v1")
    assert coder._gateway_headers() == {"Content-Type": "application/json"}


def test_gateway_headers_sends_bearer_with_key():
    coder = Coder(model="zqwen", base_url="http://127.0.0.1:8080/v1", api_key="sk-test")
    assert coder._gateway_headers() == {
        "Content-Type": "application/json",
        "Authorization": "Bearer sk-test",
    }


# -- non-stream remote bearer --------------------------------------------------


def test_non_stream_remote_sends_bearer_header():
    captured = {}

    def fake_open(req, timeout=None):
        captured["req"] = req
        resp = MagicMock()
        resp.read.return_value = json.dumps({"choices": [{"message": {"content": "done"}}]}).encode()
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        return resp

    coder = Coder(model="zqwen", base_url="http://192.168.1.100:8080/v1", api_key="sk-remote")
    with patch("zcoder.services.coder._open_local", side_effect=fake_open):
        assert coder.generate("hi") == "done"

    assert captured["req"].get_header("Authorization") == "Bearer sk-remote"
