# UPGRADE-14: Fully Self-Hosted Local AI Stack & Zero-Cost Pipeline

## 1. Overview
Upgrade-14 establishes a 100% self-hosted, offline-capable AI execution architecture for ZCoder without mandatory paid commercial LLM APIs, hosted vector databases, or SaaS infrastructure.

## 2. Subsystem Components
- **Hardware Profiler & Fit Estimator (`local_ai_stack.py`)**: Queries physical/logical CPU cores, total/available RAM (`/proc/meminfo`), and detects NVIDIA/AMD/Apple GPU/VRAM hardware without external dependencies. Conservative fit calculation prevents out-of-memory crashes.
- **Local Model Gateway & Adapters**: Supports local Ollama (`http://127.0.0.1:11434`), vLLM (OpenAI-compatible endpoints), and generic loopback providers.
- **Local Embeddings & RAG Indexer**: Deterministic TF-IDF in-process vector retrieval engine with automatic secret and credential file exclusion.
- **MCP 2026-07-28 Server & Tool Registry**: Implements stdio/in-memory tool registry conforming to the MCP 2026-07-28 specification with strict input schema validation and sandboxed handlers.
- **Autonomous Coding Runtime & Zero-Paid Monitor**: Runs the complete Inspect -> Plan -> Edit -> Test -> Validate cycle offline and verifies zero commercial transport calls.

## 3. Verification
- `pytest tests/test_upgrade14_localai_suite.py`: 5 passed
- Full regression suite: 724 passed, 2 optional skipped
