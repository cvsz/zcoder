"""zGPU simulator telemetry and local developer console server.

Provides a live web interface for:
- Software simulator counters (IPC, cycles, memory traffic, bank conflicts).
- Active SM warp scheduler states and SIMT lane visualizers.
- Live LLM inference test prompt submission and real-time generation benchmark.
- Self-coding kernel generator and evaluator.
- SuperAGI autonomous agent execution monitor.
- Network Compute Discovery & CPU/GPU powerup cluster manager.
"""

from __future__ import annotations

import base64
import binascii
import ipaddress
import json
import logging
import math
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse, urlsplit

from zgpu.agi.agent_core import SuperAGIAgent
from zgpu.agi.swarm import SuperAGISwarm
from zgpu.cluster.discovery.scanner import NetworkComputeScanner
from zgpu.cluster.network_pool import NetworkCPUPool
from zgpu.compiler.ast_compiler import AstJitCompiler
from zgpu.integrations.assistants import AssistantProfileError, AssistantProfiles
from zgpu.integrations.conversations import ConversationError, ConversationStore
from zgpu.integrations.document_loaders import MAX_UPLOAD_BYTES, DocumentLoadError, extract_document_text
from zgpu.integrations.embeddings import OpenAICompatibleEmbeddingProvider
from zgpu.integrations.engineering_jobs import EngineeringJobsClient, EngineeringJobsError
from zgpu.integrations.knowledge_base import KnowledgeBaseClient, KnowledgeBaseError
from zgpu.integrations.knowledge_chat import KnowledgeChatClient, KnowledgeChatError
from zgpu.integrations.local_knowledge import LocalKnowledgeError, LocalKnowledgeStore
from zgpu.integrations.local_model_catalog import LocalModelCatalog, LocalModelCatalogError
from zgpu.integrations.notes import WorkspaceNotes, WorkspaceNotesError
from zgpu.integrations.openai_provider import OpenAICompatibleProvider, OpenAIProviderError
from zgpu.integrations.prompts import PromptLibrary, PromptLibraryError
from zgpu.integrations.zisa_studio import (
    ZISAAssemblyError,
    ZISASimulationError,
    assemble_source,
    list_opcodes,
    simulate_elementwise_expression,
    simulate_source,
)
from zgpu.kernels.flash_attn.flash_attention import FlashAttention3Kernel
from zgpu.llm.llama_cpp import LlamaCppConfig, LlamaCppError, LlamaCppServer
from zgpu.llm.model_registry import ModelRegistry
from zgpu.llm.openai_compat import CompletionRequestError, OpenAICompatibleAdapter, ProviderPool
from zgpu.llm.tool_calls import ToolCallError, ZGPUToolRegistry
from zgpu.llm.transformer import ZGPULLM, LLMConfig
from zgpu.runtime.network_policy import require_loopback_host
from zgpu.runtime.runtime import ZRuntime
from zgpu.self_coding.evaluator import KernelEvaluator
from zgpu.self_coding.generator import SelfCodingEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("zGPU-Dashboard")


