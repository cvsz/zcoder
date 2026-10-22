"""Local Coder transport tests; remote provider calls are forbidden."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from zcoder.services.coder import Coder


def test_default_provider_uses_loopback_without_api_key(monkeypatch):
    monkeypatch.delenv("ZCODER_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    coder = Coder()
    assert coder.provider == "llama_cpp"
    assert coder.api_key == ""
    assert coder.model == "zcoder-qwen2.5-coder-7b"


def test_local_inference_rejects_non_zcoder_model_without_network():
    coder = Coder(provider="llama_cpp", model="claude-sonnet-5")
    with patch(
        "zcoder.services.coder.safe_local_urlopen", side_effect=AssertionError("network forbidden")
    ) as opened:
        result = coder.generate("hello")
    assert "Unsupported local model" in result
    opened.assert_not_called()


def test_local_generate_sends_prompt_to_loopback_only():
    coder = Coder(provider="llama_cpp", base_url="http://127.0.0.1:8080", model="local")
    seen = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, *_args):
            return json.dumps({"choices": [{"message": {"content": "local answer"}}]}).encode()

    def fake_open(request, timeout):
        seen.append(request.full_url)
        assert request.full_url == "http://127.0.0.1:8080/v1/chat/completions"
        assert "x-api-key" not in {name.lower() for name, _value in request.header_items()}
        return Response()

    with patch("zcoder.services.coder.safe_local_urlopen", side_effect=fake_open):
        assert coder.generate("hello") == "local answer"
    assert seen == ["http://127.0.0.1:8080/v1/chat/completions"]


def test_explicit_anthropic_provider_is_blocked_without_network():
    coder = Coder(provider="anthropic", api_key="unused", model="claude-sonnet-5")
    with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")) as urlopen:
        result = coder.generate("hello")
    assert "Remote model providers are disabled" in result
    urlopen.assert_not_called()


def test_non_loopback_endpoint_is_blocked_without_network():
    coder = Coder(provider="llama_cpp", base_url="https://api.anthropic.com", model="local")
    with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")) as urlopen:
        result = coder.generate("hello")
    assert "loopback" in result
    urlopen.assert_not_called()


def test_local_server_failure_returns_safe_error():
    coder = Coder(provider="llama_cpp", base_url="http://127.0.0.1:8080", model="local")
    with patch("zcoder.services.coder.safe_local_urlopen", side_effect=OSError("offline")):
        result = coder.generate("hello")
    assert result.startswith("[ERROR] Local llama.cpp inference failed:")


def test_local_inference_ignores_environment_proxies(monkeypatch):
    received = []
    proxy_received = []

    class ModelHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"choices":[{"message":{"content":"local"}}]}')

        def log_message(self, *_args):
            return

    class ProxyHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            proxy_received.append(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(502)
            self.end_headers()

        def log_message(self, *_args):
            return

    model_server = ThreadingHTTPServer(("127.0.0.1", 0), ModelHandler)
    proxy_server = ThreadingHTTPServer(("127.0.0.1", 0), ProxyHandler)
    servers = (model_server, proxy_server)
    threads = [threading.Thread(target=server.serve_forever, daemon=True) for server in servers]
    for thread in threads:
        thread.start()
    try:
        proxy = f"http://127.0.0.1:{proxy_server.server_port}"
        for name in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"):
            monkeypatch.setenv(name, proxy)
        monkeypatch.setenv("NO_PROXY", "")
        monkeypatch.setenv("no_proxy", "")
        coder = Coder(provider="llama_cpp", base_url=f"http://127.0.0.1:{model_server.server_port}")

        assert coder.generate("proxy-boundary-probe") == "local"
        assert received[0]["messages"][-1]["content"] == "proxy-boundary-probe"
        assert proxy_received == []
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=2)


def test_local_inference_includes_personality_in_system_prompt(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, *_args):
            return b'{"choices":[{"message":{"content":"local"}}]}'

    def fake_open(request, timeout):
        captured.update(json.loads(request.data))
        return Response()

    monkeypatch.setattr("zcoder.services.coder.safe_local_urlopen", fake_open)
    coder = Coder(provider="llama_cpp", personality_style="teaching")

    assert coder.generate("explain", system="Be concise") == "local"
    system_message = captured["messages"][0]
    assert system_message["role"] == "system"
    assert "Be concise" in system_message["content"]
    assert "teaching a beginner" in system_message["content"].lower()
