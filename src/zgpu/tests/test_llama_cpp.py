"""Tests for the optional local llama.cpp process and API adapter."""

from __future__ import annotations

import json
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from zgpu.llm.llama_cpp import LlamaCppConfig, LlamaCppError, LlamaCppServer, _runtime_environment


class _ModelHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.server.authorization = self.headers.get("Authorization")
        self.server.request_body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.server.stream:
            body = (
                b'data: {"id":"cmpl-1","choices":[{"delta":{"role":"assistant"}}]}\n\n'
                b'data: {"id":"cmpl-1","choices":[{"delta":{"content":"hello"}}]}\n\n'
                b"data: [DONE]\n\n"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
        else:
            response = {
                "id": "cmpl-1",
                "choices": [{"message": {"role": "assistant", "content": "hello"}, "finish_reason": "stop"}],
            }
            if not self.server.no_usage:
                response["usage"] = {"prompt_tokens": 7, "completion_tokens": 1, "total_tokens": 8}
            body = json.dumps(response).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


@pytest.fixture
def model_server():
    server = HTTPServer(("127.0.0.1", 0), _ModelHandler)
    server.stream = False
    server.no_usage = False
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _provider(model_server: HTTPServer) -> LlamaCppServer:
    config = LlamaCppConfig(
        Path("/usr/bin/llama-server"), Path("/models/local.gguf"), port=model_server.server_port
    )
    provider = LlamaCppServer(config)
    provider._process = MagicMock()
    provider._process.poll.return_value = None
    return provider


def test_config_command_uses_explicit_safe_loopback_arguments():
    config = LlamaCppConfig(
        Path("/opt/llama build/llama-server"),
        Path("/srv/private model.gguf"),
        port=8032,
        context_size=8192,
        threads=6,
        batch_size=256,
        gpu_layers=0,
    )
    args = config.command("/tmp/key-file")
    assert args[0] == "/opt/llama build/llama-server"
    assert args[args.index("--model") + 1] == "/srv/private model.gguf"
    assert args[args.index("--api-key-file") + 1] == "/tmp/key-file"
    assert args[args.index("--host") + 1] == "127.0.0.1"
    assert args[args.index("--ctx-size") + 1] == "8192"
    assert args[args.index("--threads") + 1] == "6"
    assert args[args.index("--batch-size") + 1] == "256"
    assert args[args.index("--n-gpu-layers") + 1] == "0"
    assert _runtime_environment().keys() <= {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "LD_LIBRARY_PATH",
        "DYLD_LIBRARY_PATH",
        "CUDA_VISIBLE_DEVICES",
        "HIP_VISIBLE_DEVICES",
        "ROCR_VISIBLE_DEVICES",
        "GGML_VK_VISIBLE_DEVICES",
        "OMP_NUM_THREADS",
    }


def test_environment_config_requires_explicit_executable_and_model(tmp_path, monkeypatch):
    for key in (
        "ZGPU_LLAMA_SERVER_PATH",
        "ZGPU_LLAMA_MODEL_PATH",
        "ZGPU_LLAMA_MODEL_ALIAS",
        "ZGPU_LLAMA_PORT",
        "ZGPU_LLAMA_CONTEXT_SIZE",
        "ZGPU_LLAMA_THREADS",
        "ZGPU_LLAMA_BATCH_SIZE",
        "ZGPU_LLAMA_GPU_LAYERS",
        "ZGPU_LLAMA_STARTUP_TIMEOUT",
    ):
        monkeypatch.delenv(key, raising=False)
    assert LlamaCppConfig.from_environment() is None
    monkeypatch.setenv("ZGPU_LLAMA_SERVER_PATH", "/usr/bin/llama-server")
    with pytest.raises(ValueError, match="Both ZGPU_LLAMA_SERVER_PATH"):
        LlamaCppConfig.from_environment()

    executable = tmp_path / "llama-server"
    model = tmp_path / "model with spaces.gguf"
    executable.write_text("fixture")
    executable.chmod(0o700)
    model.write_bytes(b"GGUF test fixture")
    monkeypatch.setenv("ZGPU_LLAMA_SERVER_PATH", str(executable))
    monkeypatch.setenv("ZGPU_LLAMA_MODEL_PATH", str(model))
    monkeypatch.setenv("ZGPU_LLAMA_MODEL_ALIAS", "zgpu-test-model")
    monkeypatch.setenv("ZGPU_LLAMA_THREADS", "0")
    with pytest.raises(ValueError, match="ZGPU_LLAMA_THREADS"):
        LlamaCppConfig.from_environment()
    monkeypatch.setenv("ZGPU_LLAMA_THREADS", "4")
    config = LlamaCppConfig.from_environment()
    assert config is not None
    assert config.alias == "zgpu-test-model"
    assert config.model_path == model


def test_non_stream_completion_forwards_auth_and_uses_actual_usage(model_server):
    provider = _provider(model_server)
    result = provider.create_completion(
        {"model": "zgpu-local-gguf", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 4}
    )
    assert result["model"] == "zgpu-local-gguf"
    assert result["usage"] == {"prompt_tokens": 7, "completion_tokens": 1, "total_tokens": 8}
    assert model_server.authorization == f"Bearer {provider.api_key}"
    assert model_server.request_body["model"] == "zgpu-local-gguf"


def test_stream_forwards_events_and_requires_done_marker(model_server):
    provider = _provider(model_server)
    model_server.stream = True
    events = []
    result = provider.create_completion(
        {"model": "zgpu-local-gguf", "messages": [{"role": "user", "content": "hi"}], "stream": True},
        events.append,
    )
    assert result is None
    assert events[1]["choices"][0]["delta"]["content"] == "hello"


def test_nonstream_completion_rejects_missing_or_inconsistent_usage(model_server):
    provider = _provider(model_server)
    model_server.no_usage = True
    with pytest.raises(LlamaCppError, match="token usage"):
        provider.create_completion({"messages": [{"role": "user", "content": "hi"}]})


def test_stop_removes_ephemeral_api_key_file(tmp_path):
    config = LlamaCppConfig(Path("/usr/bin/llama-server"), Path("/models/local.gguf"))
    provider = LlamaCppServer(config)
    key_file = tmp_path / "token"
    key_file.write_text("private\n")
    provider._api_key_file = str(key_file)
    process = MagicMock()
    process.poll.return_value = None
    provider._process = process
    provider.stop()
    process.terminate.assert_called_once()
    assert not key_file.exists()


def test_startup_binds_securely_and_does_not_pass_unrelated_secrets(monkeypatch):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    config = LlamaCppConfig(Path("/usr/bin/llama-server"), Path("/models/local.gguf"), port=port)
    provider = LlamaCppServer(config)
    process = MagicMock()
    process.poll.return_value = None
    health = MagicMock()
    health.__enter__.return_value = health
    health.read.return_value = b'{"status":"ok"}'
    health.__exit__.return_value = None
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-reach-runtime")

    with (
        patch("llm.llama_cpp.subprocess.Popen", return_value=process) as spawn,
        patch.object(provider._opener, "open", return_value=health),
    ):
        provider.start()
        argv = spawn.call_args.args[0]
        child_environment = spawn.call_args.kwargs["env"]
        key_path = Path(argv[argv.index("--api-key-file") + 1])
        assert key_path.is_file()
        assert spawn.call_args.kwargs["stdout"] == subprocess.DEVNULL
        assert "OPENAI_API_KEY" not in child_environment
        provider.stop()

    assert not key_path.exists()
    process.terminate.assert_called_once()
