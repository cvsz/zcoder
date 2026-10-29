"""zGPU LLM JSON-RPC server with multi-model software simulation.

Exposes a JSON-RPC 2.0 interface on standard HTTP that serves LLM generation
requests through the zGPU Tensor Core and SIMT software runtime.
"""

from __future__ import annotations

import json
import logging
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import urlparse

from zgpu.llm.model_registry import ModelRegistry
from zgpu.llm.openai_compat import CompletionRequestError, OpenAICompatibleAdapter
from zgpu.llm.transformer import LLMConfig
from zgpu.runtime.network_policy import require_loopback_host

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("zGPU-Server")

# Global Model Registry managing multiple models
registry = ModelRegistry()
openai_adapter = OpenAICompatibleAdapter(registry)


class JSONRPCHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Respond with health status, models list, or endpoints on GET requests."""
        path = urlparse(getattr(self, "path", "/rpc")).path
        if path == "/v1/models":
            self._send_json(openai_adapter.list_models())

        elif path in ("/", "/rpc", "/health"):
            data = {
                "jsonrpc": "2.0",
                "result": {
                    "healthy": True,
                    "engine": "zGPU-Python-SIMT-TensorCore-Simulator",
                    "device": "zGPU-Simulator-0",
                    "status": "ready",
                    "available_models": [m["name"] for m in registry.list_models()],
                    "endpoints": {
                        "GET /models": "List available models and configuration",
                        "POST /rpc": "JSON-RPC 2.0 API (methods: system.health, llm.models, llm.add_model, llm.generate)",
                    },
                },
            }
            self._send_json(data)

        elif self.path in ("models", "/models", "/api/models"):
            data = {
                "jsonrpc": "2.0",
                "result": {
                    "models": registry.list_models(),
                },
            }
            self._send_json(data)

        else:
            self.send_error(404, "Endpoint not found")

    def do_POST(self):
        path = urlparse(getattr(self, "path", "/rpc")).path
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            self._send_openai_error("Invalid Content-Length", status=400)
            return
        if content_length < 0 or content_length > 1_048_576:
            self._send_openai_error("Request body must be at most 1 MiB", status=413)
            return
        try:
            raw_body = self.rfile.read(content_length).decode("utf-8")
        except UnicodeDecodeError:
            self._send_openai_error("Request body must be UTF-8 JSON", status=400)
            return

        if path == "/v1/chat/completions":
            try:
                payload = json.loads(raw_body)
                if not isinstance(payload, dict):
                    raise CompletionRequestError("request body must be a JSON object")
                if payload.get("stream", False):
                    self._stream_openai_completion(payload)
                else:
                    self._send_json(openai_adapter.create_completion(payload))
            except (json.JSONDecodeError, CompletionRequestError) as exc:
                self._send_openai_error(str(exc), status=400)
            except (BrokenPipeError, ConnectionResetError):
                log.info("Client disconnected during streamed completion")
            except Exception:
                log.exception("OpenAI-compatible completion failed")
                self._send_openai_error("The zGPU model could not complete the request", status=500)
            return

        try:
            req = json.loads(raw_body)
            method = req.get("method")
            params = req.get("params", {})
            req_id = req.get("id")

            if method == "system.health":
                result = {
                    "healthy": True,
                    "engine": "zGPU-Python-SIMT-TensorCore-Simulator",
                    "device": "zGPU-Simulator-0",
                    "status": "ready",
                    "models": [m["name"] for m in registry.list_models()],
                }
                resp_payload = {"jsonrpc": "2.0", "id": req_id, "result": result}

            elif method in ("llm.models", "models.list"):
                result = {"models": registry.list_models()}
                resp_payload = {"jsonrpc": "2.0", "id": req_id, "result": result}

            elif method in ("llm.add_model", "models.add"):
                model_name = params.get("name")
                if not model_name:
                    raise ValueError("Parameter 'name' is required")
                d_model = int(params.get("d_model", 16))
                if d_model % 4 != 0:
                    raise ValueError("d_model must be a multiple of 4 for zGPU Tensor Core tiling")
                num_layers = int(params.get("num_layers", 2))
                num_heads = int(params.get("num_heads", 2))
                d_ff = int(params.get("d_ff", d_model * 2))
                vocab_size = int(params.get("vocab_size", 128))
                max_seq_len = int(params.get("max_seq_len", 64))
                desc = params.get("description", f"Custom model {model_name}")
                tags = params.get("tags", ["custom"])

                cfg = LLMConfig(
                    vocab_size=vocab_size,
                    d_model=d_model,
                    num_heads=num_heads,
                    d_ff=d_ff,
                    num_layers=num_layers,
                    max_seq_len=max_seq_len,
                )
                registry.register_model(name=model_name, config=cfg, description=desc, tags=tags)
                result = {
                    "success": True,
                    "message": f"Model '{model_name}' successfully added to zGPU registry",
                    "model": model_name,
                    "config": {
                        "d_model": d_model,
                        "num_layers": num_layers,
                        "num_heads": num_heads,
                        "vocab_size": vocab_size,
                    },
                }
                resp_payload = {"jsonrpc": "2.0", "id": req_id, "result": result}

            elif method == "llm.generate":
                prompt = params.get("prompt", "")
                model_name = params.get("model")
                max_tokens = int(params.get("max_tokens", 16))
                result = registry.generate(prompt=prompt, model_name=model_name, max_tokens=max_tokens)
                resp_payload = {"jsonrpc": "2.0", "id": req_id, "result": result}

            else:
                resp_payload = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }

        except Exception as e:
            log.exception("Error processing RPC request")
            resp_payload = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": str(e)},
            }

        self._send_json(resp_payload)

    def _stream_openai_completion(self, payload: dict[str, Any]) -> None:
        headers_sent = False

        def send_event(event: dict[str, Any]) -> None:
            nonlocal headers_sent
            if not headers_sent:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-transform")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                headers_sent = True
            data = json.dumps(event, separators=(",", ":"))
            self.wfile.write(f"data: {data}\n\n".encode())
            self.wfile.flush()

        try:
            openai_adapter.create_completion(payload, event_callback=send_event)
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except CompletionRequestError:
            if not headers_sent:
                raise
            log.exception("Invalid streamed completion request")
            self.wfile.write(
                b'data: {"error":{"message":"Invalid chat completion request","type":"invalid_request_error"}}\n\n'
            )
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            raise
        except Exception:
            if not headers_sent:
                raise
            log.exception("Streamed zGPU completion failed")
            self.wfile.write(
                b'data: {"error":{"message":"The zGPU model could not complete the request"}}\n\n'
            )
            self.wfile.flush()

    def _send_json(self, data: Any, status: int = 200):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_openai_error(self, message: str, status: int = 400):
        self._send_json(
            {"error": {"message": message, "type": "invalid_request_error", "param": None, "code": status}},
            status=status,
        )

    def log_message(self, format, *args):
        # Override to suppress default noisy console logs
        pass


def run_server(host: str = "127.0.0.1", port: int = 8880):
    require_loopback_host(host, "The LLM API")
    server = HTTPServer((host, port), JSONRPCHandler)
    log.info("zGPU simulator LLM API listening on http://%s:%d/rpc", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down zGPU Server...")
        server.server_close()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8880
    run_server(port=port)
