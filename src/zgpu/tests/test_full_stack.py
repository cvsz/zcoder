"""Tests for RTL modules, Rasterizer, and Runtime API."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zgpu.compiler.compiler import ZKernelCompiler
from zgpu.rasterizer.rasterizer import Framebuffer, Rasterizer, Vertex
from zgpu.runtime.runtime import ZRuntime


def test_rasterizer_triangle_depth_and_color():
    fb = Framebuffer(width=32, height=32)
    fb.clear((0, 0, 0))
    rast = Rasterizer()

    # Red triangle near camera (z=0.2)
    v0 = Vertex(5, 5, 0.2, 1.0, 0.0, 0.0)
    v1 = Vertex(25, 5, 0.2, 1.0, 0.0, 0.0)
    v2 = Vertex(15, 25, 0.2, 1.0, 0.0, 0.0)
    rast.draw_triangle(fb, v0, v1, v2)

    # Center pixel (15, 10) must be colored red
    assert fb.color[10][15][0] > 200
    assert fb.depth[10][15] < 0.5


def test_zruntime_memory_and_kernel():
    rt = ZRuntime(num_sms=2)
    ptr_a = rt.malloc(128)
    ptr_b = rt.malloc(128)
    assert ptr_a.addr % 128 == 0
    assert ptr_b.addr % 128 == 0

    data = [1.25, 2.5, 5.0, 10.0]
    rt.memcpy_h2d(ptr_a, data)
    readback = rt.memcpy_d2h(ptr_a, 4)
    for original, read in zip(data, readback, strict=False):
        assert abs(original - read) < 1e-4


def test_compiler_code_generation():
    comp = ZKernelCompiler()
    add_code = comp.compile_elementwise_add()
    relu_code = comp.compile_relu()
    assert "VFADD" in add_code
    assert "BRA.DIV" in relu_code


def test_ast_jit_compiler():
    from zgpu.compiler.ast_compiler import AstJitCompiler

    def sample_add(out, a, b):
        return a + b

    jit = AstJitCompiler()
    src = jit.compile_binary_expr(sample_add)
    assert "VFADD" in src
    bytecode = jit.compile_to_bytecode(src)
    assert len(bytecode) > 0


def test_compiler_service_api():
    import json
    from unittest.mock import MagicMock

    from zgpu.compiler.service import CompilerHTTPHandler

    handler = CompilerHTTPHandler.__new__(CompilerHTTPHandler)
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler.wfile = MagicMock()

    # Test POST /api/compile
    handler.path = "/api/compile"
    src = "GET.TID R0\nHALT"
    req_body = json.dumps({"source": src}).encode("utf-8")
    handler.rfile = MagicMock()
    handler.rfile.read.return_value = req_body
    handler.headers = {"Content-Length": str(len(req_body))}
    handler.do_POST()

    written_data = b"".join(call.args[0] for call in handler.wfile.write.call_args_list)
    res = json.loads(written_data.decode("utf-8"))
    assert res["ok"] is True
    assert res["instructions_count"] == 2


def test_compiler_service_rejects_network_wide_bind():
    from zgpu.compiler.service import run_compiler_service

    with pytest.raises(ValueError, match="loopback only"):
        run_compiler_service(host="0.0.0.0")


def test_compiler_service_rejects_malformed_and_oversized_requests():
    import json
    from unittest.mock import MagicMock

    from zgpu.compiler.service import CompilerHTTPHandler

    handler = CompilerHTTPHandler.__new__(CompilerHTTPHandler)
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler.wfile = MagicMock()
    handler.path = "/api/compile"
    handler.headers = {"Content-Length": str(CompilerHTTPHandler.MAX_REQUEST_BYTES + 1)}
    handler.rfile = MagicMock()
    handler.do_POST()
    assert handler.send_response.call_args.args[0] == 400

    handler.send_response.reset_mock()
    body = json.dumps({"source": 42}).encode()
    handler.headers = {"Content-Length": str(len(body))}
    handler.rfile.read.return_value = body
    handler.do_POST()
    assert handler.send_response.call_args.args[0] == 400