class DashboardBackend:
    """Telemetry aggregator, cluster manager, and service manager."""

    def __init__(self):
        self.runtime = ZRuntime()
        self.llm = ZGPULLM(config=LLMConfig(d_model=16, num_layers=2), runtime=self.runtime)
        self.model_registry = ModelRegistry(runtime=self.runtime)
        self.local_model_catalog = LocalModelCatalog.from_environment()
        llama_config = LlamaCppConfig.from_environment()
        self.llama_cpp = LlamaCppServer(llama_config) if llama_config is not None else None
        if self.llama_cpp is not None:
            self.llama_cpp.start()
        openai_url = os.environ.get("ZGPU_OPENAI_API_URL", "").strip()
        openai_key = os.environ.get("ZGPU_OPENAI_API_KEY", "").strip()
        if bool(openai_url) != bool(openai_key):
            raise ValueError("Both ZGPU_OPENAI_API_URL and ZGPU_OPENAI_API_KEY are required")
        remote_provider = (
            OpenAICompatibleProvider(openai_url, openai_key) if openai_url and openai_key else None
        )
        self.model_providers = ProviderPool([self.llama_cpp, remote_provider])
        self.chat_api = OpenAICompatibleAdapter(self.model_registry, external_provider=self.model_providers)
        self.chat_tools = self._build_chat_tools()
        knowledge_url = os.environ.get("ZGPU_KNOWLEDGE_API_URL", "").strip()
        knowledge_token = os.environ.get("ZGPU_KNOWLEDGE_API_TOKEN", "").strip()
        if bool(knowledge_url) != bool(knowledge_token):
            raise ValueError("Both ZGPU_KNOWLEDGE_API_URL and ZGPU_KNOWLEDGE_API_TOKEN are required")
        self.knowledge_chat = (
            KnowledgeChatClient(knowledge_url, knowledge_token) if knowledge_url and knowledge_token else None
        )
        knowledge_base_url = os.environ.get("ZGPU_KNOWLEDGE_BASE_URL", "").strip()
        knowledge_base_key = os.environ.get("ZGPU_KNOWLEDGE_BASE_API_KEY", "").strip()
        if bool(knowledge_base_url) != bool(knowledge_base_key):
            raise ValueError("Both ZGPU_KNOWLEDGE_BASE_URL and ZGPU_KNOWLEDGE_BASE_API_KEY are required")
        self.knowledge_base = (
            KnowledgeBaseClient(knowledge_base_url, knowledge_base_key)
            if knowledge_base_url and knowledge_base_key
            else None
        )
        embedding_url = os.environ.get("ZGPU_EMBEDDING_API_URL", "").strip()
        embedding_model = os.environ.get("ZGPU_EMBEDDING_MODEL", "").strip()
        embedding_token = os.environ.get("ZGPU_EMBEDDING_API_KEY", "").strip()
        embedding_settings = (embedding_url, embedding_model, embedding_token)
        if any(embedding_settings) and not all(embedding_settings):
            raise ValueError(
                "ZGPU_EMBEDDING_API_URL, ZGPU_EMBEDDING_MODEL, and ZGPU_EMBEDDING_API_KEY must be configured together"
            )
        embedding_provider = (
            OpenAICompatibleEmbeddingProvider(embedding_url, embedding_model, embedding_token)
            if all(embedding_settings)
            else None
        )
        configured_knowledge_path = os.environ.get("ZGPU_KNOWLEDGE_DB_PATH", "").strip()
        if configured_knowledge_path:
            knowledge_path = Path(configured_knowledge_path).expanduser()
        elif os.name == "nt":
            knowledge_path = (
                Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
                / "zGPU"
                / "knowledge.sqlite3"
            )
        elif sys.platform == "darwin":
            knowledge_path = Path.home() / "Library" / "Application Support" / "zGPU" / "knowledge.sqlite3"
        else:
            knowledge_path = (
                Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
                / "zgpu"
                / "knowledge.sqlite3"
            )
        self.local_knowledge = LocalKnowledgeStore(knowledge_path, embedding_provider=embedding_provider)
        configured_conversation_path = os.environ.get("ZGPU_CONVERSATIONS_DB_PATH", "").strip()
        if configured_conversation_path:
            conversation_path = Path(configured_conversation_path).expanduser()
        elif os.name == "nt":
            conversation_path = (
                Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
                / "zGPU"
                / "conversations.sqlite3"
            )
        elif sys.platform == "darwin":
            conversation_path = (
                Path.home() / "Library" / "Application Support" / "zGPU" / "conversations.sqlite3"
            )
        else:
            conversation_path = (
                Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
                / "zgpu"
                / "conversations.sqlite3"
            )
        self.conversations = ConversationStore(conversation_path)
        configured_assistants_path = os.environ.get("ZGPU_ASSISTANTS_DB_PATH", "").strip()
        if configured_assistants_path:
            assistants_path = Path(configured_assistants_path).expanduser()
        elif os.name == "nt":
            assistants_path = (
                Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
                / "zGPU"
                / "assistants.sqlite3"
            )
        elif sys.platform == "darwin":
            assistants_path = Path.home() / "Library" / "Application Support" / "zGPU" / "assistants.sqlite3"
        else:
            assistants_path = (
                Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
                / "zgpu"
                / "assistants.sqlite3"
            )
        self.assistants = AssistantProfiles(assistants_path)
        configured_prompts_path = os.environ.get("ZGPU_PROMPTS_DB_PATH", "").strip()
        if configured_prompts_path:
            prompts_path = Path(configured_prompts_path).expanduser()
        elif os.name == "nt":
            prompts_path = (
                Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
                / "zGPU"
                / "prompts.sqlite3"
            )
        elif sys.platform == "darwin":
            prompts_path = Path.home() / "Library" / "Application Support" / "zGPU" / "prompts.sqlite3"
        else:
            prompts_path = (
                Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
                / "zgpu"
                / "prompts.sqlite3"
            )
        self.prompts = PromptLibrary(prompts_path)
        configured_notes_path = os.environ.get("ZGPU_NOTES_DB_PATH", "").strip()
        if configured_notes_path:
            notes_path = Path(configured_notes_path).expanduser()
        elif os.name == "nt":
            notes_path = (
                Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
                / "zGPU"
                / "notes.sqlite3"
            )
        elif sys.platform == "darwin":
            notes_path = Path.home() / "Library" / "Application Support" / "zGPU" / "notes.sqlite3"
        else:
            notes_path = (
                Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
                / "zgpu"
                / "notes.sqlite3"
            )
        self.notes = WorkspaceNotes(notes_path)
        engineering_url = os.environ.get("ZGPU_ENGINEERING_API_URL", "").strip()
        engineering_token = os.environ.get("ZGPU_ENGINEERING_API_TOKEN", "").strip()
        if bool(engineering_url) != bool(engineering_token):
            raise ValueError("Both ZGPU_ENGINEERING_API_URL and ZGPU_ENGINEERING_API_TOKEN are required")
        self.engineering_jobs = (
            EngineeringJobsClient(engineering_url, engineering_token)
            if engineering_url and engineering_token
            else None
        )
        self.agent = SuperAGIAgent(d_model=16, runtime=self.runtime)
        self.swarm = SuperAGISwarm(shared_memory_dim=16, runtime=self.runtime)
        self.self_coder = SelfCodingEngine()
        self.evaluator = KernelEvaluator(self.runtime)
        self.network_pool = NetworkCPUPool(runtime=self.runtime)
        self.scanner = NetworkComputeScanner()
        self.flash_attn = FlashAttention3Kernel(d_model=16, block_size=4, runtime=self.runtime)

        # Pre-seed memory
        for i in range(16):
            self.agent.memory.add(f"init_context_{i}", [0.1 * ((i + j) % 7 - 3) for j in range(16)])

    def get_system_telemetry(self) -> dict[str, Any]:
        sm = self.runtime.device.sms[0]
        mem = self.runtime.device.global_mem
        return {
            "timestamp": time.time(),
            "device_name": "zGPU Software SIMT Simulator",
            "sm_count": len(self.runtime.device.sms),
            "warp_size": 32,
            "clock_mhz": 1200,
            "performance_counters": {
                "cycles": sm.cycle_count,
                "instructions_retired": sm.instructions_retired,
                "ipc": round(sm.instructions_retired / max(1, sm.cycle_count), 2),
                "dram_reads": mem.read_transactions * 4,
                "dram_writes": mem.write_transactions * 4,
                "bank_conflicts": sm.shared_mem.bank_conflicts,
            },
            "llm_config": {
                "d_model": self.llm.config.d_model,
                "vocab_size": self.llm.config.vocab_size,
                "layers": self.llm.config.num_layers,
                "flash_attention_enabled": True,
            },
            "cluster_status": {
                "registered_nodes": len(self.network_pool.nodes),
                "active_nodes": sum(1 for n in self.network_pool.nodes.values() if n.active),
                "nodes": [
                    {"id": n.node_id, "url": n.url, "active": n.active, "latency_ms": round(n.latency_ms, 2)}
                    for n in self.network_pool.nodes.values()
                ],
            },
            "super_agi_status": {
                "active_memory_records": self.agent.memory.count(),
                "history_steps": len(self.agent.execution_history),
                "swarm_active": len(self.swarm.agents) > 0,
            },
        }

    def close_optional_services(self) -> None:
        if self.llama_cpp is not None:
            self.llama_cpp.stop()

    def get_chat_models(self) -> dict[str, Any]:
        result = self.chat_api.list_models()
        if self.knowledge_chat is not None:
            result["data"].append(
                {"id": "zgpu-knowledge", "object": "model", "created": 0, "owned_by": "zgpu"}
            )
        return result

    def _build_chat_tools(self) -> ZGPUToolRegistry:
        registry = ZGPUToolRegistry()

        def telemetry_snapshot() -> dict[str, Any]:
            telemetry = self.get_system_telemetry()
            return {
                "device": "zGPU Software SIMT Simulator",
                "sm_count": telemetry["sm_count"],
                "warp_size": telemetry["warp_size"],
                "performance_counters": telemetry["performance_counters"],
                "llm_config": telemetry["llm_config"],
            }

        def assemble_for_chat(source: str) -> dict[str, Any]:
            result = assemble_source(source)
            limit = 256
            result["word_hex"] = result["word_hex"][:limit]
            result["bytecode_le_hex"] = result["bytecode_le_hex"][:limit]
            result["truncated"] = result["instruction_count"] > limit
            return result

        registry.register(
            "zgpu_get_telemetry",
            "Read a small, safe snapshot of zGPU software simulator counters. This does not report physical GPU execution.",
            {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
            telemetry_snapshot,
        )
        registry.register(
            "zgpu_assemble_zisa",
            "Assemble bounded zISA-32 source and return its instruction words. Does not execute the program.",
            {
                "type": "object",
                "properties": {"source": {"type": "string", "maxLength": 65536}},
                "required": ["source"],
                "additionalProperties": False,
            },
            assemble_for_chat,
        )
        registry.register(
            "zgpu_simulate_zisa",
            "Simulate one bounded 32-lane warp using the zGPU software simulator, never physical GPU hardware.",
            {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "maxLength": 65536},
                    "max_cycles": {"type": "integer", "minimum": 1, "maximum": 20000},
                },
                "required": ["source", "max_cycles"],
                "additionalProperties": False,
            },
            simulate_source,
        )
        return registry

    def create_tool_completion(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Run at most three remote model turns and four allowlisted tool calls."""
        model = payload.get("model")
        if not isinstance(model, str) or not model.startswith("zgpu-remote-"):
            raise CompletionRequestError("zGPU tools are available only for configured remote models")
        if "tools" in payload or "tool_choice" in payload or "parallel_tool_calls" in payload:
            raise CompletionRequestError("client-defined tools are not accepted")
        messages = payload.get("messages")
        if not isinstance(messages, list) or not messages:
            raise CompletionRequestError("'messages' must be a non-empty array")
        working_messages = list(messages)
        calls_used = 0
        seen_ids: set[str] = set()
        for _ in range(3):
            request = {key: value for key, value in payload.items() if key not in {"zgpu_tools", "stream"}}
            request.update(
                {
                    "messages": working_messages,
                    "tools": self.chat_tools.definitions(),
                    "tool_choice": "auto",
                    "parallel_tool_calls": False,
                    "stream": False,
                }
            )
            if len(json.dumps(request, ensure_ascii=False).encode("utf-8")) > 1_048_576:
                raise CompletionRequestError("tool conversation exceeds 1 MiB")
            result = self.chat_api.create_completion(request)
            choices = result.get("choices") if isinstance(result, dict) else None
            if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                raise OpenAIProviderError("provider returned an invalid tool completion")
            message = choices[0].get("message")
            if not isinstance(message, dict):
                raise OpenAIProviderError("provider returned an invalid tool message")
            tool_calls = message.get("tool_calls", [])
            if not tool_calls:
                result["model"] = model
                return result
            if not isinstance(tool_calls, list) or len(tool_calls) > 4 - calls_used:
                raise CompletionRequestError("tool call limit exceeded")
            working_messages.append(message)
            for tool_call in tool_calls:
                if not isinstance(tool_call, dict):
                    raise OpenAIProviderError("provider returned an invalid tool call")
                call_id = tool_call.get("id")
                function = tool_call.get("function")
                if (
                    not isinstance(call_id, str)
                    or not call_id
                    or len(call_id) > 256
                    or call_id in seen_ids
                    or not isinstance(function, dict)
                    or not isinstance(function.get("name"), str)
                    or not isinstance(function.get("arguments"), str)
                ):
                    raise OpenAIProviderError("provider returned an invalid tool call")
                seen_ids.add(call_id)
                try:
                    content = self.chat_tools.execute(function["name"], function["arguments"])
                except ToolCallError as exc:
                    content = json.dumps({"error": str(exc)})
                working_messages.append({"role": "tool", "tool_call_id": call_id, "content": content})
                calls_used += 1
        raise CompletionRequestError("tool round limit exceeded")

    def validate_knowledge_project(self, project_id: str | None, *, allow_all: bool = False) -> None:
        if project_id is None or (allow_all and project_id == "*"):
            return
        try:
            projects = self.conversations.list_projects()
        except ConversationError as exc:
            raise LocalKnowledgeError("project registry is unavailable", status=503) from exc
        if not isinstance(project_id, str) or not any(project["id"] == project_id for project in projects):
            raise LocalKnowledgeError("project not found", status=404)

    def create_knowledge_session(self) -> str:
        if self.knowledge_chat is None:
            raise KnowledgeChatError(503, "NOT_CONFIGURED", "Knowledge chat is not configured")
        return self.knowledge_chat.create_chat_session()

    def list_engineering_jobs(self, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        if self.engineering_jobs is None:
            raise EngineeringJobsError(503, "NOT_CONFIGURED", "Engineering service is not configured")
        return self.engineering_jobs.list_jobs(limit=limit, offset=offset)

    def get_engineering_entitlements(self) -> dict[str, Any]:
        if self.engineering_jobs is None:
            raise EngineeringJobsError(503, "NOT_CONFIGURED", "Engineering service is not configured")
        return self.engineering_jobs.get_entitlements()

    def get_engineering_job(self, job_id: str) -> dict[str, Any]:
        if self.engineering_jobs is None:
            raise EngineeringJobsError(503, "NOT_CONFIGURED", "Engineering service is not configured")
        return self.engineering_jobs.get_job(job_id)

    def cancel_engineering_job(self, job_id: str, *, idempotency_key: str | None = None) -> dict[str, Any]:
        if self.engineering_jobs is None:
            raise EngineeringJobsError(503, "NOT_CONFIGURED", "Engineering service is not configured")
        return self.engineering_jobs.cancel_job(job_id, idempotency_key=idempotency_key)

    def submit_engineering_job(
        self,
        task: str,
        *,
        runtime: str = "direct",
        model: str | None = None,
        budget_usd: float = 0.0,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if self.engineering_jobs is None:
            raise EngineeringJobsError(503, "NOT_CONFIGURED", "Engineering service is not configured")
        if runtime == "direct" and (isinstance(budget_usd, bool) or budget_usd <= 0):
            raise ValueError("direct engineering jobs require a positive USD budget cap")
        return self.engineering_jobs.submit_job(
            task,
            runtime=runtime,
            model=model,
            budget_usd=budget_usd,
            idempotency_key=idempotency_key,
        )

    def generate_llm(self, prompt: str, max_tokens: int = 16) -> dict[str, Any]:
        t0 = time.perf_counter()
        token_ids = [ord(c) % self.llm.config.vocab_size for c in prompt] or [1]
        out_tokens = self.llm.generate(token_ids, max_new_tokens=max_tokens)
        new_tokens = out_tokens[len(token_ids) :]
        text_out = "".join(chr(32 + (t % 95)) for t in new_tokens)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "prompt": prompt,
            "output_text": text_out,
            "tokens_generated": len(new_tokens),
            "latency_ms": round(latency_ms, 2),
            "throughput_tps": round(len(new_tokens) / max(0.001, latency_ms / 1000.0), 2),
        }

    def trigger_self_coding(self, op_name: str, op_type: str) -> dict[str, Any]:
        kernel = self.self_coder.synthesize_vector_op(op_name, op_type)
        eval_rep = self.evaluator.evaluate_kernel(kernel, num_warps=1)
        return {
            "kernel_name": kernel.name,
            "source_code": kernel.source_code,
            "bytecode_length": len(kernel.bytecode) if kernel.bytecode else 0,
            "valid": eval_rep.valid,
            "cycles": eval_rep.cycles_elapsed,
            "ipc": round(eval_rep.ipc, 2),
            "error": eval_rep.error_message,
        }

    def trigger_agi_step(self, goal: str) -> dict[str, Any]:
        res = self.agent.step(goal)
        return {
            "step_num": res.step_num,
            "thought": res.thought,
            "action": res.action,
            "score": round(res.score, 3),
            "observation": res.observation,
            "latency_ms": round(res.latency_ms, 2),
        }

    def trigger_network_scan(
        self, subnet_prefix: str = "127.0.0", start: int = 1, end: int = 2
    ) -> dict[str, Any]:
        discovered = self.scanner.scan_subnet(base_ip_prefix=subnet_prefix, start_host=start, end_host=end)
        nodes = []
        for node in discovered:
            node_id = f"{node.node_type}_{node.ip}_{node.port}"
            token = self.network_pool.configured_worker_token(node_id, node.url)
            registered = True
            try:
                self.network_pool.register_node(node_id, node.url, token=token)
            except ValueError as exc:
                if "require an authentication token" not in str(exc):
                    raise
                registered = False
            nodes.append(
                {
                    "ip": node.ip,
                    "port": node.port,
                    "type": node.node_type,
                    "latency_ms": node.latency_ms,
                    "url": node.url,
                    "registered": registered,
                    "authentication_required": not registered,
                }
            )
        return {
            "nodes_found": len(discovered),
            "nodes_registered": sum(node["registered"] for node in nodes),
            "nodes": nodes,
        }

    def trigger_hybrid_gemm(self, size: int = 16, gpu_fraction: float = 0.5) -> dict[str, Any]:
        A = [[1.0 for _ in range(size)] for _ in range(size)]
        B = [[2.0 for _ in range(size)] for _ in range(size)]
        t0 = time.perf_counter()
        out = self.network_pool.hybrid_gemm_powerup(A, B, gpu_fraction=gpu_fraction)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "matrix_size": f"{size}x{size}",
            "gpu_fraction": gpu_fraction,
            "latency_ms": round(elapsed_ms, 2),
            "result_sample": out[0][0] if out and out[0] else 0.0,
        }


backend = DashboardBackend()


class DashboardHTTPHandler(BaseHTTPRequestHandler):
    def _validate_request_origin(self, *, require_custom_header: bool = False) -> bool:
        headers = getattr(self, "headers", None)
        if headers is None:
            return not require_custom_header
        host_header = headers.get("Host")
        origin = headers.get("Origin")
        fetch_site = headers.get("Sec-Fetch-Site", "").lower()
        server_port = getattr(getattr(self, "server", None), "server_port", None)

        host_parts = None
        host_name = None
        host_port = None
        if host_header:
            try:
                host_parts = urlsplit(f"//{host_header}")
                host_name = host_parts.hostname
                host_port = host_parts.port
                host_is_loopback = host_name is not None and (
                    host_name.lower() == "localhost" or ipaddress.ip_address(host_name).is_loopback
                )
            except ValueError:
                host_is_loopback = False
                host_name = None
                host_port = None
            if (
                not host_is_loopback
                or host_parts.path
                or host_parts.query
                or host_parts.fragment
                or host_parts.username
                or host_parts.password
            ):
                self._send_json(
                    {"error": {"message": "The zGPU dashboard accepts loopback hosts only"}}, status=403
                )
                return False
            if server_port is not None and host_port != server_port:
                self._send_json({"error": {"message": "The zGPU dashboard host port is invalid"}}, status=403)
                return False

        if origin:
            origin_parts = None
            try:
                origin_parts = urlsplit(origin)
                origin_name = origin_parts.hostname
                origin_port = origin_parts.port if origin_parts.port is not None else 80
                origin_is_loopback = origin_name is not None and (
                    origin_name.lower() == "localhost" or ipaddress.ip_address(origin_name).is_loopback
                )
            except ValueError:
                origin_is_loopback = False
                origin_name = None
                origin_port = None
            expected_port = server_port if server_port is not None else host_port if host_header else None
            if (
                not origin_is_loopback
                or origin_parts is None
                or origin_parts.scheme != "http"
                or origin_parts.username
                or origin_parts.password
                or origin_parts.path
                or origin_parts.query
                or origin_parts.fragment
                or (expected_port is not None and origin_port != expected_port)
                or (host_name is not None and origin_name.lower() != host_name.lower())
            ):
                self._send_json(
                    {"error": {"message": "The zGPU dashboard rejected this request origin"}}, status=403
                )
                return False

        if fetch_site == "cross-site":
            self._send_json({"error": {"message": "Cross-site requests are not allowed"}}, status=403)
            return False
        if require_custom_header and headers.get("X-zGPU-Request") != "dashboard-ui":
            self._send_json(
                {"error": {"message": "The zGPU dashboard request marker is missing"}}, status=403
            )
            return False
        return True

    def do_GET(self):
        if not self._validate_request_origin():
            return
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'",
            )
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write((Path(__file__).with_name("index.html")).read_bytes())

        elif url.path in ("/dashboard.css", "/dashboard.js"):
            asset = Path(__file__).with_name(url.path.removeprefix("/"))
            content_type = (
                "text/css; charset=utf-8" if asset.suffix == ".css" else "text/javascript; charset=utf-8"
            )
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(asset.read_bytes())

        elif url.path == "/api/telemetry":
            data = backend.get_system_telemetry()
            self._send_json(data)

        elif url.path == "/api/isa/opcodes":
            if url.query:
                self._send_json(
                    {"error": {"message": "opcode listing does not accept query parameters"}}, status=400
                )
                return
            self._send_json({"target": "zISA-32", "instruction_width_bits": 32, "data": list_opcodes()})

        elif url.path == "/api/knowledge/status":
            try:
                query = parse_qs(url.query, keep_blank_values=True, strict_parsing=True)
                if set(query) - {"project_id"} or any(len(values) != 1 for values in query.values()):
                    raise LocalKnowledgeError("invalid knowledge scope")
                raw_project_id = query.get("project_id", ["*"])[0]
                project_id = None if raw_project_id == "" else raw_project_id
                backend.validate_knowledge_project(project_id, allow_all=True)
                self._send_json({"data": backend.local_knowledge.retrieval_status(project_id=project_id)})
            except LocalKnowledgeError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
            except ValueError:
                self._send_json({"error": {"message": "invalid knowledge scope"}}, status=400)

        elif url.path == "/api/knowledge/base/status":
            if url.query:
                self._send_json(
                    {"error": {"message": "knowledge service status does not accept query parameters"}},
                    status=400,
                )
                return
            if backend.knowledge_base is None:
                self._send_json({"configured": False})
                return
            try:
                self._send_json(
                    {"configured": True, "available": True, "health": backend.knowledge_base.health()}
                )
            except KnowledgeBaseError as exc:
                log.warning("zGPU Knowledge Base health request failed: %s", exc.code)
                self._send_json({"configured": True, "available": False, "message": str(exc)})

        elif url.path == "/api/knowledge/base/documents":
            if url.query:
                self._send_json(
                    {"error": {"message": "connected documents route does not accept query parameters"}},
                    status=400,
                )
                return
            if backend.knowledge_base is None:
                self._send_json(
                    {"error": {"message": "The connected knowledge service is not configured"}}, status=503
                )
                return
            try:
                self._send_json({"data": backend.knowledge_base.list_documents()})
            except KnowledgeBaseError as exc:
                log.warning("zGPU Knowledge Base document listing failed: %s", exc.code)
                self._send_json(
                    {"error": {"message": "The connected knowledge service could not list documents"}},
                    status=502,
                )

        elif url.path == "/api/knowledge/base/jobs":
            if backend.knowledge_base is None:
                self._send_json(
                    {"error": {"message": "The connected knowledge service is not configured"}}, status=503
                )
                return
            try:
                query = parse_qs(url.query, keep_blank_values=True, strict_parsing=True)
                if set(query) - {"limit"} or any(len(values) != 1 for values in query.values()):
                    raise ValueError("invalid ingestion job query")
                raw_limit = query.get("limit", ["100"])[0]
                if not raw_limit.isascii() or not raw_limit.isdecimal():
                    raise ValueError("invalid ingestion job limit")
                jobs = backend.knowledge_base.list_ingestion_jobs(limit=int(raw_limit))
                self._send_json({"data": jobs})
            except ValueError:
                self._send_json({"error": {"message": "Invalid connected ingestion job query"}}, status=400)
            except KnowledgeBaseError as exc:
                log.warning("zGPU Knowledge Base job listing failed: %s", exc.code)
                self._send_json(
                    {"error": {"message": "The connected knowledge service could not list jobs"}}, status=502
                )

        elif url.path.startswith("/api/knowledge/base/jobs/"):
            if backend.knowledge_base is None:
                self._send_json(
                    {"error": {"message": "The connected knowledge service is not configured"}}, status=503
                )
                return
            encoded_id = url.path.removeprefix("/api/knowledge/base/jobs/")
            if not encoded_id or "/" in encoded_id or url.query:
                self._send_json(
                    {"error": {"message": "Invalid connected ingestion job identifier"}}, status=400
                )
                return
            try:
                job = backend.knowledge_base.get_ingestion_job(unquote(encoded_id, errors="strict"))
                self._send_json({"data": job})
            except (UnicodeDecodeError, ValueError):
                self._send_json(
                    {"error": {"message": "Invalid connected ingestion job identifier"}}, status=400
                )
            except KnowledgeBaseError as exc:
                status = exc.status if exc.status in {404, 409} else 502
                log.warning("zGPU Knowledge Base job detail failed: %s", exc.code)
                self._send_json(
                    {"error": {"message": "The connected knowledge service could not load this job"}},
                    status=status,
                )

        elif url.path == "/api/chat/models":
            try:
                self._send_json(backend.get_chat_models())
            except OpenAIProviderError as exc:
                log.warning("zGPU model provider discovery failed: %s", exc)
                self._send_json(
                    {"error": {"message": "Configured model provider is unavailable"}}, status=502
                )

        elif url.path == "/api/models/local":
            if url.query:
                self._send_json(
                    {"error": {"message": "local model inventory does not accept query parameters"}},
                    status=400,
                )
                return
            llama_cpp = backend.llama_cpp
            self._send_json(
                backend.local_model_catalog.list_models(
                    runtime_model_path=llama_cpp.config.model_path if llama_cpp is not None else None,
                    runtime_model_id=llama_cpp.config.alias if llama_cpp is not None else None,
                )
            )

        elif url.path == "/api/prompts":
            try:
                query = parse_qs(url.query, keep_blank_values=True, strict_parsing=True)
                if set(query) - {"limit"} or any(len(values) != 1 for values in query.values()):
                    raise ValueError
                limit = int(query.get("limit", ["200"])[0])
                self._send_json({"data": backend.prompts.list(limit=limit)})
            except ValueError as exc:
                if isinstance(exc, PromptLibraryError):
                    self._send_json({"error": {"message": str(exc)}}, status=exc.status)
                else:
                    self._send_json({"error": {"message": "Invalid prompt query"}}, status=400)

        elif url.path == "/api/notes/search":
            try:
                query = parse_qs(url.query, keep_blank_values=True, strict_parsing=True)
                if (
                    set(query) - {"query", "project_id"}
                    or "query" not in query
                    or any(len(values) != 1 for values in query.values())
                ):
                    raise ValueError
                project_id = query.get("project_id", [""])[0] or None
                if project_id is not None:
                    backend.validate_knowledge_project(project_id)
                self._send_json({"data": backend.notes.search(query["query"][0], project_id=project_id)})
            except WorkspaceNotesError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
            except LocalKnowledgeError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
            except ValueError:
                self._send_json({"error": {"message": "Invalid workspace note search query"}}, status=400)

        elif url.path == "/api/notes":
            try:
                query = parse_qs(url.query, keep_blank_values=True, strict_parsing=True)
                if set(query) - {"limit"} or any(len(values) != 1 for values in query.values()):
                    raise ValueError
                limit = int(query.get("limit", [str(WorkspaceNotes.MAX_NOTES)])[0])
                self._send_json({"data": backend.notes.list(limit=limit)})
            except WorkspaceNotesError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
            except ValueError:
                self._send_json({"error": {"message": "Invalid workspace note query"}}, status=400)

        elif url.path.startswith("/api/notes/"):
            encoded_id = url.path.removeprefix("/api/notes/")
            if not encoded_id or "/" in encoded_id or url.query:
                self._send_json({"error": {"message": "Invalid workspace note identifier"}}, status=400)
                return
            try:
                note_id = unquote(encoded_id, errors="strict")
                self._send_json({"data": backend.notes.get(note_id)})
            except WorkspaceNotesError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
            except UnicodeDecodeError:
                self._send_json({"error": {"message": "Invalid workspace note identifier"}}, status=400)

        elif url.path.startswith("/api/prompts/"):
            encoded_id = url.path.removeprefix("/api/prompts/")
            if not encoded_id or "/" in encoded_id or url.query:
                self._send_json({"error": {"message": "Invalid prompt identifier"}}, status=400)
                return
            try:
                prompt_id = unquote(encoded_id, errors="strict")
                self._send_json({"data": backend.prompts.get(prompt_id)})
            except PromptLibraryError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
            except UnicodeDecodeError:
                self._send_json({"error": {"message": "Invalid prompt identifier"}}, status=400)

        elif url.path == "/api/projects":
            try:
                if url.query:
                    raise ValueError
                self._send_json({"data": backend.conversations.list_projects()})
            except ValueError:
                self._send_json({"error": {"message": "Invalid project query"}}, status=400)

        elif url.path == "/api/assistants":
            if url.query:
                self._send_json(
                    {"error": {"message": "assistant listing does not accept query parameters"}}, status=400
                )
                return
            try:
                self._send_json({"data": backend.assistants.list()})
            except AssistantProfileError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)

        elif url.path.startswith("/api/assistants/"):
            encoded_id = url.path.removeprefix("/api/assistants/")
            if not encoded_id or "/" in encoded_id or url.query:
                self._send_json({"error": {"message": "Invalid assistant profile identifier"}}, status=400)
                return
            try:
                profile_id = unquote(encoded_id, errors="strict")
                self._send_json({"data": backend.assistants.get(profile_id)})
            except AssistantProfileError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
            except UnicodeDecodeError:
                self._send_json({"error": {"message": "Invalid assistant profile identifier"}}, status=400)

        elif url.path == "/api/conversations":
            try:
                query = parse_qs(url.query, keep_blank_values=True, strict_parsing=True)
                if set(query) - {"limit", "search", "project_id"} or any(
                    len(values) != 1 for values in query.values()
                ):
                    raise ValueError
                limit = int(query.get("limit", ["200"])[0])
                search = query.get("search", [""])[0]
                project_id = query.get("project_id", [None])[0]
                self._send_json(
                    {"data": backend.conversations.list(limit=limit, search=search, project_id=project_id)}
                )
            except ValueError as exc:
                if isinstance(exc, ConversationError):
                    self._send_json({"error": {"message": str(exc)}}, status=exc.status)
                else:
                    self._send_json({"error": {"message": "Invalid conversation query"}}, status=400)

        elif url.path.startswith("/api/conversations/"):
            encoded_id = url.path.removeprefix("/api/conversations/")
            if not encoded_id or "/" in encoded_id or url.query:
                self._send_json({"error": {"message": "Invalid conversation identifier"}}, status=400)
                return
            try:
                conversation_id = unquote(encoded_id, errors="strict")
                self._send_json({"data": backend.conversations.get(conversation_id)})
            except ConversationError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
            except UnicodeDecodeError:
                self._send_json({"error": {"message": "Invalid conversation identifier"}}, status=400)

        elif url.path == "/api/knowledge/library/documents":
            try:
                query = parse_qs(url.query, keep_blank_values=True, strict_parsing=True)
                if set(query) - {"project_id"} or any(len(values) != 1 for values in query.values()):
                    raise LocalKnowledgeError("invalid knowledge scope")
                raw_project_id = query.get("project_id", ["*"])[0]
                project_id = None if raw_project_id == "" else raw_project_id
                backend.validate_knowledge_project(project_id, allow_all=True)
                self._send_json({"data": backend.local_knowledge.list_documents(project_id=project_id)})
            except ValueError as exc:
                if isinstance(exc, LocalKnowledgeError):
                    self._send_json({"error": {"message": str(exc)}}, status=exc.status)
                else:
                    self._send_json({"error": {"message": "invalid knowledge scope"}}, status=400)
            except LocalKnowledgeError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)

        elif url.path == "/api/engineering/status":
            if url.query:
                self._send_json(
                    {"error": {"message": "The engineering status route does not accept query parameters"}},
                    status=400,
                )
                return
            self._send_json({"configured": backend.engineering_jobs is not None})

        elif url.path == "/api/engineering/entitlements":
            if backend.engineering_jobs is None:
                self._send_json(
                    {"error": {"message": "The zGPU Engineering service is not configured"}}, status=503
                )
                return
            if url.query:
                self._send_json(
                    {"error": {"message": "Engineering entitlements do not accept query parameters"}},
                    status=400,
                )
                return
            try:
                result = backend.get_engineering_entitlements()
            except EngineeringJobsError as exc:
                log.warning("zGPU engineering entitlement lookup failed: %s", exc.code)
                status = 403 if exc.status == 403 else 502
                self._send_json(
                    {"error": {"message": "The zGPU Engineering service could not return entitlements"}},
                    status=status,
                )
                return
            values = result.get("entitlements") if isinstance(result, dict) else None
            if not isinstance(values, dict):
                self._send_json(
                    {"error": {"message": "The zGPU Engineering service returned invalid entitlements"}},
                    status=502,
                )
                return
            safe_values: dict[str, Any] = {}
            for field in (
                "version",
                "max_projects",
                "max_repositories",
                "monthly_budget_usd",
                "concurrent_jobs",
                "managed_agents",
                "multiagent_orchestration",
                "scim_enabled",
                "sso_oidc_enabled",
            ):
                value = values.get(field)
                if (field == "version" and isinstance(value, str) and len(value) <= 128) or (
                    field
                    in {
                        "managed_agents",
                        "multiagent_orchestration",
                        "scim_enabled",
                        "sso_oidc_enabled",
                    }
                    and isinstance(value, bool)
                ):
                    safe_values[field] = value
                elif (
                    field == "monthly_budget_usd"
                    and isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and math.isfinite(value)
                    and value >= 0
                ):
                    safe_values[field] = float(value)
                elif (
                    field in {"max_projects", "max_repositories", "concurrent_jobs"}
                    and isinstance(value, int)
                    and not isinstance(value, bool)
                    and value >= 0
                ):
                    safe_values[field] = value
            self._send_json({"data": safe_values})

        elif url.path == "/api/engineering/jobs":
            if backend.engineering_jobs is None:
                self._send_json(
                    {"error": {"message": "The zGPU Engineering service is not configured"}}, status=503
                )
                return
            try:
                query = parse_qs(url.query, keep_blank_values=True, strict_parsing=True)
            except ValueError:
                self._send_json({"error": {"message": "Invalid engineering job query"}}, status=400)
                return
            if any(len(values) != 1 for values in query.values()) or set(query) - {"limit", "offset"}:
                self._send_json({"error": {"message": "Invalid engineering job query"}}, status=400)
                return
            try:
                limit = int(query.get("limit", ["20"])[0])
                offset = int(query.get("offset", ["0"])[0])
                if not 1 <= limit <= 100 or offset < 0:
                    raise ValueError
                result = backend.list_engineering_jobs(limit=limit, offset=offset)
            except (ValueError, TypeError):
                self._send_json(
                    {"error": {"message": "limit must be 1-100 and offset must be non-negative"}}, status=400
                )
                return
            except EngineeringJobsError:
                log.exception("zGPU engineering jobs request failed")
                self._send_json(
                    {"error": {"message": "The zGPU Engineering service could not return jobs"}}, status=502
                )
                return
            rows = result.get("data")
            pagination = result.get("pagination")
            if not isinstance(rows, list) or len(rows) > limit or not isinstance(pagination, dict):
                self._send_json(
                    {"error": {"message": "The zGPU Engineering service returned invalid job data"}},
                    status=502,
                )
                return
            total = pagination.get("total")
            has_more = pagination.get("has_more")
            if (
                isinstance(pagination.get("limit"), bool)
                or not isinstance(pagination.get("limit"), int)
                or pagination.get("limit") != limit
                or isinstance(pagination.get("offset"), bool)
                or not isinstance(pagination.get("offset"), int)
                or pagination.get("offset") != offset
                or isinstance(total, bool)
                or not isinstance(total, int)
                or total < len(rows)
                or not isinstance(has_more, bool)
                or has_more != (offset + len(rows) < total)
            ):
                self._send_json(
                    {"error": {"message": "The zGPU Engineering service returned invalid pagination"}},
                    status=502,
                )
                return
            fields = ("id", "task", "status", "runtime", "model", "created_at", "updated_at", "project_id")
            safe_rows = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                safe_row = {
                    key: value[:500] if isinstance(value, str) else value
                    for key in fields
                    if isinstance((value := row.get(key)), (str, int, type(None)))
                    and not isinstance(value, bool)
                }
                safe_rows.append(safe_row)
            safe_pagination = {"limit": limit, "offset": offset, "total": total, "has_more": has_more}
            self._send_json({"data": safe_rows, "pagination": safe_pagination})

        elif url.path.startswith("/api/engineering/jobs/"):
            if backend.engineering_jobs is None:
                self._send_json(
                    {"error": {"message": "The zGPU Engineering service is not configured"}}, status=503
                )
                return
            encoded_id = url.path.removeprefix("/api/engineering/jobs/")
            if not encoded_id or "/" in encoded_id:
                self._send_json({"error": {"message": "Invalid engineering job identifier"}}, status=400)
                return
            try:
                job_id = unquote(encoded_id, errors="strict")
                result = backend.get_engineering_job(job_id)
            except (UnicodeDecodeError, ValueError):
                self._send_json({"error": {"message": "Invalid engineering job identifier"}}, status=400)
                return
            except EngineeringJobsError as exc:
                log.exception("zGPU engineering job detail request failed")
                status = 404 if exc.status == 404 else 502
                self._send_json(
                    {"error": {"message": "The zGPU Engineering service could not return this job"}},
                    status=status,
                )
                return
            if not isinstance(result, dict) or result.get("id") != job_id:
                self._send_json(
                    {"error": {"message": "The zGPU Engineering service returned invalid job data"}},
                    status=502,
                )
                return
            fields = ("id", "task", "status", "runtime", "model", "created_at", "updated_at", "project_id")
            safe_job = {
                key: value[:500] if isinstance(value, str) else value
                for key in fields
                if isinstance((value := result.get(key)), (str, int, type(None)))
                and not isinstance(value, bool)
            }
            self._send_json({"data": safe_job})

        else:
            self.send_error(404, "File Not Found")

    def do_POST(self):
        if not self._validate_request_origin(require_custom_header=True):
            return
        url = urlparse(self.path)
        try:
            length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            self._send_json({"error": {"message": "Invalid Content-Length"}}, status=400)
            return
        if length < 0 or length > 1_048_576:
            self._send_json({"error": {"message": "Request body must be at most 1 MiB"}}, status=413)
            return
        try:
            raw_body = self.rfile.read(length).decode("utf-8")
            payload = json.loads(raw_body) if raw_body else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json({"error": {"message": "Request body must be UTF-8 JSON"}}, status=400)
            return
        if not isinstance(payload, dict):
            self._send_json({"error": {"message": "Request body must be a JSON object"}}, status=400)
            return
        if url.path == "/api/models/local/manifest":
            try:
                if url.query or payload:
                    raise LocalModelCatalogError("model manifest request must have an empty JSON object")
                self._send_json(backend.local_model_catalog.create_integrity_manifest())
            except LocalModelCatalogError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
            return
        if "zgpu_tools" in payload and not isinstance(payload["zgpu_tools"], bool):
            self._send_json({"error": {"message": "'zgpu_tools' must be a boolean"}}, status=400)
            return
        if payload.get("zgpu_tools") is False:
            payload.pop("zgpu_tools")

        if url.path == "/api/chat/completions":
            try:
                if payload.get("stream") is True:
                    self._stream_chat_completion(payload)
                    return
                if payload.get("zgpu_tools") is True:
                    self._send_json(backend.create_tool_completion(payload))
                else:
                    self._send_json(backend.chat_api.create_completion(payload))
            except CompletionRequestError as exc:
                self._send_json({"error": {"message": str(exc), "type": "invalid_request_error"}}, status=400)
            except LlamaCppError as exc:
                log.warning("zGPU local model request failed: %s", exc)
                self._send_json({"error": {"message": str(exc), "type": "service_unavailable"}}, status=502)
            except OpenAIProviderError as exc:
                log.warning("zGPU remote model provider request failed: %s", exc)
                self._send_json({"error": {"message": str(exc), "type": "service_unavailable"}}, status=502)
            except Exception:
                log.exception("Dashboard chat completion failed")
                self._send_json(
                    {"error": {"message": "The zGPU simulator could not complete the request"}}, status=500
                )
            return

        if url.path == "/api/isa/assemble":
            if url.query or set(payload) != {"source"}:
                self._send_json(
                    {"error": {"message": "request must contain source and no query parameters"}}, status=400
                )
                return
            try:
                self._send_json({"data": assemble_source(payload["source"])})
            except ZISAAssemblyError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
            return

        if url.path == "/api/isa/compile-expression":
            if url.query or set(payload) != {"expression"}:
                self._send_json(
                    {"error": {"message": "request must contain only expression and no query parameters"}},
                    status=400,
                )
                return
            try:
                expression = payload["expression"]
                source = AstJitCompiler.compile_expression(expression)
                assembled = assemble_source(source)
                self._send_json(
                    {
                        "data": {
                            "expression": expression,
                            "compiler": "zGPU restricted Python AST compiler",
                            "execution": "not-run",
                            "assembly": source,
                            **assembled,
                        }
                    }
                )
            except (ValueError, ZISAAssemblyError) as exc:
                status = exc.status if isinstance(exc, ZISAAssemblyError) else 400
                self._send_json({"error": {"message": str(exc)}}, status=status)
            return

        if url.path == "/api/isa/run-expression":
            allowed_fields = {"expression", "a", "b", "max_cycles"}
            if url.query or set(payload) - allowed_fields or not {"expression", "a", "b"} <= set(payload):
                self._send_json(
                    {"error": {"message": "request must contain expression, a, b, and optional max_cycles"}},
                    status=400,
                )
                return
            try:
                result = simulate_elementwise_expression(
                    payload["expression"],
                    payload["a"],
                    payload["b"],
                    max_cycles=payload.get("max_cycles", 10_000),
                )
                self._send_json({"data": result})
            except (ZISAAssemblyError, ZISASimulationError) as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
            return

        if url.path == "/api/isa/simulate":
            allowed_fields = {"source", "inputs", "output_registers", "max_cycles"}
            if url.query or set(payload) - allowed_fields or "source" not in payload:
                self._send_json(
                    {
                        "error": {
                            "message": "request must contain source and only supported simulator options"
                        }
                    },
                    status=400,
                )
                return
            try:
                result = simulate_source(
                    payload["source"],
                    inputs=payload.get("inputs"),
                    output_registers=payload.get("output_registers"),
                    max_cycles=payload.get("max_cycles", 10_000),
                )
                self._send_json({"data": result})
            except (ZISAAssemblyError, ZISASimulationError) as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
            return

        if url.path == "/api/projects":
            try:
                if url.query or set(payload) != {"name"}:
                    raise ConversationError("request must contain only a project name")
                project = backend.conversations.create_project(payload["name"])
                self._send_json({"data": project}, status=201)
            except ConversationError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
            return

        if url.path.startswith("/api/projects/"):
            encoded_id = url.path.removeprefix("/api/projects/")
            if not encoded_id or "/" in encoded_id or url.query:
                self._send_json({"error": {"message": "Invalid project identifier"}}, status=400)
                return
            try:
                project_id = unquote(encoded_id, errors="strict")
                if set(payload) != {"name"}:
                    raise ConversationError("request must contain only a project name")
                project = backend.conversations.rename_project(project_id, payload["name"])
                self._send_json({"data": project})
            except ConversationError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
            except UnicodeDecodeError:
                self._send_json({"error": {"message": "Invalid project identifier"}}, status=400)
            return

        if url.path == "/api/conversations":
            try:
                if url.query:
                    raise ConversationError("conversation creation does not accept query parameters")
                if set(payload) - {"title", "model", "project_id", "assistant_id"}:
                    raise ConversationError("unsupported conversation fields")
                assistant_id = payload.get("assistant_id")
                if assistant_id is not None:
                    backend.assistants.get(assistant_id)
                conversation = backend.conversations.create(
                    payload.get("title", "New chat"),
                    payload.get("model", ""),
                    payload.get("project_id"),
                    assistant_id,
                )
                self._send_json({"data": conversation}, status=201)
            except ConversationError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
            except AssistantProfileError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
            return

        if url.path == "/api/assistants":
            try:
                if url.query or set(payload) != {"name", "description", "system_prompt"}:
                    raise AssistantProfileError(
                        "request must contain name, description, system_prompt and no query parameters"
                    )
                profile = backend.assistants.create(
                    payload["name"], payload["description"], payload["system_prompt"]
                )
                self._send_json({"data": profile}, status=201)
            except AssistantProfileError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
            return

        if url.path.startswith("/api/assistants/"):
            encoded_id = url.path.removeprefix("/api/assistants/")
            if not encoded_id or "/" in encoded_id or url.query:
                self._send_json({"error": {"message": "Invalid assistant profile identifier"}}, status=400)
                return
            try:
                profile_id = unquote(encoded_id, errors="strict")
                if set(payload) != {"name", "description", "system_prompt"}:
                    raise AssistantProfileError("request must contain name, description and system_prompt")
                self._send_json(
                    {
                        "data": backend.assistants.update(
                            profile_id, payload["name"], payload["description"], payload["system_prompt"]
                        )
                    }
                )
            except AssistantProfileError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
            except UnicodeDecodeError:
                self._send_json({"error": {"message": "Invalid assistant profile identifier"}}, status=400)
            return

        if url.path == "/api/prompts":
            try:
                if url.query:
                    raise PromptLibraryError("prompt creation does not accept query parameters")
                if set(payload) != {"title", "content"}:
                    raise PromptLibraryError("request must contain only title and content")
                prompt = backend.prompts.create(payload["title"], payload["content"])
                self._send_json({"data": prompt}, status=201)
            except PromptLibraryError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
            return

        if url.path == "/api/notes":
            try:
                if url.query:
                    raise WorkspaceNotesError("note creation does not accept query parameters")
                if set(payload) - {"title", "content", "project_id"} or not {"title", "content"} <= set(
                    payload
                ):
                    raise WorkspaceNotesError(
                        "request must contain title and content, with optional project_id"
                    )
                project_id = payload.get("project_id")
                if project_id == "":
                    project_id = None
                if project_id is not None:
                    backend.validate_knowledge_project(project_id)
                note = backend.notes.create(payload["title"], payload["content"], project_id=project_id)
                self._send_json({"data": note}, status=201)
            except WorkspaceNotesError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
            except LocalKnowledgeError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
            return

        if url.path.startswith("/api/notes/"):
            encoded_id = url.path.removeprefix("/api/notes/")
            if not encoded_id or "/" in encoded_id or url.query:
                self._send_json({"error": {"message": "Invalid workspace note identifier"}}, status=400)
                return
            try:
                note_id = unquote(encoded_id, errors="strict")
                if set(payload) - {"title", "content", "project_id"} or not {"title", "content"} <= set(
                    payload
                ):
                    raise WorkspaceNotesError(
                        "request must contain title and content, with optional project_id"
                    )
                project_id = (
                    payload.get("project_id")
                    if "project_id" in payload
                    else backend.notes.get(note_id)["project_id"]
                )
                if project_id is not None:
                    backend.validate_knowledge_project(project_id)
                note = backend.notes.update(
                    note_id, payload["title"], payload["content"], project_id=project_id
                )
                self._send_json({"data": note})
            except WorkspaceNotesError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
            except LocalKnowledgeError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
            except UnicodeDecodeError:
                self._send_json({"error": {"message": "Invalid workspace note identifier"}}, status=400)
            return

        if url.path.startswith("/api/prompts/"):
            encoded_id = url.path.removeprefix("/api/prompts/")
            if not encoded_id or "/" in encoded_id or url.query:
                self._send_json({"error": {"message": "Invalid prompt identifier"}}, status=400)
                return
            try:
                prompt_id = unquote(encoded_id, errors="strict")
                if set(payload) != {"title", "content"}:
                    raise PromptLibraryError("request must contain only title and content")
                prompt = backend.prompts.update(prompt_id, payload["title"], payload["content"])
                self._send_json({"data": prompt})
            except PromptLibraryError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
            except UnicodeDecodeError:
                self._send_json({"error": {"message": "Invalid prompt identifier"}}, status=400)
            return

        if url.path.startswith("/api/conversations/") and url.path.endswith("/project"):
            encoded_id = url.path.removeprefix("/api/conversations/").removesuffix("/project")
            if not encoded_id or encoded_id.endswith("/") or "/" in encoded_id or url.query:
                self._send_json({"error": {"message": "Invalid conversation identifier"}}, status=400)
                return
            try:
                conversation_id = unquote(encoded_id, errors="strict")
                if set(payload) != {"project_id"}:
                    raise ConversationError("request must contain only project_id")
                conversation = backend.conversations.assign_project(conversation_id, payload["project_id"])
                self._send_json({"data": conversation})
            except ConversationError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
            except UnicodeDecodeError:
                self._send_json({"error": {"message": "Invalid conversation identifier"}}, status=400)
            return

        if url.path.startswith("/api/conversations/") and url.path.endswith("/assistant"):
            encoded_id = url.path.removeprefix("/api/conversations/").removesuffix("/assistant")
            if not encoded_id or encoded_id.endswith("/") or "/" in encoded_id or url.query:
                self._send_json({"error": {"message": "Invalid conversation identifier"}}, status=400)
                return
            try:
                conversation_id = unquote(encoded_id, errors="strict")
                if set(payload) != {"assistant_id"}:
                    raise ConversationError("request must contain only assistant_id")
                assistant_id = payload["assistant_id"]
                if assistant_id is not None:
                    backend.assistants.get(assistant_id)
                self._send_json(
                    {"data": backend.conversations.assign_assistant(conversation_id, assistant_id)}
                )
            except ConversationError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
            except AssistantProfileError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
            except UnicodeDecodeError:
                self._send_json({"error": {"message": "Invalid conversation identifier"}}, status=400)
            return

        if url.path.startswith("/api/conversations/") and url.path.endswith("/title"):
            encoded_id = url.path.removeprefix("/api/conversations/").removesuffix("/title")
            if not encoded_id or encoded_id.endswith("/") or "/" in encoded_id or url.query:
                self._send_json({"error": {"message": "Invalid conversation identifier"}}, status=400)
                return
            try:
                conversation_id = unquote(encoded_id, errors="strict")
                if set(payload) != {"title"}:
                    raise ConversationError("request must contain only title")
                conversation = backend.conversations.rename(conversation_id, payload["title"])
                self._send_json({"data": conversation})
            except ConversationError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
            except UnicodeDecodeError:
                self._send_json({"error": {"message": "Invalid conversation identifier"}}, status=400)
            return

        if url.path.startswith("/api/conversations/") and url.path.endswith("/messages"):
            encoded_id = url.path.removeprefix("/api/conversations/").removesuffix("/messages")
            if not encoded_id or encoded_id.endswith("/") or "/" in encoded_id or url.query:
                self._send_json({"error": {"message": "Invalid conversation identifier"}}, status=400)
                return
            try:
                conversation_id = unquote(encoded_id, errors="strict")
                if set(payload) - {"messages", "model"} or "messages" not in payload:
                    raise ConversationError("request must contain messages and an optional model")
                conversation = backend.conversations.append_messages(
                    conversation_id, payload["messages"], model=payload.get("model")
                )
                self._send_json({"data": conversation})
            except ConversationError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
            except UnicodeDecodeError:
                self._send_json({"error": {"message": "Invalid conversation identifier"}}, status=400)
            return

        if url.path == "/api/knowledge/sessions":
            try:
                session_id = backend.create_knowledge_session()
                self._send_json({"session_id": session_id})
            except KnowledgeChatError as exc:
                self._send_json({"error": {"message": str(exc), "code": exc.code}}, status=exc.status)
            return

        if url.path == "/api/knowledge/base/ingest":
            if backend.knowledge_base is None:
                self._send_json(
                    {"error": {"message": "The connected knowledge service is not configured"}}, status=503
                )
                return
            if url.query or set(payload) != {"filename", "file_base64"}:
                self._send_json(
                    {"error": {"message": "request must contain only filename and file_base64"}}, status=400
                )
                return
            encoded = payload["file_base64"]
            max_encoded_bytes = ((MAX_UPLOAD_BYTES + 2) // 3) * 4
            if not isinstance(encoded, str) or len(encoded) > max_encoded_bytes:
                self._send_json(
                    {"error": {"message": "uploaded file exceeds the encoded size limit"}}, status=413
                )
                return
            try:
                file_bytes = base64.b64decode(encoded, validate=True)
                if len(file_bytes) > MAX_UPLOAD_BYTES:
                    self._send_json(
                        {"error": {"message": "uploaded file exceeds the size limit"}}, status=413
                    )
                    return
                KnowledgeBaseClient.validate_upload(payload["filename"], file_bytes)
                result = backend.knowledge_base.ingest_file(payload["filename"], file_bytes)
                self._send_json({"data": result}, status=202)
            except (binascii.Error, ValueError) as exc:
                self._send_json(
                    {"error": {"message": str(exc) or "file_base64 must contain valid base64 data"}},
                    status=400,
                )
            except KnowledgeBaseError as exc:
                status = exc.status if exc.status in {400, 409, 413, 415, 422} else 502
                log.warning("zGPU Knowledge Base ingestion request failed: %s", exc.code)
                self._send_json({"error": {"message": str(exc)}}, status=status)
            return

        if url.path == "/api/knowledge/library/documents":
            try:
                allowed_fields = {"title", "content", "project_id", "filename", "file_base64"}
                if set(payload) - allowed_fields:
                    raise LocalKnowledgeError("request contains unsupported document fields")
                project_id = payload.get("project_id")
                backend.validate_knowledge_project(project_id)
                if "filename" in payload or "file_base64" in payload:
                    if not {"filename", "file_base64"} <= set(payload) or "content" in payload:
                        raise LocalKnowledgeError(
                            "file uploads require filename and file_base64 without content"
                        )
                    filename = payload["filename"]
                    encoded = payload["file_base64"]
                    max_encoded_bytes = ((MAX_UPLOAD_BYTES + 2) // 3) * 4
                    if not isinstance(encoded, str) or len(encoded) > max_encoded_bytes:
                        raise DocumentLoadError("uploaded file exceeds the encoded size limit", status=413)
                    try:
                        file_bytes = base64.b64decode(encoded, validate=True)
                    except (binascii.Error, ValueError) as exc:
                        raise DocumentLoadError("file_base64 must contain valid base64 data") from exc
                    content = extract_document_text(filename, file_bytes)
                    title = payload.get("title") or Path(filename).name
                else:
                    if set(payload) - {"title", "content", "project_id"} or not {"title", "content"} <= set(
                        payload
                    ):
                        raise LocalKnowledgeError(
                            "request must contain title, content, and optional project_id"
                        )
                    title = payload["title"]
                    content = payload["content"]
                document = backend.local_knowledge.add_document(title, content, project_id=project_id)
                self._send_json({"data": document}, status=201)
            except DocumentLoadError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
            except LocalKnowledgeError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
            return

        if url.path == "/api/knowledge/reindex":
            try:
                if url.query or set(payload) - {"limit", "project_id"}:
                    raise LocalKnowledgeError("request accepts only limit and project_id")
                limit = payload.get("limit", 5)
                project_id = payload.get("project_id", "*")
                project_id = None if project_id == "" else project_id
                backend.validate_knowledge_project(project_id, allow_all=True)
                result = backend.local_knowledge.reindex_missing(limit=limit, project_id=project_id)
                self._send_json({"data": result})
            except LocalKnowledgeError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
            return

        if url.path == "/api/knowledge/library/search":
            try:
                if set(payload) - {"query", "limit", "project_id"}:
                    self._send_json(
                        {"error": {"message": "Request must contain only query, limit, and project_id"}},
                        status=400,
                    )
                    return
                limit = payload.get("limit", 10)
                project_id = payload.get("project_id")
                backend.validate_knowledge_project(project_id, allow_all=True)
                local_results = backend.local_knowledge.search(
                    payload.get("query"), limit=limit, project_id=project_id
                )
                connected_results = []
                warning = None
                if backend.knowledge_base is not None:
                    try:
                        connected_results = backend.knowledge_base.search(
                            payload.get("query"), top_k=min(limit, 5)
                        )
                    except KnowledgeBaseError as exc:
                        log.warning("zGPU connected knowledge search failed: %s", exc.code)
                        warning = "The connected knowledge service could not be searched; local results are still shown."
                results = []
                for index in range(max(len(local_results), len(connected_results))):
                    if index < len(local_results):
                        results.append({**local_results[index], "source": "local"})
                    if index < len(connected_results):
                        results.append(
                            {
                                **connected_results[index],
                                "sha256": None,
                                "project_id": None,
                                "source": "connected",
                            }
                        )
                self._send_json(
                    {
                        "data": results,
                        "retrieval": backend.local_knowledge.retrieval_mode,
                        "connected": backend.knowledge_base is not None,
                        "warning": warning,
                    }
                )
            except LocalKnowledgeError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
            return

        if url.path == "/api/engineering/jobs":
            if backend.engineering_jobs is None:
                self._send_json(
                    {"error": {"message": "The zGPU Engineering service is not configured"}}, status=503
                )
                return
            allowed_fields = {"task", "runtime", "model", "budget_usd"}
            if set(payload) - allowed_fields:
                self._send_json({"error": {"message": "Unsupported engineering job fields"}}, status=400)
                return
            idempotency_key = self.headers.get("Idempotency-Key")
            if idempotency_key is not None and (
                not idempotency_key.strip()
                or len(idempotency_key) > 256
                or any(ord(ch) < 32 for ch in idempotency_key)
            ):
                self._send_json({"error": {"message": "Invalid Idempotency-Key"}}, status=400)
                return
            try:
                result = backend.submit_engineering_job(
                    payload.get("task"),
                    runtime=payload.get("runtime", "direct"),
                    model=payload.get("model"),
                    budget_usd=payload.get("budget_usd", 0.0),
                    idempotency_key=idempotency_key,
                )
            except (ValueError, TypeError) as exc:
                self._send_json({"error": {"message": str(exc)}}, status=400)
                return
            except EngineeringJobsError:
                log.exception("zGPU engineering job submission failed")
                self._send_json(
                    {"error": {"message": "The zGPU Engineering service could not submit this job"}},
                    status=502,
                )
                return
            if (
                not isinstance(result, dict)
                or not isinstance(result.get("id"), str)
                or not isinstance(result.get("status"), str)
            ):
                self._send_json(
                    {"error": {"message": "The zGPU Engineering service returned invalid job data"}},
                    status=502,
                )
                return
            fields = ("id", "task", "status", "runtime", "model", "created_at", "updated_at", "project_id")
            safe_job = {
                key: value[:500] if isinstance(value, str) else value
                for key in fields
                if isinstance((value := result.get(key)), (str, int, type(None)))
                and not isinstance(value, bool)
            }
            self._send_json({"data": safe_job}, status=201)
            return

        if url.path == "/api/knowledge/chat":
            try:
                if backend.knowledge_chat is None:
                    raise KnowledgeChatError(503, "NOT_CONFIGURED", "Knowledge chat is not configured")
                self._stream_knowledge_chat(payload)
            except (KeyError, TypeError, ValueError):
                self._send_json({"error": {"message": "Invalid zGPU knowledge chat request"}}, status=400)
            except KnowledgeChatError as exc:
                self._send_json({"error": {"message": str(exc), "code": exc.code}}, status=exc.status)
            return

        if url.path == "/api/llm/generate":
            prompt = payload.get("prompt", "Hello")
            max_tokens = int(payload.get("max_tokens", 16))
            result = backend.generate_llm(prompt=prompt, max_tokens=max_tokens)
            self._send_json(result)

        elif url.path == "/api/self_coding/synthesize":
            name = payload.get("name", "custom_kernel")
            op = payload.get("op", "fadd")
            result = backend.trigger_self_coding(name, op)
            self._send_json(result)

        elif url.path == "/api/agi/step":
            goal = payload.get("goal", "Execute task")
            result = backend.trigger_agi_step(goal)
            self._send_json(result)

        elif url.path == "/api/cluster/scan":
            subnet = payload.get("subnet", "127.0.0")
            start = int(payload.get("start", 1))
            end = int(payload.get("end", 2))
            result = backend.trigger_network_scan(subnet_prefix=subnet, start=start, end=end)
            self._send_json(result)

        elif url.path == "/api/cluster/hybrid_gemm":
            size = int(payload.get("size", 16))
            fraction = float(payload.get("gpu_fraction", 0.5))
            result = backend.trigger_hybrid_gemm(size=size, gpu_fraction=fraction)
            self._send_json(result)

        else:
            self.send_error(404, "Endpoint Not Found")

    def do_DELETE(self):
        if not self._validate_request_origin(require_custom_header=True):
            return
        if self.headers.get("Content-Length", "0") != "0":
            self._send_json({"error": {"message": "DELETE requests cannot contain a body"}}, status=400)
            return
        url = urlparse(self.path)
        if url.path.startswith("/api/assistants/"):
            encoded_id = url.path.removeprefix("/api/assistants/")
            if not encoded_id or "/" in encoded_id or url.query:
                self._send_json({"error": {"message": "Invalid assistant profile identifier"}}, status=400)
                return
            try:
                profile_id = unquote(encoded_id, errors="strict")
                backend.assistants.get(profile_id)
                backend.conversations.detach_assistant(profile_id)
                deleted = backend.assistants.delete(profile_id)
            except AssistantProfileError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
                return
            except UnicodeDecodeError:
                self._send_json({"error": {"message": "Invalid assistant profile identifier"}}, status=400)
                return
            if not deleted:
                self._send_json({"error": {"message": "assistant profile not found"}}, status=404)
                return
            self._send_json({"deleted": True})
            return
        project_prefix = "/api/projects/"
        if url.path.startswith(project_prefix):
            encoded_id = url.path.removeprefix(project_prefix)
            if not encoded_id or "/" in encoded_id or url.query:
                self._send_json({"error": {"message": "Invalid project identifier"}}, status=400)
                return
            try:
                project_id = unquote(encoded_id, errors="strict")
                backend.validate_knowledge_project(project_id)
                backend.notes.detach_project(project_id)
                backend.local_knowledge.detach_project(project_id)
                deleted = backend.conversations.delete_project(project_id)
            except LocalKnowledgeError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
                return
            except WorkspaceNotesError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
                return
            except ConversationError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
                return
            except UnicodeDecodeError:
                self._send_json({"error": {"message": "Invalid project identifier"}}, status=400)
                return
            if not deleted:
                self._send_json({"error": {"message": "project not found"}}, status=404)
                return
            self._send_json({"deleted": True})
            return
        prompt_prefix = "/api/prompts/"
        if url.path.startswith(prompt_prefix):
            encoded_id = url.path.removeprefix(prompt_prefix)
            if not encoded_id or "/" in encoded_id or url.query:
                self._send_json({"error": {"message": "Invalid prompt identifier"}}, status=400)
                return
            try:
                prompt_id = unquote(encoded_id, errors="strict")
                deleted = backend.prompts.delete(prompt_id)
            except PromptLibraryError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
                return
            except UnicodeDecodeError:
                self._send_json({"error": {"message": "Invalid prompt identifier"}}, status=400)
                return
            if not deleted:
                self._send_json({"error": {"message": "prompt not found"}}, status=404)
                return
            self._send_json({"deleted": True})
            return
        notes_prefix = "/api/notes/"
        if url.path.startswith(notes_prefix):
            encoded_id = url.path.removeprefix(notes_prefix)
            if not encoded_id or "/" in encoded_id or url.query:
                self._send_json({"error": {"message": "Invalid workspace note identifier"}}, status=400)
                return
            try:
                note_id = unquote(encoded_id, errors="strict")
                deleted = backend.notes.delete(note_id)
            except WorkspaceNotesError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
                return
            except UnicodeDecodeError:
                self._send_json({"error": {"message": "Invalid workspace note identifier"}}, status=400)
                return
            if not deleted:
                self._send_json({"error": {"message": "workspace note not found"}}, status=404)
                return
            self._send_json({"deleted": True})
            return
        conversation_prefix = "/api/conversations/"
        if url.path.startswith(conversation_prefix):
            encoded_id = url.path.removeprefix(conversation_prefix)
            if not encoded_id or "/" in encoded_id or url.query:
                self._send_json({"error": {"message": "Invalid conversation identifier"}}, status=400)
                return
            try:
                conversation_id = unquote(encoded_id, errors="strict")
                deleted = backend.conversations.delete(conversation_id)
            except ConversationError as exc:
                self._send_json({"error": {"message": str(exc)}}, status=exc.status)
                return
            except UnicodeDecodeError:
                self._send_json({"error": {"message": "Invalid conversation identifier"}}, status=400)
                return
            if not deleted:
                self._send_json({"error": {"message": "conversation not found"}}, status=404)
                return
            self._send_json({"deleted": True})
            return
        knowledge_job_prefix = "/api/knowledge/base/jobs/"
        if url.path.startswith(knowledge_job_prefix):
            if backend.knowledge_base is None:
                self._send_json(
                    {"error": {"message": "The connected knowledge service is not configured"}}, status=503
                )
                return
            encoded_id = url.path.removeprefix(knowledge_job_prefix)
            if not encoded_id or "/" in encoded_id or url.query:
                self._send_json(
                    {"error": {"message": "Invalid connected ingestion job identifier"}}, status=400
                )
                return
            try:
                backend.knowledge_base.cancel_ingestion_job(unquote(encoded_id, errors="strict"))
            except (UnicodeDecodeError, ValueError):
                self._send_json(
                    {"error": {"message": "Invalid connected ingestion job identifier"}}, status=400
                )
                return
            except KnowledgeBaseError as exc:
                status = exc.status if exc.status in {404, 409} else 502
                log.warning("zGPU Knowledge Base job cancellation failed: %s", exc.code)
                self._send_json(
                    {"error": {"message": "The connected ingestion job could not be cancelled"}},
                    status=status,
                )
                return
            self._send_json({"cancelled": True})
            return

        engineering_prefix = "/api/engineering/jobs/"
        if url.path.startswith(engineering_prefix):
            if backend.engineering_jobs is None:
                self._send_json(
                    {"error": {"message": "The zGPU Engineering service is not configured"}}, status=503
                )
                return
            encoded_id = url.path.removeprefix(engineering_prefix)
            if not encoded_id or "/" in encoded_id or url.query:
                self._send_json({"error": {"message": "Invalid engineering job identifier"}}, status=400)
                return
            try:
                job_id = unquote(encoded_id, errors="strict")
            except UnicodeDecodeError:
                self._send_json({"error": {"message": "Invalid engineering job identifier"}}, status=400)
                return
            idempotency_key = self.headers.get("Idempotency-Key")
            if idempotency_key is not None and (
                not idempotency_key.strip()
                or len(idempotency_key) > 256
                or any(ord(character) < 32 for character in idempotency_key)
            ):
                self._send_json({"error": {"message": "Invalid idempotency key"}}, status=400)
                return
            try:
                result = backend.cancel_engineering_job(job_id, idempotency_key=idempotency_key)
            except EngineeringJobsError as exc:
                log.exception("zGPU engineering job cancellation failed")
                status = 404 if exc.status == 404 else 403 if exc.status == 403 else 502
                self._send_json(
                    {"error": {"message": "The zGPU Engineering service could not cancel this job"}},
                    status=status,
                )
                return
            if (
                not isinstance(result, dict)
                or result.get("id") != job_id
                or not isinstance(result.get("status"), str)
            ):
                self._send_json(
                    {"error": {"message": "The zGPU Engineering service returned invalid cancellation data"}},
                    status=502,
                )
                return
            fields = ("id", "task", "status", "runtime", "model", "created_at", "updated_at", "project_id")
            safe_job = {
                key: value[:500] if isinstance(value, str) else value
                for key in fields
                if isinstance((value := result.get(key)), (str, int, type(None)))
                and not isinstance(value, bool)
            }
            self._send_json({"data": safe_job})
            return
        prefix = "/api/knowledge/library/documents/"
        if not url.path.startswith(prefix) or "/" in url.path.removeprefix(prefix):
            self.send_error(404, "Endpoint Not Found")
            return
        document_id = unquote(url.path.removeprefix(prefix), errors="replace")
        try:
            deleted = backend.local_knowledge.delete_document(document_id)
        except LocalKnowledgeError as exc:
            self._send_json({"error": {"message": str(exc)}}, status=exc.status)
            return
        if not deleted:
            self._send_json({"error": {"message": "Knowledge document not found"}}, status=404)
            return
        self._send_json({"deleted": True})

    def _send_json(self, data: Any, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _stream_chat_completion(self, payload: dict[str, Any]) -> None:
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
            if payload.get("zgpu_tools") is True:
                result = backend.create_tool_completion(payload)
                choices = result.get("choices", [])
                message = choices[0].get("message", {}) if choices and isinstance(choices[0], dict) else {}
                content = message.get("content") if isinstance(message, dict) else None
                if not isinstance(content, str):
                    content = ""
                send_event(
                    {
                        "id": result.get("id", f"chatcmpl-{int(time.time())}"),
                        "object": "chat.completion.chunk",
                        "created": result.get("created", int(time.time())),
                        "model": payload.get("model", "zgpu"),
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"role": "assistant", "content": content},
                                "finish_reason": "stop",
                            }
                        ],
                    }
                )
            else:
                backend.chat_api.create_completion(payload, event_callback=send_event)
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except CompletionRequestError as exc:
            if not headers_sent:
                self._send_json({"error": {"message": str(exc), "type": "invalid_request_error"}}, status=400)
                return
            error_event = {"error": {"message": "Invalid zGPU chat request", "type": "invalid_request_error"}}
            data = json.dumps(error_event, separators=(",", ":"))
            self.wfile.write(f"data: {data}\n\n".encode())
            self.wfile.flush()
        except OpenAIProviderError as exc:
            log.warning("zGPU remote model stream failed: %s", exc)
            if not headers_sent:
                self._send_json({"error": {"message": str(exc), "type": "service_unavailable"}}, status=502)
                return
            error_event = {"error": {"message": str(exc), "type": "service_unavailable"}}
            data = json.dumps(error_event, separators=(",", ":"))
            self.wfile.write(f"data: {data}\n\n".encode())
            self.wfile.flush()
        except LlamaCppError as exc:
            log.warning("zGPU local model stream failed: %s", exc)
            if not headers_sent:
                self._send_json({"error": {"message": str(exc), "type": "service_unavailable"}}, status=502)
                return
            error_event = {"error": {"message": str(exc), "type": "service_unavailable"}}
            data = json.dumps(error_event, separators=(",", ":"))
            self.wfile.write(f"data: {data}\n\n".encode())
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            log.info("Client disconnected during zGPU chat stream")
        except Exception:
            log.exception("Dashboard chat stream failed")
            if not headers_sent:
                self._send_json(
                    {"error": {"message": "The zGPU simulator could not complete the request"}}, status=500
                )
                return
            error_event = {"error": {"message": "The zGPU simulator could not complete the request"}}
            data = json.dumps(error_event, separators=(",", ":"))
            self.wfile.write(f"data: {data}\n\n".encode())
            self.wfile.flush()

    def _stream_knowledge_chat(self, payload: dict[str, Any]) -> None:
        client = backend.knowledge_chat
        if client is None:
            raise KnowledgeChatError(503, "NOT_CONFIGURED", "Knowledge chat is not configured")
        session_id = payload.get("session_id")
        message = payload.get("message")
        if not isinstance(session_id, str) or not session_id or len(session_id) > 256:
            raise KnowledgeChatError(400, "INVALID_SESSION", "Invalid zGPU knowledge session")
        if not isinstance(message, str) or not message.strip() or len(message) > 100_000:
            raise KnowledgeChatError(400, "INVALID_MESSAGE", "Invalid zGPU knowledge message")
        packets = client.stream_message(message, session_id, include_citations=True)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        documents: dict[str, dict[str, str]] = {}
        citation_ids: dict[int, str] = {}
        try:
            for packet in packets:
                payload_obj = packet.get("obj", packet)
                if not isinstance(payload_obj, dict):
                    continue
                packet_type = payload_obj.get("type")
                if packet_type == "message_start":
                    final_documents = payload_obj.get("final_documents")
                    if isinstance(final_documents, list):
                        for document in final_documents[:64]:
                            if not isinstance(document, dict):
                                continue
                            document_id = document.get("document_id")
                            title = document.get("semantic_identifier")
                            link = document.get("link")
                            if (
                                isinstance(document_id, str)
                                and document_id
                                and len(document_id) <= 512
                                and isinstance(title, str)
                                and title.strip()
                            ):
                                source = {"title": title.strip()[:300]}
                                if isinstance(link, str):
                                    try:
                                        parsed_link = urlsplit(link)
                                        if (
                                            parsed_link.scheme in {"http", "https"}
                                            and parsed_link.hostname
                                            and not parsed_link.username
                                            and not parsed_link.password
                                            and len(link) <= 2048
                                        ):
                                            source["url"] = link
                                    except ValueError:
                                        pass
                                documents[document_id] = source
                elif packet_type == "citation_info":
                    number = payload_obj.get("citation_number")
                    document_id = payload_obj.get("document_id")
                    if (
                        isinstance(number, int)
                        and not isinstance(number, bool)
                        and 1 <= number <= 1000
                        and isinstance(document_id, str)
                        and len(document_id) <= 512
                    ):
                        citation_ids[number] = document_id
                elif packet_type == "message_delta" and isinstance(payload_obj.get("content"), str):
                    event = {"choices": [{"delta": {"content": payload_obj["content"]}}]}
                    data = json.dumps(event, separators=(",", ":"))
                    self.wfile.write(f"data: {data}\n\n".encode())
                    self.wfile.flush()
                elif packet_type == "error":
                    event = {
                        "error": {"message": "The zGPU knowledge service could not complete the request"}
                    }
                    data = json.dumps(event, separators=(",", ":"))
                    self.wfile.write(f"data: {data}\n\n".encode())
                    self.wfile.flush()
                    return
            citations = [
                {"number": number, **documents[document_id]}
                for number, document_id in sorted(citation_ids.items())
                if document_id in documents
            ][:32]
            if citations:
                event = {"zgpu": {"citations": citations}}
                data = json.dumps(event, separators=(",", ":"))
                self.wfile.write(f"data: {data}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            log.info("Client disconnected during zGPU knowledge chat stream")
        except KnowledgeChatError:
            log.exception("zGPU knowledge integration request failed")
            event = {"error": {"message": "The zGPU knowledge service could not complete the request"}}
            data = json.dumps(event, separators=(",", ":"))
            self.wfile.write(f"data: {data}\n\n".encode())
            self.wfile.flush()
        except Exception:
            log.exception("zGPU knowledge stream failed")
            event = {"error": {"message": "The zGPU knowledge service could not complete the request"}}
            data = json.dumps(event, separators=(",", ":"))
            self.wfile.write(f"data: {data}\n\n".encode())
            self.wfile.flush()

    def log_message(self, format, *args):
        pass


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def run_dashboard(host: str = "127.0.0.1", port: int = 9000):
    require_loopback_host(host, "The dashboard")
    server = ThreadedHTTPServer((host, port), DashboardHTTPHandler)
    log.info("zGPU Control & Telemetry Dashboard running at http://%s:%d/", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        backend.close_optional_services()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9000
    run_dashboard(port=port)
