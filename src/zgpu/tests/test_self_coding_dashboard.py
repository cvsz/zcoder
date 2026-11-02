import base64
import io
import json
from email.message import Message
from types import SimpleNamespace
from unittest.mock import MagicMock
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

import zgpu.dashboard.server as dashboard_server
from zgpu.dashboard.server import DashboardBackend, DashboardHTTPHandler
from zgpu.integrations.assistants import AssistantProfiles
from zgpu.integrations.conversations import ConversationStore
from zgpu.integrations.local_knowledge import LocalKnowledgeStore
from zgpu.integrations.notes import WorkspaceNotes
from zgpu.integrations.prompts import PromptLibrary
from zgpu.isa.assembler import Assembler
from zgpu.self_coding.evaluator import KernelEvaluator
from zgpu.self_coding.generator import SelfCodingEngine


def test_self_coding_engine():
    engine = SelfCodingEngine()
    kernel = engine.synthesize_vector_op("test_vec_add", "add")
    assert kernel.name == "test_vec_add"
    assert kernel.bytecode is not None
    assert len(kernel.bytecode) > 0
    assert "VADD" in kernel.source_code

    relu_kernel = engine.synthesize_activation_kernel("test_relu", "relu")
    assert relu_kernel.name == "test_relu"
    assert len(relu_kernel.bytecode) > 0


def test_kernel_evaluator():
    engine = SelfCodingEngine()
    kernel = engine.synthesize_vector_op("test_eval_add", "fadd")
    evaluator = KernelEvaluator()
    report = evaluator.evaluate_kernel(kernel, num_warps=1)
    assert report.valid is True
    assert report.cycles_elapsed > 0
    assert report.instructions_retired > 0


def test_dashboard_backend_services():
    backend = DashboardBackend()
    telem = backend.get_system_telemetry()
    assert "performance_counters" in telem
    assert telem["warp_size"] == 32

    # Test LLM generation on dashboard backend
    llm_res = backend.generate_llm("test prompt", max_tokens=4)
    assert "output_text" in llm_res
    assert llm_res["tokens_generated"] == 4

    # Test self-coding synthesis via backend
    sc_res = backend.trigger_self_coding("dashboard_add", "fadd")
    assert sc_res["valid"] is True

    # Test AGI step via backend
    agi_res = backend.trigger_agi_step("run test task")
    assert agi_res["step_num"] >= 1
    assert "thought" in agi_res


def test_dashboard_backend_enables_embeddings_only_with_complete_settings(monkeypatch, tmp_path):
    for name in (
        "ZGPU_OPENAI_API_URL",
        "ZGPU_OPENAI_API_KEY",
        "ZGPU_KNOWLEDGE_API_URL",
        "ZGPU_KNOWLEDGE_API_TOKEN",
        "ZGPU_KNOWLEDGE_BASE_URL",
        "ZGPU_KNOWLEDGE_BASE_API_KEY",
        "ZGPU_ENGINEERING_API_URL",
        "ZGPU_ENGINEERING_API_TOKEN",
        "ZGPU_LLAMA_SERVER_PATH",
        "ZGPU_LLAMA_MODEL_PATH",
        "ZGPU_EMBEDDING_API_URL",
        "ZGPU_EMBEDDING_MODEL",
        "ZGPU_EMBEDDING_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ZGPU_EMBEDDING_API_URL", "http://127.0.0.1:11434/v1")
    monkeypatch.setenv("ZGPU_EMBEDDING_MODEL", "local-embed-model")
    monkeypatch.setenv("ZGPU_EMBEDDING_API_KEY", "local-test-key")
    monkeypatch.setenv("ZGPU_KNOWLEDGE_DB_PATH", str(tmp_path / "knowledge.sqlite3"))

    backend = DashboardBackend()

    assert backend.local_knowledge.embedding_provider.base_url == "http://127.0.0.1:11434/v1/embeddings"
    assert backend.local_knowledge.embedding_provider.model == "local-embed-model"
    assert backend.local_knowledge.retrieval_status()["retrieval"] == "lexical"

    monkeypatch.delenv("ZGPU_EMBEDDING_MODEL")
    with pytest.raises(ValueError, match="must be configured together"):
        DashboardBackend()


def test_dashboard_zisa_studio_uses_canonical_assembler_words():
    source = "GET.TID R0\nVADD R1, R1, R2\nHALT"
    handler = _post_handler("/api/isa/assemble", json.dumps({"source": source}).encode())
    handler.do_POST()

    assert handler.send_response.call_args.args[0] == 200
    result = json.loads(b"".join(call.args[0] for call in handler.wfile.write.call_args_list))["data"]
    assert result["target"] == "zISA-32"
    assert result["execution"] == "not-run"
    assert result["instruction_count"] == 3
    assert result["byte_count"] == 12
    assert result["word_hex"][0] == f"0x{Assembler.assemble(source)[0]:08X}"
    assert result["bytecode_le_hex"][0] == Assembler.assemble(source)[0].to_bytes(4, "little").hex()


@pytest.mark.parametrize(
    ("expression", "instruction"),
    [("a + b", "VFADD"), ("a - b", "VFSUB"), ("a * b", "VFMUL"), ("b + a", "VFADD")],
)
def test_dashboard_compiles_restricted_expression_through_zisa(expression, instruction):
    handler = _post_handler(
        "/api/isa/compile-expression",
        json.dumps({"expression": expression}).encode(),
    )
    handler.do_POST()

    response = json.loads(b"".join(call.args[0] for call in handler.wfile.write.call_args_list))
    program = response["data"]
    assert handler.send_response.call_args.args[0] == 200
    assert program["target"] == "zISA-32"
    assert program["execution"] == "not-run"
    assert instruction in program["assembly"]
    assert program["instruction_count"] == len(Assembler.assemble(program["assembly"]))


@pytest.mark.parametrize(
    "expression",
    ["__import__('os').system('id')", "a ** b", "a + c", "a + b + a", "a + b #\nHALT", ""],
)
def test_dashboard_expression_compiler_rejects_unsupported_python(expression):
    handler = _post_handler(
        "/api/isa/compile-expression",
        json.dumps({"expression": expression}).encode(),
    )
    handler.do_POST()

    assert handler.send_response.call_args.args[0] == 400


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("a + b", [float(index + 1) for index in range(32)]),
        ("a - b", [float(index - 1) for index in range(32)]),
        ("b - a", [float(1 - index) for index in range(32)]),
        ("a * b", [float(index) for index in range(32)]),
    ],
)
def test_dashboard_compiles_and_simulates_elementwise_fp32(expression, expected):
    handler = _post_handler(
        "/api/isa/run-expression",
        json.dumps({"expression": expression, "a": list(range(32)), "b": [1] * 32}).encode(),
    )
    handler.do_POST()

    response = json.loads(b"".join(call.args[0] for call in handler.wfile.write.call_args_list))
    assert handler.send_response.call_args.args[0] == 200
    assert response["data"]["target"] == "zGPU-SIMT-Simulator"
    assert response["data"]["execution"] == "simulated"
    assert response["data"]["result"] == expected


