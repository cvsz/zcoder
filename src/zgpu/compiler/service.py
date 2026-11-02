"""zGPU Web & REST Compiler Service.

Exposes a web IDE and JSON API for interactive compiling, assembling, and disassembling
zGPU SIMT assembly and high-level DSL expressions.
"""

from __future__ import annotations

import json
import logging
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

from zgpu.isa.assembler import Assembler
from zgpu.runtime.network_policy import require_loopback_host

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("zCompiler-Service")

COMPILER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>zGPU Online Compiler & Disassembler (zcc)</title>
    <style>
        :root { --bg: #0d1117; --card: #161b22; --border: #30363d; --text: #c9d1d9; --accent: #58a6ff; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--bg); color: var(--text); padding: 20px; margin: 0; }
        h1 { color: #fff; margin-top: 0; }
        .container { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        .card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 15px; }
        textarea { width: 100%; height: 350px; background: #000; border: 1px solid var(--border); color: #7ee787; font-family: monospace; font-size: 13px; padding: 10px; box-sizing: border-box; border-radius: 6px; }
        button { background: #238636; color: white; border: none; padding: 10px 18px; border-radius: 6px; cursor: pointer; font-weight: bold; margin-top: 10px; font-size: 14px; }
        button:hover { background: #2ea043; }
        pre { background: #000; color: var(--accent); padding: 10px; border-radius: 6px; overflow-x: auto; font-family: monospace; font-size: 13px; height: 350px; margin: 0; box-sizing: border-box; }
        .status { margin-top: 10px; font-size: 13px; color: #8b949e; }
    </style>
</head>
<body>
    <h1>⚡ zGPU Online Compiler Studio (zcc)</h1>
    <div class="status">Target: zISA 32-bit SIMT Vector Engine • Cycle-Accurate Bytecode Assembler</div>
    <br/>
    <div class="container">
        <div class="card">
            <h3>zISA Source / Assembly Editor</h3>
            <textarea id="src"># Vectorized Elementwise SAXPY Kernel
GET.TID R0
VMUL R5, R0, R1         # offset = tid * stride
VADD R6, R3, R5         # addr_x = base_x + offset
VADD R7, R4, R5         # addr_y = base_y + offset

VLOAD.G R8, R6, 0       # x = *addr_x
VLOAD.G R9, R7, 0       # y = *addr_y
VFMUL R10, R2, R8       # a_x = a * x
VFADD R11, R10, R9      # out = a_x + y
VSTORE.G R7, R11, 0     # *addr_y = out
HALT
</textarea>
            <button onclick="compileCode()">⚡ Assemble & Compile Bytecode</button>
        </div>
        <div class="card">
            <h3>Compiled Binary Bytecode & Disassembly</h3>
            <pre id="out">Click 'Assemble & Compile Bytecode' to view hex word machine output...</pre>
        </div>
    </div>

    <script>
        async function compileCode() {
            const src = document.getElementById('src').value;
            const res = await fetch('/api/compile', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({source: src})
            });
            const data = await res.json();
            if (data.ok) {
                let text = "=== COMPILATION SUCCESSFUL ===\\n";
                text += `Total Instructions: ${data.instructions_count}\\n`;
                text += `Binary Byte Size: ${data.bytes_count} Bytes\\n\\n`;
                text += "Hex Words (32-bit little-endian):\\n";
                data.bytecode_hex.forEach((w, i) => {
                    text += `  [${i.toString().padStart(3, '0')}] 0x${w}\\n`;
                });
                document.getElementById('out').innerText = text;
            } else {
                document.getElementById('out').innerText = `=== ERROR ===\\n${data.error}`;
            }
        }
    </script>
</body>
</html>
"""


class CompilerHTTPHandler(BaseHTTPRequestHandler):
    MAX_REQUEST_BYTES = 1_048_576
    MAX_SOURCE_CHARS = 65_536

    def do_GET(self):
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self._send_security_headers()
            self.end_headers()
            self.wfile.write(COMPILER_HTML.encode("utf-8"))
        elif url.path == "/api/health":
            self._send_json({"ok": True, "compiler": "zcc-v1.0", "target": "zISA-32"})
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        url = urlparse(self.path)
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length < 0 or length > self.MAX_REQUEST_BYTES:
                raise ValueError("Request body must be at most 1 MiB")
            body = self.rfile.read(length).decode("utf-8")
            payload = json.loads(body) if body else {}
            if not isinstance(payload, dict):
                raise ValueError("Request body must be a JSON object")
        except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=400)
            return

        if url.path == "/api/compile":
            source = payload.get("source", "")
            if not isinstance(source, str):
                self._send_json({"ok": False, "error": "source must be a string"}, status=400)
                return
            if len(source) > self.MAX_SOURCE_CHARS:
                self._send_json({"ok": False, "error": "source must be at most 65536 characters"}, status=413)
                return
            try:
                words = Assembler.assemble(source)
                hex_words = [f"{w:08X}" for w in words]
                self._send_json(
                    {
                        "ok": True,
                        "instructions_count": len(words),
                        "bytes_count": len(words) * 4,
                        "bytecode": words,
                        "bytecode_hex": hex_words,
                    }
                )
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)})
        else:
            self.send_error(404, "Not Found")

    def _send_security_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
            "connect-src 'self'; base-uri 'none'; frame-ancestors 'none'",
        )

    def _send_json(self, data: dict, status: int = 200):
        body_bytes = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._send_security_headers()
        self.send_header("Content-Length", str(len(body_bytes)))
        self.end_headers()
        self.wfile.write(body_bytes)

    def log_message(self, format, *args):
        pass


def run_compiler_service(host: str = "127.0.0.1", port: int = 9100):
    require_loopback_host(host, "The compiler service")
    server = HTTPServer((host, port), CompilerHTTPHandler)
    log.info("zGPU Web Compiler Studio running at http://%s:%d/", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9100
    run_compiler_service(port=port)
