"""tests/test_upgrade14_localai_suite.py — Comprehensive Test Suite for Upgrade-14 Local AI Stack.

Verifies:
  1. Hardware Profiler & Model Fit Estimator (CPU, RAM, GPU, safe fit calculation)
  2. Local Model Gateway (OllamaAdapter, listing, mock/fallback execution)
  3. Local Repository Indexer / RAG (secret redaction, term frequency indexing, search)
  4. Local MCP Tool Registry (MCP 2026-07-28 schema, call execution, error wrapping)
  5. Autonomous Local Coding Pipeline (Inspect -> Plan -> Edit with ZERO paid calls proof)
"""

from zcoder.enterprise.local_ai_stack import (
    AutonomousLocalCodingPipeline,
    HardwareProfiler,
    LocalMCPServer,
    LocalRepositoryIndexer,
    MCPToolDefinition,
    ModelFit,
    OllamaAdapter,
)


def test_hardware_profiler_and_fit_estimator():
    profile = HardwareProfiler.profile()
    assert profile.cpu_cores >= 1
    assert profile.ram_total_gb > 0.0
    assert profile.gpu_vendor in ("NVIDIA", "AMD", "APPLE", "CPU_ONLY")

    # Fit estimation
    # 7B model @ 4-bit requires ~4.5 GB -> should fit in standard system RAM/VRAM
    fit_7b = HardwareProfiler.estimate_fit(profile, parameter_size_b=7.0, quantization_bits=4)
    assert fit_7b in (ModelFit.FITS, ModelFit.MAYBE)

    # 400B model @ 16-bit requires ~800 GB -> does not fit on standard desktop
    fit_huge = HardwareProfiler.estimate_fit(profile, parameter_size_b=400.0, quantization_bits=16)
    assert fit_huge == ModelFit.DOES_NOT_FIT


def test_local_model_gateway_ollama_adapter(monkeypatch):
    """Both runtime paths are verified deterministic and network-free.

    A real Ollama daemon appearing on the host must not change the outcome
    (a daemon without the probed model installed would otherwise leak the
    simulated marker into the live branch and flip this test between
    machines). The adapter's `safe_urlopen` boundary is therefore replaced
    with an in-memory fake for the live branch, and availability is forced
    down for the offline branch.
    """
    import json

    import zcoder.enterprise.local_ai_stack as local_ai_stack

    class _FakeResponse:
        def __init__(self, body: bytes):
            self.status = 200
            self._body = body

        def read(self) -> bytes:
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *exc_info) -> bool:
            return False

    tags = json.dumps(
        {"models": [{"name": "qwen2.5-coder:7b", "details": {"parameter_size": "7B"}}]}
    ).encode()
    generate = json.dumps({"response": "def addition(a, b):\n    return a + b\n"}).encode()

    def fake_safe_urlopen(req, timeout=None):
        url = getattr(req, "full_url", "")
        if url.endswith("/api/tags"):
            return _FakeResponse(tags)
        if url.endswith("/api/generate"):
            return _FakeResponse(generate)
        raise AssertionError(f"unexpected URL in test: {url}")

    monkeypatch.setattr(local_ai_stack, "safe_urlopen", fake_safe_urlopen)
    adapter = OllamaAdapter(base_url="http://127.0.0.1:11434")

    # Live-adapter path: no simulated marker may ever leak into it.
    models = adapter.list_models()
    assert len(models) >= 1
    assert models[0].provider == "ollama"
    assert adapter.is_available() is True

    result = adapter.chat_complete("qwen2.5-coder:7b", "def add(a, b):")
    assert result.strip(), "live adapter path returned an empty response"
    assert "LOCAL_AI:" not in result, "simulated marker leaked into live path"

    # Offline branch: unavailable inference must fail explicitly.
    monkeypatch.setattr(adapter, "is_available", lambda: False)
    import pytest

    with pytest.raises(RuntimeError, match="Ollama inference server is unavailable"):
        adapter.chat_complete("qwen2.5-coder:7b", "def add(a, b):")


def test_local_repository_indexer_and_secret_redaction():
    indexer = LocalRepositoryIndexer()

    # 1. Normal code file indexing
    code_text = "def calculate_discount(price, rate):\n    return price * (1.0 - rate)"
    ok = indexer.index_file("src/billing.py", code_text)
    assert ok is True

    # 2. Secret file must be ignored
    secret_ok = indexer.index_file(".env.production", "API_KEY=sk_secret_12345")
    assert secret_ok is False

    # 3. Search query retrieval
    results = indexer.search("calculate discount price", top_k=1)
    assert len(results) == 1
    assert results[0][0] == "src/billing.py"
    assert "calculate_discount" in results[0][2]


def test_local_mcp_conformance_and_tool_call():
    server = LocalMCPServer(server_name="test-mcp", version="2026-07-28")

    def dummy_linter(args):
        return {"errors": 0, "status": "clean"}

    tool = MCPToolDefinition(
        name="run_linter",
        description="Executes project linting",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        handler=dummy_linter,
    )
    server.register_tool(tool)

    tools_list = server.list_tools()
    assert len(tools_list) == 1
    assert tools_list[0]["name"] == "run_linter"

    # Execute tool call
    res = server.call_tool("run_linter", {"path": "."})
    assert res["isError"] is False
    assert "clean" in res["content"][0]["text"]


def test_autonomous_coding_pipeline_zero_paid_calls():
    # Use a deterministic in-process provider: this test verifies the
    # pipeline's zero-paid-call guarantee and RAG wiring, not live network
    # behavior (that path is exercised by the Ollama adapter test above).
    class _SimulatedLocalProvider:
        def chat_complete(self, model_id, prompt, tools=None):
            return f"[LOCAL_AI:{model_id}] Simulated code completion for task: {prompt[:40]}"

    pipeline = AutonomousLocalCodingPipeline(
        local_provider=_SimulatedLocalProvider(),
        indexer=LocalRepositoryIndexer(),
        mcp_server=LocalMCPServer(),
    )
    codebase = {
        "calculator.py": "def add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a * b",
        "test_calc.py": "def test_add():\n    assert add(2, 3) == 5",
    }

    result = pipeline.run_task("Fix multiply function", codebase)
    assert result["status"] == "PLAN_GENERATED"
    assert "calculator.py" in result["context_files"]
    assert result["paid_transport_calls"] == 0
    assert result["is_zero_cost"] is True