@pytest.mark.parametrize(
    ("payload", "status"),
    [
        ({"expression": "a + b", "a": [1] * 31, "b": [1] * 32}, 400),
        ({"expression": "a + b", "a": [float("nan")] * 32, "b": [1] * 32}, 400),
        ({"expression": "a + b", "a": [3.4e38] * 32, "b": [3.4e38] * 32}, 422),
    ],
)
def test_dashboard_expression_simulation_rejects_invalid_or_nonfinite_data(payload, status):
    handler = _post_handler("/api/isa/run-expression", json.dumps(payload).encode())
    handler.do_POST()
    assert handler.send_response.call_args.args[0] == status


def test_dashboard_zisa_studio_rejects_malformed_and_oversized_source():
    malformed = _post_handler("/api/isa/assemble", b'{"source":"VADD"}')
    malformed.do_POST()
    assert malformed.send_response.call_args.args[0] == 400

    oversized = _post_handler("/api/isa/assemble", json.dumps({"source": " " * 65_537}).encode())
    oversized.do_POST()
    assert oversized.send_response.call_args.args[0] == 413


def test_dashboard_zisa_opcode_listing_comes_from_existing_assembler():
    handler = _get_handler("/api/isa/opcodes")
    handler.headers = Message()
    handler.do_GET()

    response = json.loads(b"".join(call.args[0] for call in handler.wfile.write.call_args_list))
    assert response["target"] == "zISA-32"
    assert response["instruction_width_bits"] == 32
    assert {item["mnemonic"] for item in response["data"]} >= {"VADD", "MMA.SYNC", "HALT"}


def test_dashboard_http_handler_endpoints():
    handler = DashboardHTTPHandler.__new__(DashboardHTTPHandler)
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler.wfile = MagicMock()

    # Test GET /api/telemetry
    handler.path = "/api/telemetry"
    handler.do_GET()

    written_data = b"".join(call.args[0] for call in handler.wfile.write.call_args_list)
    telem = json.loads(written_data.decode("utf-8"))
    assert "device_name" in telem
    assert telem["device_name"] == "zGPU Software SIMT Simulator"


def test_dashboard_serves_standalone_ui_with_security_headers():
    handler = DashboardHTTPHandler.__new__(DashboardHTTPHandler)
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler.wfile = MagicMock()
    handler.path = "/"

    handler.do_GET()

    response = b"".join(call.args[0] for call in handler.wfile.write.call_args_list).decode()
    assert "zGPU Console" in response
    assert "Software simulator" in response
    assert "AI workspace" in response
    assert "Prompt library" in response
    assert "Documents &amp; search" in response
    assert "{{input}}" in response
    assert "zGPU Assistant" in response
    assert 'id="chat-project"' in response
    assert "New project" in response
    assert "Open WebUI" not in response
    assert "Onyx" not in response
    assert "zcoder" not in response
    assert "zknowbase" not in response
    assert "CONNECTED KNOWLEDGE" in response
    assert "dashboard.css" in response
    headers = {call.args[0]: call.args[1] for call in handler.send_header.call_args_list}
    assert "default-src 'self'" in headers["Content-Security-Policy"]
    assert headers["X-Content-Type-Options"] == "nosniff"


def test_dashboard_serves_frontend_assets():
    for path, expected_type, marker in (
        ("/dashboard.css", "text/css; charset=utf-8", ".chat-panel"),
        ("/dashboard.js", "text/javascript; charset=utf-8", "searchConversations"),
    ):
        handler = DashboardHTTPHandler.__new__(DashboardHTTPHandler)
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()
        handler.wfile = MagicMock()
        handler.path = path

        handler.do_GET()

        body = b"".join(call.args[0] for call in handler.wfile.write.call_args_list).decode()
        assert marker in body
        assert ("Content-Type", expected_type) in [call.args for call in handler.send_header.call_args_list]


def _post_handler(path, body: bytes, length: str | None = None):
    handler = DashboardHTTPHandler.__new__(DashboardHTTPHandler)
    handler.path = path
    handler.headers = Message()
    handler.headers["Content-Length"] = length if length is not None else str(len(body))
    handler.headers["X-zGPU-Request"] = "dashboard-ui"
    handler.rfile = io.BytesIO(body)
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler.wfile = MagicMock()
    return handler


def _get_handler(path: str):
    handler = DashboardHTTPHandler.__new__(DashboardHTTPHandler)
    handler.path = path
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler.send_error = MagicMock()
    handler.wfile = MagicMock()
    return handler


def test_engineering_jobs_route_is_optional_read_only_and_bounded(monkeypatch):
    status_handler = _get_handler("/api/engineering/status")
    monkeypatch.setattr(dashboard_server.backend, "engineering_jobs", None)
    status_handler.do_GET()
    body = b"".join(call.args[0] for call in status_handler.wfile.write.call_args_list)
    assert json.loads(body) == {"configured": False}

    missing_handler = _get_handler("/api/engineering/jobs")
    missing_handler.do_GET()
    assert missing_handler.send_response.call_args.args[0] == 503

    client = MagicMock()
    client.list_jobs.return_value = {
        "data": [
            {
                "id": "job-1",
                "task": "x" * 800,
                "status": "running",
                "runtime": "direct",
                "model": "local",
                "created_at": "2026-10-23T00:00:00Z",
                "secret_field": "must not be forwarded",
            }
        ],
        "pagination": {"limit": 10, "offset": 5, "total": 6, "has_more": False},
    }
    monkeypatch.setattr(dashboard_server.backend, "engineering_jobs", client)
    handler = _get_handler("/api/engineering/jobs?limit=10&offset=5")
    handler.do_GET()
    payload = json.loads(b"".join(call.args[0] for call in handler.wfile.write.call_args_list))
    assert client.list_jobs.call_args.kwargs == {"limit": 10, "offset": 5}
    assert payload["data"][0]["task"] == "x" * 500
    assert "secret_field" not in payload["data"][0]
    assert payload["pagination"] == {"limit": 10, "offset": 5, "total": 6, "has_more": False}

    client.get_job.return_value = {
        "id": "a/b",
        "task": "inspect kernel",
        "status": "completed",
        "runtime": "direct",
        "model": "local",
        "created_at": "2026-10-23T00:00:00Z",
        "secret_field": "must not be forwarded",
    }
    detail = _get_handler("/api/engineering/jobs/a%2Fb")
    detail.do_GET()
    detail_payload = json.loads(b"".join(call.args[0] for call in detail.wfile.write.call_args_list))
    client.get_job.assert_called_once_with("a/b")
    assert detail_payload["data"]["status"] == "completed"
    assert "secret_field" not in detail_payload["data"]

    invalid = _get_handler("/api/engineering/jobs?limit=10&limit=20")
    invalid.do_GET()
    assert invalid.send_response.call_args.args[0] == 400


