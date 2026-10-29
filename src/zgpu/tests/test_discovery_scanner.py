from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from zgpu.cluster.discovery.scanner import NetworkComputeScanner


def test_probe_node_does_not_follow_redirects():
    target_hits = []

    class TargetHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            target_hits.append(self.path)
            body = b'{"status":"ready"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            self.do_GET()

        def log_message(self, *_args):
            return

    target_server = ThreadingHTTPServer(("127.0.0.1", 0), TargetHandler)
    target_thread = Thread(target=target_server.serve_forever, daemon=True)
    target_thread.start()
    target_url = f"http://127.0.0.1:{target_server.server_port}/redirected"

    class RedirectHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302)
            self.send_header("Location", target_url)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_POST(self):
            self.do_GET()

        def log_message(self, *_args):
            return

    redirect_server = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
    redirect_thread = Thread(target=redirect_server.serve_forever, daemon=True)
    redirect_thread.start()
    try:
        scanner = NetworkComputeScanner(probe_ports=[redirect_server.server_port], timeout=0.2)
        assert scanner.probe_node("127.0.0.1", redirect_server.server_port) is None
        assert target_hits == []
    finally:
        redirect_server.shutdown()
        redirect_server.server_close()
        redirect_thread.join(timeout=2)
        target_server.shutdown()
        target_server.server_close()
        target_thread.join(timeout=2)