def test_engineering_entitlements_are_read_only_and_allowlisted(monkeypatch):
    service = MagicMock()
    service.get_entitlements.return_value = {
        "organization_id": "private-org-id",
        "request_id": "private-request-id",
        "entitlements": {
            "version": "2026.1",
            "max_projects": 5,
            "max_repositories": 10,
            "monthly_budget_usd": 100.0,
            "concurrent_jobs": 3,
            "managed_agents": True,
            "multiagent_orchestration": False,
            "scim_enabled": False,
            "sso_oidc_enabled": True,
            "secret": "must not be forwarded",
            "audit_export_enabled": "invalid type",
        },
    }
    monkeypatch.setattr(dashboard_server.backend, "engineering_jobs", service)

    handler = _get_handler("/api/engineering/entitlements")
    handler.do_GET()

    payload = json.loads(b"".join(call.args[0] for call in handler.wfile.write.call_args_list))
    assert payload["data"] == {
        "version": "2026.1",
        "max_projects": 5,
        "max_repositories": 10,
        "monthly_budget_usd": 100.0,
        "concurrent_jobs": 3,
        "managed_agents": True,
        "multiagent_orchestration": False,
        "scim_enabled": False,
        "sso_oidc_enabled": True,
    }
    assert "private-org-id" not in str(payload)
    service.get_entitlements.assert_called_once_with()

    invalid = _get_handler("/api/engineering/entitlements?debug=1")
    invalid.do_GET()
    assert invalid.send_response.call_args.args[0] == 400

    service.get_entitlements.return_value = {"entitlements": []}
    malformed = _get_handler("/api/engineering/entitlements")
    malformed.do_GET()
    assert malformed.send_response.call_args.args[0] == 502


def test_engineering_job_submission_is_explicit_bounded_and_idempotent(monkeypatch):
    monkeypatch.setattr(dashboard_server.backend, "engineering_jobs", MagicMock())
    submit = MagicMock(
        return_value={"id": "job-2", "status": "ready", "task": "run checks", "secret_field": "omit"}
    )
    monkeypatch.setattr(dashboard_server.backend, "submit_engineering_job", submit)
    handler = _post_handler(
        "/api/engineering/jobs",
        json.dumps({"task": "run checks", "runtime": "direct", "budget_usd": 2.5}).encode(),
    )
    handler.headers["Idempotency-Key"] = "request-2"
    handler.do_POST()
    result = json.loads(b"".join(call.args[0] for call in handler.wfile.write.call_args_list))
    assert handler.send_response.call_args.args[0] == 201
    assert result["data"]["id"] == "job-2"
    assert "secret_field" not in result["data"]
    submit.assert_called_once_with(
        "run checks", runtime="direct", model=None, budget_usd=2.5, idempotency_key="request-2"
    )

    no_budget = _post_handler(
        "/api/engineering/jobs",
        json.dumps({"task": "run checks", "runtime": "direct", "budget_usd": 0}).encode(),
    )
    monkeypatch.undo()
    monkeypatch.setattr(dashboard_server.backend, "engineering_jobs", MagicMock())
    no_budget.do_POST()
    assert no_budget.send_response.call_args.args[0] == 400
    assert dashboard_server.backend.engineering_jobs.submit_job.call_count == 0


def test_engineering_job_cancellation_requires_marker_and_projects_safe_response(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(dashboard_server.backend, "engineering_jobs", client)
    cancel = MagicMock(
        return_value={
            "id": "a/b",
            "task": "run checks",
            "status": "CANCELLED",
            "runtime": "direct",
            "secret_field": "must not be forwarded",
        }
    )
    monkeypatch.setattr(dashboard_server.backend, "cancel_engineering_job", cancel)

    handler = _get_handler("/api/engineering/jobs/a%2Fb")
    handler.headers = Message()
    handler.headers["X-zGPU-Request"] = "dashboard-ui"
    handler.headers["Idempotency-Key"] = "cancel-1"
    handler.do_DELETE()

    cancel.assert_called_once_with("a/b", idempotency_key="cancel-1")
    payload = json.loads(b"".join(call.args[0] for call in handler.wfile.write.call_args_list))
    assert handler.send_response.call_args.args[0] == 200
    assert payload["data"]["status"] == "CANCELLED"
    assert "secret_field" not in payload["data"]

    denied = _get_handler("/api/engineering/jobs/job-1")
    denied.headers = Message()
    denied.do_DELETE()
    assert denied.send_response.call_args.args[0] == 403
    cancel.assert_called_once()


def test_dashboard_local_knowledge_api_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(
        dashboard_server.backend, "local_knowledge", LocalKnowledgeStore(tmp_path / "knowledge.sqlite3")
    )
    monkeypatch.setattr(
        dashboard_server.backend, "conversations", ConversationStore(tmp_path / "conversations.sqlite3")
    )

    create_project = _post_handler("/api/projects", b'{"name":"Kernel project"}')
    create_project.do_POST()
    project = json.loads(b"".join(call.args[0] for call in create_project.wfile.write.call_args_list))["data"]

    create = _post_handler(
        "/api/knowledge/library/documents",
        json.dumps(
            {
                "title": "ISA guide",
                "content": "zISA instructions are fixed width 32-bit words.",
                "project_id": project["id"],
            }
        ).encode(),
    )
    create.do_POST()
    assert create.send_response.call_args.args[0] == 201
    saved = json.loads(b"".join(call.args[0] for call in create.wfile.write.call_args_list))["data"]
    assert saved["project_id"] == project["id"]

    listing = _get_handler("/api/knowledge/library/documents")
    listing.do_GET()
    listed = json.loads(b"".join(call.args[0] for call in listing.wfile.write.call_args_list))["data"]
    assert listed[0]["id"] == saved["id"]
    assert listed[0]["project_id"] == project["id"]
    assert "content" not in listed[0]

    general_listing = _get_handler("/api/knowledge/library/documents?project_id=")
    general_listing.do_GET()
    assert (
        json.loads(b"".join(call.args[0] for call in general_listing.wfile.write.call_args_list))["data"]
        == []
    )

    search = _post_handler(
        "/api/knowledge/library/search",
        json.dumps({"query": "fixed width", "limit": 5, "project_id": project["id"]}).encode(),
    )
    search.do_POST()
    results = json.loads(b"".join(call.args[0] for call in search.wfile.write.call_args_list))
    assert results["retrieval"] == "lexical"
    assert results["data"][0]["id"] == saved["id"]

    invalid_project = _post_handler(
        "/api/knowledge/library/search", b'{"query":"fixed width","project_id":"' + b"0" * 32 + b'"}'
    )
    invalid_project.do_POST()
    assert invalid_project.send_response.call_args.args[0] == 404

    invalid_search = _post_handler(
        "/api/knowledge/library/search", json.dumps({"query": "fixed width", "unexpected": True}).encode()
    )
    invalid_search.do_POST()
    assert invalid_search.send_response.call_args.args[0] == 400

    delete = _get_handler(f"/api/knowledge/library/documents/{saved['id']}")
    delete.command = "DELETE"
    delete.headers = Message()
    delete.headers["X-zGPU-Request"] = "dashboard-ui"
    delete.do_DELETE()
    assert json.loads(b"".join(call.args[0] for call in delete.wfile.write.call_args_list)) == {
        "deleted": True
    }

    invalid = _post_handler("/api/knowledge/library/documents", b'{"title":"bad","content":""}')
    invalid.do_POST()
    assert invalid.send_response.call_args.args[0] == 400


def test_dashboard_reports_lexical_and_hybrid_retrieval_status(monkeypatch, tmp_path):
    lexical_store = LocalKnowledgeStore(tmp_path / "lexical.sqlite3")
    monkeypatch.setattr(dashboard_server.backend, "local_knowledge", lexical_store)
    lexical = _get_handler("/api/knowledge/status")
    lexical.headers = Message()
    lexical.do_GET()
    lexical_status = json.loads(b"".join(call.args[0] for call in lexical.wfile.write.call_args_list))["data"]
    assert lexical_status["retrieval"] == "lexical"
    assert lexical_status["embedding_configured"] is False

    provider = SimpleNamespace(model="api-test-embeddings", embed=lambda _text: [1.0, 0.0])
    hybrid_store = LocalKnowledgeStore(tmp_path / "hybrid.sqlite3", embedding_provider=provider)
    hybrid_store.add_document("Cat source", "A cat sleeps.")
    monkeypatch.setattr(dashboard_server.backend, "local_knowledge", hybrid_store)
    hybrid = _get_handler("/api/knowledge/status")
    hybrid.headers = Message()
    hybrid.do_GET()
    hybrid_status = json.loads(b"".join(call.args[0] for call in hybrid.wfile.write.call_args_list))["data"]
    assert hybrid_status["retrieval"] == "hybrid"
    assert hybrid_status["embedding_model"] == "api-test-embeddings"
    assert hybrid_status["indexed_document_count"] == 1
    assert hybrid_status["pending_document_count"] == 0

    reindex_store = LocalKnowledgeStore(tmp_path / "reindex.sqlite3")
    reindex_store.add_document("Legacy source", "A cat sleeps.")
    reindex_store.embedding_provider = provider
    monkeypatch.setattr(dashboard_server.backend, "local_knowledge", reindex_store)
    reindex = _post_handler("/api/knowledge/reindex", b'{"limit":5,"project_id":"*"}')
    reindex.do_POST()
    reindex_payload = json.loads(b"".join(call.args[0] for call in reindex.wfile.write.call_args_list))
    assert reindex.send_response.call_args.args[0] == 200
    assert reindex_payload["data"]["indexed_count"] == 1
    assert reindex_payload["data"]["complete"] is True

    oversized_reindex = _post_handler("/api/knowledge/reindex", b'{"limit":6}')
    oversized_reindex.do_POST()
    assert oversized_reindex.send_response.call_args.args[0] == 400

    search = _post_handler("/api/knowledge/library/search", b'{"query":"cat","limit":5}')
    search.do_POST()
    search_payload = json.loads(b"".join(call.args[0] for call in search.wfile.write.call_args_list))
    assert search_payload["retrieval"] == "hybrid"


def test_dashboard_search_merges_connected_and_local_knowledge(monkeypatch, tmp_path):
    local = LocalKnowledgeStore(tmp_path / "knowledge.sqlite3")
    local.add_document("Local zISA guide", "The kernel uses a 32-bit instruction word.")
    remote = MagicMock()
    remote.search.return_value = [
        {"id": "remote-doc", "title": "Remote guide", "excerpt": "The kernel uses a SIMT warp.", "score": 0.8}
    ]
    monkeypatch.setattr(dashboard_server.backend, "local_knowledge", local)
    monkeypatch.setattr(dashboard_server.backend, "knowledge_base", remote)

    handler = _post_handler("/api/knowledge/library/search", b'{"query":"kernel","limit":5,"project_id":"*"}')
    handler.do_POST()
    payload = json.loads(b"".join(call.args[0] for call in handler.wfile.write.call_args_list))
    assert handler.send_response.call_args.args[0] == 200
    assert [item["source"] for item in payload["data"]] == ["local", "connected"]
    assert payload["data"][1]["title"] == "Remote guide"
    assert payload["connected"] is True
    assert payload["warning"] is None
    remote.search.assert_called_once_with("kernel", top_k=5)

    remote.search.side_effect = dashboard_server.KnowledgeBaseError(503, "UPSTREAM_UNAVAILABLE", "offline")
    fallback = _post_handler(
        "/api/knowledge/library/search", b'{"query":"kernel","limit":5,"project_id":"*"}'
    )
    fallback.do_POST()
    fallback_payload = json.loads(b"".join(call.args[0] for call in fallback.wfile.write.call_args_list))
    assert fallback.send_response.call_args.args[0] == 200
    assert fallback_payload["data"][0]["source"] == "local"
    assert fallback_payload["warning"]


def test_dashboard_connected_knowledge_routes_are_optional_and_bounded(monkeypatch):
    monkeypatch.setattr(dashboard_server.backend, "knowledge_base", None)
    status = _get_handler("/api/knowledge/base/status")
    status.do_GET()
    assert json.loads(b"".join(call.args[0] for call in status.wfile.write.call_args_list)) == {
        "configured": False
    }

    absent = _get_handler("/api/knowledge/base/documents")
    absent.do_GET()
    assert absent.send_response.call_args.args[0] == 503

    connected = MagicMock()
    connected.health.return_value = {
        "status": "ok",
        "qdrant": "ok",
        "metadata_store": "ok",
        "scanner": "validation-only",
    }
    connected.list_documents.return_value = [{"id": "doc-1", "name": "guide.md", "status": "completed"}]
    connected.list_ingestion_jobs.return_value = [{"id": "job-1", "document_id": "doc-1", "status": "queued"}]
    connected.get_ingestion_job.return_value = {"id": "job-1", "document_id": "doc-1", "status": "queued"}
    monkeypatch.setattr(dashboard_server.backend, "knowledge_base", connected)

    health = _get_handler("/api/knowledge/base/status")
    health.do_GET()
    assert (
        json.loads(b"".join(call.args[0] for call in health.wfile.write.call_args_list))["available"] is True
    )

    documents = _get_handler("/api/knowledge/base/documents")
    documents.do_GET()
    assert (
        json.loads(b"".join(call.args[0] for call in documents.wfile.write.call_args_list))["data"][0]["id"]
        == "doc-1"
    )

    jobs = _get_handler("/api/knowledge/base/jobs?limit=10")
    jobs.do_GET()
    connected.list_ingestion_jobs.assert_called_once_with(limit=10)

    detail = _get_handler("/api/knowledge/base/jobs/job-1")
    detail.do_GET()
    connected.get_ingestion_job.assert_called_once_with("job-1")

    invalid = _get_handler("/api/knowledge/base/jobs?limit=10&limit=20")
    invalid.do_GET()
    assert invalid.send_response.call_args.args[0] == 400


def test_dashboard_connected_knowledge_upload_is_explicit_and_bounded(monkeypatch):
    connected = MagicMock()
    connected.ingest_file.return_value = {
        "document": {"id": "doc-1", "name": "guide.md"},
        "job": {"id": "job-1", "status": "queued"},
    }
    monkeypatch.setattr(dashboard_server.backend, "knowledge_base", connected)
    payload = {"filename": "guide.md", "file_base64": base64.b64encode(b"# zGPU").decode("ascii")}
    handler = _post_handler("/api/knowledge/base/ingest", json.dumps(payload).encode())
    handler.do_POST()
    assert handler.send_response.call_args.args[0] == 202
    assert connected.ingest_file.call_args.args == ("guide.md", b"# zGPU")

    invalid = _post_handler("/api/knowledge/base/ingest", b'{"filename":"../secret.md","file_base64":"eA=="}')
    invalid.do_POST()
    assert invalid.send_response.call_args.args[0] == 400


def test_dashboard_connected_knowledge_job_cancellation_requires_marker(monkeypatch):
    connected = MagicMock()
    monkeypatch.setattr(dashboard_server.backend, "knowledge_base", connected)
    handler = DashboardHTTPHandler.__new__(DashboardHTTPHandler)
    handler.path = "/api/knowledge/base/jobs/job-1"
    handler.headers = Message()
    handler.headers["Content-Length"] = "0"
    handler.headers["X-zGPU-Request"] = "dashboard-ui"
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler.wfile = MagicMock()

    handler.do_DELETE()

    connected.cancel_ingestion_job.assert_called_once_with("job-1")
    assert json.loads(b"".join(call.args[0] for call in handler.wfile.write.call_args_list)) == {
        "cancelled": True
    }


def test_dashboard_runs_bounded_zisa_program_on_simulator():
    handler = _post_handler(
        "/api/isa/simulate",
        json.dumps(
            {
                "source": "VADD R3, R1, R2\nHALT",
                "inputs": {"R1": list(range(32)), "R2": 1},
                "output_registers": [3],
                "max_cycles": 10,
            }
        ).encode(),
    )
    handler.do_POST()

    payload = json.loads(b"".join(call.args[0] for call in handler.wfile.write.call_args_list))
    assert handler.send_response.call_args.args[0] == 200
    assert payload["data"]["target"] == "zGPU-SIMT-Simulator"
    assert payload["data"]["execution"] == "simulated"
    assert payload["data"]["performance_counters"]["total_cycles"] == 2
    assert payload["data"]["registers"]["R3"] == list(range(1, 33))

    looping = _post_handler(
        "/api/isa/simulate",
        json.dumps({"source": "LOOP:\nBRA LOOP", "max_cycles": 3, "output_registers": [3]}).encode(),
    )
    looping.do_POST()
    assert looping.send_response.call_args.args[0] == 408

    invalid = _post_handler("/api/isa/simulate", b'{"source":"HALT","unexpected":true}')
    invalid.do_POST()
    assert invalid.send_response.call_args.args[0] == 400


def test_chat_stream_disconnect_stops_generation_at_the_next_token(monkeypatch):
    state = {"generated_after_disconnect": False}

    class DisconnectAfterFirstEvent:
        writes = 0

        def write(self, _data):
            self.writes += 1
            if self.writes > 1:
                raise BrokenPipeError("client closed stream")

        def flush(self):
            return None

    def create_completion(_payload, *, event_callback):
        event_callback({"choices": [{"delta": {"role": "assistant"}}]})
        event_callback({"choices": [{"delta": {"content": "token"}}]})
        state["generated_after_disconnect"] = True

    monkeypatch.setattr(
        dashboard_server.backend,
        "chat_api",
        SimpleNamespace(create_completion=create_completion),
    )
    handler = DashboardHTTPHandler.__new__(DashboardHTTPHandler)
    handler.wfile = DisconnectAfterFirstEvent()
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()

    handler._stream_chat_completion({})

    assert state["generated_after_disconnect"] is False


def test_dashboard_local_knowledge_uploads_text_document(monkeypatch, tmp_path):
    monkeypatch.setattr(
        dashboard_server.backend, "local_knowledge", LocalKnowledgeStore(tmp_path / "knowledge.sqlite3")
    )
    payload = {
        "filename": "manual.md",
        "file_base64": base64.b64encode(b"# Local guide\n\nzISA uses 32-bit words.").decode("ascii"),
    }
    handler = _post_handler("/api/knowledge/library/documents", json.dumps(payload).encode())
    handler.do_POST()

    assert handler.send_response.call_args.args[0] == 201
    saved = json.loads(b"".join(call.args[0] for call in handler.wfile.write.call_args_list))["data"]
    assert saved["title"] == "manual.md"
    assert LocalKnowledgeStore(tmp_path / "knowledge.sqlite3").search("32-bit words")[0]["id"] == saved["id"]


def test_dashboard_local_knowledge_uploads_docx_document(monkeypatch, tmp_path):
    store = LocalKnowledgeStore(tmp_path / "knowledge.sqlite3")
    monkeypatch.setattr(dashboard_server.backend, "local_knowledge", store)
    document = io.BytesIO()
    xml = (
        b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        b"<w:body><w:p><w:r><w:t>SIMT warp execution contract</w:t></w:r></w:p></w:body></w:document>"
    )
    with ZipFile(document, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", xml)
    payload = {
        "filename": "simt.docx",
        "file_base64": base64.b64encode(document.getvalue()).decode("ascii"),
    }
    handler = _post_handler("/api/knowledge/library/documents", json.dumps(payload).encode())
    handler.do_POST()

    assert handler.send_response.call_args.args[0] == 201
    saved = json.loads(b"".join(call.args[0] for call in handler.wfile.write.call_args_list))["data"]
    assert saved["title"] == "simt.docx"
    assert store.search("SIMT warp")[0]["id"] == saved["id"]


def test_dashboard_local_knowledge_upload_rejects_invalid_base64(monkeypatch, tmp_path):
    monkeypatch.setattr(
        dashboard_server.backend, "local_knowledge", LocalKnowledgeStore(tmp_path / "knowledge.sqlite3")
    )
    handler = _post_handler(
        "/api/knowledge/library/documents", b'{"filename":"notes.txt","file_base64":"%%%"}'
    )
    handler.do_POST()

    assert handler.send_response.call_args.args[0] == 400


def test_dashboard_conversation_api_roundtrip_and_request_marker(monkeypatch, tmp_path):
    store = ConversationStore(tmp_path / "conversations.sqlite3")
    monkeypatch.setattr(dashboard_server.backend, "conversations", store)

    create = _post_handler("/api/conversations", b'{"model":"zgpu-thai"}')
    create.do_POST()
    assert create.send_response.call_args.args[0] == 201
    conversation = json.loads(b"".join(call.args[0] for call in create.wfile.write.call_args_list))["data"]

    invalid_create = _post_handler("/api/conversations?unexpected=true", b"{}")
    invalid_create.do_POST()
    assert invalid_create.send_response.call_args.args[0] == 400

    append = _post_handler(
        f"/api/conversations/{conversation['id']}/messages",
        b'{"model":"zgpu-thai","messages":[{"role":"user","content":"Review the kernel"},{"role":"assistant","content":"I found the bounds issue."}]}',
    )
    append.do_POST()
    assert append.send_response.call_args.args[0] == 200

    listing = _get_handler("/api/conversations?limit=20")
    listing.do_GET()
    listed = json.loads(b"".join(call.args[0] for call in listing.wfile.write.call_args_list))["data"]
    assert listed[0]["title"] == "Review the kernel"
    assert listed[0]["message_count"] == 2
    assert listed[0]["model"] == "zgpu-thai"

    search = _get_handler("/api/conversations?limit=20&search=kernel")
    search.do_GET()
    matching = json.loads(b"".join(call.args[0] for call in search.wfile.write.call_args_list))["data"]
    assert [item["id"] for item in matching] == [conversation["id"]]

    invalid_search = _get_handler("/api/conversations?unsupported=1")
    invalid_search.do_GET()
    assert invalid_search.send_response.call_args.args[0] == 400

    rename = _post_handler(f"/api/conversations/{conversation['id']}/title", b'{"title":"Kernel review"}')
    rename.do_POST()
    renamed = json.loads(b"".join(call.args[0] for call in rename.wfile.write.call_args_list))["data"]
    assert renamed["title"] == "Kernel review"
    assert len(renamed["messages"]) == 2

    invalid_rename = _post_handler(f"/api/conversations/{conversation['id']}/title", b'{"title":"  "}')
    invalid_rename.do_POST()
    assert invalid_rename.send_response.call_args.args[0] == 400

    detail = _get_handler(f"/api/conversations/{conversation['id']}")
    detail.do_GET()
    result = json.loads(b"".join(call.args[0] for call in detail.wfile.write.call_args_list))["data"]
    assert result["messages"][1]["content"] == "I found the bounds issue."

    denied = _post_handler("/api/conversations", b"{}")
    del denied.headers["X-zGPU-Request"]
    denied.do_POST()
    assert denied.send_response.call_args.args[0] == 403

    delete = _get_handler(f"/api/conversations/{conversation['id']}")
    delete.command = "DELETE"
    delete.headers = Message()
    delete.headers["X-zGPU-Request"] = "dashboard-ui"
    delete.do_DELETE()
    assert json.loads(b"".join(call.args[0] for call in delete.wfile.write.call_args_list)) == {
        "deleted": True
    }


def test_dashboard_assistant_profile_api_and_conversation_assignment(monkeypatch, tmp_path):
    profiles = AssistantProfiles(tmp_path / "assistants.sqlite3")
    conversations = ConversationStore(tmp_path / "conversations.sqlite3")
    monkeypatch.setattr(dashboard_server.backend, "assistants", profiles)
    monkeypatch.setattr(dashboard_server.backend, "conversations", conversations)

    listing = _get_handler("/api/assistants")
    listing.do_GET()
    assert any(
        profile["id"] == "builtin_precise"
        for profile in json.loads(b"".join(call.args[0] for call in listing.wfile.write.call_args_list))[
            "data"
        ]
    )

    create = _post_handler(
        "/api/assistants",
        b'{"name":"Kernel review","description":"Review kernels","system_prompt":"Check bounds."}',
    )
    create.do_POST()
    assert create.send_response.call_args.args[0] == 201
    profile = json.loads(b"".join(call.args[0] for call in create.wfile.write.call_args_list))["data"]

    conversation_create = _post_handler(
        "/api/conversations", json.dumps({"assistant_id": profile["id"]}).encode()
    )
    conversation_create.do_POST()
    conversation = json.loads(
        b"".join(call.args[0] for call in conversation_create.wfile.write.call_args_list)
    )["data"]
    assert conversation["assistant_id"] == profile["id"]

    update = _post_handler(
        f"/api/conversations/{conversation['id']}/assistant", b'{"assistant_id":"builtin_teaching"}'
    )
    update.do_POST()
    assert (
        json.loads(b"".join(call.args[0] for call in update.wfile.write.call_args_list))["data"][
            "assistant_id"
        ]
        == "builtin_teaching"
    )

    reassign = _post_handler(
        f"/api/conversations/{conversation['id']}/assistant",
        json.dumps({"assistant_id": profile["id"]}).encode(),
    )
    reassign.do_POST()

    delete = _get_handler(f"/api/assistants/{profile['id']}")
    delete.command = "DELETE"
    delete.headers = Message()
    delete.headers["Content-Length"] = "0"
    delete.headers["X-zGPU-Request"] = "dashboard-ui"
    delete.do_DELETE()
    assert json.loads(b"".join(call.args[0] for call in delete.wfile.write.call_args_list)) == {
        "deleted": True
    }
    assert conversations.get(conversation["id"])["assistant_id"] is None


def test_dashboard_chat_projects_api_roundtrip(monkeypatch, tmp_path):
    store = ConversationStore(tmp_path / "conversations.sqlite3")
    monkeypatch.setattr(dashboard_server.backend, "conversations", store)
    knowledge = LocalKnowledgeStore(tmp_path / "knowledge.sqlite3")
    monkeypatch.setattr(dashboard_server.backend, "local_knowledge", knowledge)
    notes = WorkspaceNotes(tmp_path / "notes.sqlite3")
    monkeypatch.setattr(dashboard_server.backend, "notes", notes)

    create_project = _post_handler("/api/projects", b'{"name":"Kernel work"}')
    create_project.do_POST()
    assert create_project.send_response.call_args.args[0] == 201
    project = json.loads(b"".join(call.args[0] for call in create_project.wfile.write.call_args_list))["data"]

    create_chat = _post_handler(
        "/api/conversations", json.dumps({"model": "zgpu-code", "project_id": project["id"]}).encode()
    )
    create_chat.do_POST()
    conversation = json.loads(b"".join(call.args[0] for call in create_chat.wfile.write.call_args_list))[
        "data"
    ]
    assert conversation["project_id"] == project["id"]

    source = knowledge.add_document(
        "Project source", "SIMT project source remains in the general library.", project_id=project["id"]
    )
    project_note = notes.create(
        "Kernel invariant", "Preserve the project kernel launch contract.", project["id"]
    )

    listing = _get_handler("/api/projects")
    listing.do_GET()
    projects = json.loads(b"".join(call.args[0] for call in listing.wfile.write.call_args_list))["data"]
    assert projects[0]["conversation_count"] == 1

    scoped = _get_handler(f"/api/conversations?limit=20&project_id={project['id']}")
    scoped.do_GET()
    scoped_chats = json.loads(b"".join(call.args[0] for call in scoped.wfile.write.call_args_list))["data"]
    assert [item["id"] for item in scoped_chats] == [conversation["id"]]

    assign = _post_handler(f"/api/conversations/{conversation['id']}/project", b'{"project_id":null}')
    assign.do_POST()
    detached = json.loads(b"".join(call.args[0] for call in assign.wfile.write.call_args_list))["data"]
    assert detached["project_id"] is None

    rename = _post_handler(f"/api/projects/{project['id']}", b'{"name":"Vector kernels"}')
    rename.do_POST()
    assert (
        json.loads(b"".join(call.args[0] for call in rename.wfile.write.call_args_list))["data"]["name"]
        == "Vector kernels"
    )

    remove = _get_handler(f"/api/projects/{project['id']}")
    remove.command = "DELETE"
    remove.headers = Message()
    remove.headers["X-zGPU-Request"] = "dashboard-ui"
    remove.do_DELETE()
    assert json.loads(b"".join(call.args[0] for call in remove.wfile.write.call_args_list)) == {
        "deleted": True
    }
    detached_sources = knowledge.search("SIMT")
    assert len(detached_sources) == 1
    assert detached_sources[0]["id"] == source["id"]
    assert detached_sources[0]["project_id"] is None
    assert notes.get(project_note["id"])["project_id"] is None


def test_dashboard_prompt_library_routes(monkeypatch, tmp_path):
    library = PromptLibrary(tmp_path / "prompts.sqlite3")
    monkeypatch.setattr(dashboard_server.backend, "prompts", library)

    create = _post_handler("/api/prompts", b'{"title":"Review","content":"Review {{input}}"}')
    create.do_POST()
    assert create.send_response.call_args.args[0] == 201
    prompt = json.loads(b"".join(call.args[0] for call in create.wfile.write.call_args_list))["data"]

    listing = _get_handler("/api/prompts?limit=50")
    listing.do_GET()
    assert (
        json.loads(b"".join(call.args[0] for call in listing.wfile.write.call_args_list))["data"][0]["id"]
        == prompt["id"]
    )

    update = _post_handler(
        f"/api/prompts/{prompt['id']}", b'{"title":"Security review","content":"Check inputs"}'
    )
    update.do_POST()
    changed = json.loads(b"".join(call.args[0] for call in update.wfile.write.call_args_list))["data"]
    assert changed["title"] == "Security review"

    detail = _get_handler(f"/api/prompts/{prompt['id']}")
    detail.do_GET()
    assert json.loads(b"".join(call.args[0] for call in detail.wfile.write.call_args_list))["data"][
        "content"
    ] == ("Check inputs")

    delete = _get_handler(f"/api/prompts/{prompt['id']}")
    delete.command = "DELETE"
    delete.headers = Message()
    delete.headers["X-zGPU-Request"] = "dashboard-ui"
    delete.do_DELETE()
    assert json.loads(b"".join(call.args[0] for call in delete.wfile.write.call_args_list)) == {
        "deleted": True
    }

    invalid = _post_handler("/api/prompts", b'{"title":"bad","content":""}')
    invalid.do_POST()
    assert invalid.send_response.call_args.args[0] == 400


def test_dashboard_workspace_notes_crud_and_bounded_context_routes(monkeypatch, tmp_path):
    notes = WorkspaceNotes(tmp_path / "notes.sqlite3")
    monkeypatch.setattr(dashboard_server.backend, "notes", notes)
    conversations = ConversationStore(tmp_path / "conversations.sqlite3")
    project = conversations.create_project("Notes project")
    monkeypatch.setattr(dashboard_server.backend, "conversations", conversations)

    create = _post_handler(
        "/api/notes",
        json.dumps(
            {
                "title": "Project invariants",
                "content": "Keep zISA at 32-bit width and preserve valid encodings.",
                "project_id": project["id"],
            }
        ).encode(),
    )
    create.do_POST()
    assert create.send_response.call_args.args[0] == 201
    note = json.loads(b"".join(call.args[0] for call in create.wfile.write.call_args_list))["data"]

    invalid_project = _post_handler(
        "/api/notes", b'{"title":"Invalid scope","content":"Note","project_id":false}'
    )
    invalid_project.do_POST()
    assert invalid_project.send_response.call_args.args[0] == 404

    listing = _get_handler("/api/notes?limit=20")
    listing.do_GET()
    assert (
        json.loads(b"".join(call.args[0] for call in listing.wfile.write.call_args_list))["data"][0]["id"]
        == note["id"]
    )

    search = _get_handler(f"/api/notes/search?query=zISA+encoding&project_id={project['id']}")
    search.do_GET()
    search_result = json.loads(b"".join(call.args[0] for call in search.wfile.write.call_args_list))["data"]
    assert len(search_result) == 1
    assert "32-bit" in search_result[0]["excerpt"]

    general_search = _get_handler("/api/notes/search?query=zISA+encoding")
    general_search.do_GET()
    assert (
        json.loads(b"".join(call.args[0] for call in general_search.wfile.write.call_args_list))["data"] == []
    )

    update = _post_handler(
        f"/api/notes/{note['id']}",
        json.dumps(
            {"title": "Updated invariants", "content": "Preserve architecture compatibility."}
        ).encode(),
    )
    update.do_POST()
    assert json.loads(b"".join(call.args[0] for call in update.wfile.write.call_args_list))["data"][
        "title"
    ] == ("Updated invariants")

    remove = _get_handler(f"/api/notes/{note['id']}")
    remove.command = "DELETE"
    remove.headers = Message()
    remove.headers["X-zGPU-Request"] = "dashboard-ui"
    remove.do_DELETE()
    assert json.loads(b"".join(call.args[0] for call in remove.wfile.write.call_args_list)) == {
        "deleted": True
    }


def test_dashboard_exposes_local_chat_models_and_completion(monkeypatch):
    fake_api = MagicMock()
    fake_api.list_models.return_value = {"object": "list", "data": [{"id": "zgpu-thai"}]}
    fake_api.create_completion.return_value = {"choices": [{"message": {"content": "hello"}}]}
    monkeypatch.setattr(dashboard_server.backend, "chat_api", fake_api)

    get_handler = DashboardHTTPHandler.__new__(DashboardHTTPHandler)
    get_handler.path = "/api/chat/models"
    get_handler.send_response = MagicMock()
    get_handler.send_header = MagicMock()
    get_handler.end_headers = MagicMock()
    get_handler.wfile = MagicMock()
    get_handler.do_GET()
    assert json.loads(b"".join(call.args[0] for call in get_handler.wfile.write.call_args_list)) == {
        "object": "list",
        "data": [{"id": "zgpu-thai"}],
    }

    request = {"model": "zgpu-thai", "messages": [{"role": "user", "content": "Hi"}]}
    post_handler = _post_handler("/api/chat/completions", json.dumps(request).encode())
    post_handler.do_POST()
    assert fake_api.create_completion.call_args.args[0] == request
    assert json.loads(b"".join(call.args[0] for call in post_handler.wfile.write.call_args_list)) == {
        "choices": [{"message": {"content": "hello"}}]
    }


def test_dashboard_local_model_inventory_is_metadata_only_and_rejects_query(monkeypatch):
    catalog = MagicMock()
    catalog.list_models.return_value = {
        "data": [{"id": "zgpu-local-test", "architecture": "gemma", "state": "metadata_only"}],
        "scanned": 1,
        "errors": 0,
        "truncated": False,
    }
    monkeypatch.setattr(dashboard_server.backend, "local_model_catalog", catalog)

    handler = _get_handler("/api/models/local")
    handler.do_GET()
    assert (
        json.loads(b"".join(call.args[0] for call in handler.wfile.write.call_args_list))
        == catalog.list_models.return_value
    )
    catalog.list_models.assert_called_once_with(runtime_model_path=None, runtime_model_id=None)

    invalid = _get_handler("/api/models/local?path=/etc")
    invalid.do_GET()
    assert invalid.send_response.call_args.args == (400,)
    catalog.list_models.assert_called_once_with(runtime_model_path=None, runtime_model_id=None)


def test_dashboard_rejects_oversized_and_invalid_chat_requests():
    oversized = _post_handler("/api/chat/completions", b"", "1048577")
    oversized.do_POST()
    assert oversized.send_response.call_args.args == (413,)

    invalid = _post_handler("/api/chat/completions", b"[]")
    invalid.do_POST()
    assert invalid.send_response.call_args.args == (400,)


def test_dashboard_streams_local_chat_as_server_sent_events(monkeypatch):
    fake_api = MagicMock()

    def emit_completion(payload, event_callback):
        event_callback({"choices": [{"delta": {"role": "assistant"}}]})
        event_callback({"choices": [{"delta": {"content": "hello"}}]})

    fake_api.create_completion.side_effect = emit_completion
    monkeypatch.setattr(dashboard_server.backend, "chat_api", fake_api)
    request = {
        "model": "zgpu-thai",
        "messages": [{"role": "user", "content": "Hi"}],
        "stream": True,
    }
    handler = _post_handler("/api/chat/completions", json.dumps(request).encode())
    handler.do_POST()

    assert ("Content-Type", "text/event-stream; charset=utf-8") in [
        call.args for call in handler.send_header.call_args_list
    ]
    body = b"".join(call.args[0] for call in handler.wfile.write.call_args_list).decode()
    assert '"content":"hello"' in body
    assert "data: [DONE]" in body


def test_knowledge_service_is_exposed_as_zgpu_capability_only(monkeypatch):
    fake_chat = MagicMock()
    fake_chat.create_chat_session.return_value = "session-zgpu-1"
    fake_chat.stream_message.return_value = iter(
        [
            {
                "obj": {
                    "type": "message_start",
                    "final_documents": [
                        {
                            "document_id": "doc-1",
                            "semantic_identifier": "Safety guide",
                            "link": "https://docs.example/safety",
                        },
                        {
                            "document_id": "doc-2",
                            "semantic_identifier": "Unsafe source",
                            "link": "javascript:alert(1)",
                        },
                    ],
                }
            },
            {"obj": {"type": "citation_info", "citation_number": 1, "document_id": "doc-1"}},
            {"obj": {"type": "citation_info", "citation_number": 2, "document_id": "doc-2"}},
            {"obj": {"type": "message_delta", "content": "grounded "}},
            {"obj": {"type": "message_delta", "content": "answer"}},
            {"obj": {"type": "stop"}},
        ]
    )
    monkeypatch.setattr(dashboard_server.backend, "knowledge_chat", fake_chat)
    models = dashboard_server.backend.get_chat_models()
    assert models["data"][-1]["id"] == "zgpu-knowledge"
    assert models["data"][-1]["owned_by"] == "zgpu"

    session_handler = _post_handler("/api/knowledge/sessions", b"{}")
    session_handler.do_POST()
    assert json.loads(b"".join(call.args[0] for call in session_handler.wfile.write.call_args_list)) == {
        "session_id": "session-zgpu-1"
    }

    request = {"session_id": "session-zgpu-1", "message": "question"}
    stream_handler = _post_handler("/api/knowledge/chat", json.dumps(request).encode())
    stream_handler.do_POST()
    body = b"".join(call.args[0] for call in stream_handler.wfile.write.call_args_list).decode()
    assert '"content":"grounded "' in body
    assert '"content":"answer"' in body
    assert '"citations":[{"number":1,"title":"Safety guide","url":"https://docs.example/safety"}' in body
    assert "Unsafe source" in body
    assert '"url":"javascript:alert(1)"' not in body
    assert "data: [DONE]" in body
    fake_chat.stream_message.assert_called_once_with("question", "session-zgpu-1", include_citations=True)


def test_knowledge_service_not_configured_is_not_advertised(monkeypatch):
    monkeypatch.setattr(dashboard_server.backend, "knowledge_chat", None)
    models = dashboard_server.backend.get_chat_models()
    assert all(model["id"] != "zgpu-knowledge" for model in models["data"])

    handler = _post_handler("/api/knowledge/sessions", b"{}")
    handler.do_POST()
    assert handler.send_response.call_args.args == (503,)


def test_knowledge_service_configuration_stays_server_side(monkeypatch):
    monkeypatch.setenv("ZGPU_KNOWLEDGE_API_URL", "https://knowledge.example")
    monkeypatch.setenv("ZGPU_KNOWLEDGE_API_TOKEN", "server-only-secret")
    configured = DashboardBackend()
    assert configured.knowledge_chat is not None
    models_json = json.dumps(configured.get_chat_models())
    assert "zgpu-knowledge" in models_json
    assert "server-only-secret" not in models_json

    monkeypatch.delenv("ZGPU_KNOWLEDGE_API_TOKEN")
    with pytest.raises(ValueError, match="Both ZGPU_KNOWLEDGE_API_URL"):
        DashboardBackend()


def test_dashboard_rejects_network_wide_bind():
    with pytest.raises(ValueError, match="loopback only"):
        dashboard_server.run_dashboard(host="0.0.0.0")  # nosec B104


def test_dashboard_rejects_spoofed_host_and_cross_site_posts(monkeypatch):
    local = _get_handler("/api/telemetry")
    local.headers = Message()
    local.headers["Host"] = "localhost:9000"
    local.headers["Origin"] = "http://localhost:9000"
    local.server = SimpleNamespace(server_port=9000)
    local.do_GET()
    assert local.send_response.call_args.args[0] == 200

    cli = _get_handler("/api/telemetry")
    cli.headers = Message()
    cli.headers["Host"] = "127.0.0.1:9000"
    cli.server = SimpleNamespace(server_port=9000)
    assert cli._validate_request_origin() is True

    spoofed_host = _get_handler("/api/telemetry")
    spoofed_host.headers = Message()
    spoofed_host.headers["Host"] = "attacker.example:9000"
    spoofed_host.server = SimpleNamespace(server_port=9000)
    spoofed_host.do_GET()
    assert spoofed_host.send_response.call_args.args[0] == 403

    api = MagicMock()
    monkeypatch.setattr(dashboard_server.backend, "chat_api", api)
    cross_site = _post_handler(
        "/api/chat/completions",
        json.dumps({"model": "zgpu-thai", "messages": [{"role": "user", "content": "run"}]}).encode(),
    )
    cross_site.headers["Host"] = "127.0.0.1:9000"
    cross_site.headers["Origin"] = "http://attacker.example"
    cross_site.server = SimpleNamespace(server_port=9000)
    cross_site.do_POST()
    assert cross_site.send_response.call_args.args[0] == 403
    api.create_completion.assert_not_called()

    missing_marker = _post_handler(
        "/api/chat/completions",
        json.dumps({"model": "zgpu-thai", "messages": [{"role": "user", "content": "run"}]}).encode(),
    )
    del missing_marker.headers["X-zGPU-Request"]
    missing_marker.headers["Host"] = "127.0.0.1:9000"
    missing_marker.server = SimpleNamespace(server_port=9000)
    missing_marker.do_POST()
    assert missing_marker.send_response.call_args.args[0] == 403
    api.create_completion.assert_not_called()
