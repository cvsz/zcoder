# ZCoder

> **AI Coding Platform ระดับองค์กรสำหรับการพัฒนาแบบ Local-First, Self-Hosted, และ Hybrid Cloud**

[![CI](https://github.com/cvsz/zcoder/actions/workflows/ci.yml/badge.svg)](https://github.com/cvsz/zcoder/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Security](https://img.shields.io/badge/Security-SEC--001%20%E2%86%92%20SEC--010%2B-green.svg)](SECURITY.md)

**เวอร์ชันปัจจุบัน:** `1.41.0`

---

## ภาพรวม

ZCoder คือ **Enterprise AI Coding Platform** ที่ออกแบบมาให้ครบ盖 toutes ด้าน ทั้ง CLI, TUI, Web Console, Autonomous Agent Runtime, Local AI Infrastructure, GitHub Orchestration, และ Enterprise Control Plane ใน codebase เดียว

### จุดเด่นหลัก

| คุณสมบัติ | รายละเอียด |
|---|---|
| **Local-First** | รันได้เต็มรูปแบบบน infrastructure ของคุณ ไม่ต้องพึ่ง cloud |
| **Zero-Cost First** | แยก cost classification จาก runtime availability — ไม่ silent fallback ไป paid provider |
| **Provider-Neutral** | รองรับ Anthropic, Gemini, xAI, Ollama, local model พร้อมกัน |
| **Production-Ready** | Durable jobs, policy, tenant isolation, audit, queues, workers, observability, backup/restore |
| **Security-First** | 11 ช่องบ่อน vulnerability ที่ปิดครบ (SEC-001 ถึง SEC-010) |
| **Evidence-Based** | роверинг แบบ tiered: source → unit → integration → live-runtime → production |

---

## Platform Capabilities

### 🖥️ Interfaces

| Interface | Technology | Description |
|---|---|---|
| **CLI** | Click/Typer patterns | `zcoder` และ `python main.py` entry points |
| **TUI** | Textual 0.80+ | Terminal UI แบบ interactive |
| **Web Console** | FastAPI + Uvicorn | Browser-based management console |
| **API Server** | FastAPI + OpenAPI | RESTful API พร้อม `/metrics`, `/health/live`, `/health/ready` |

### 🤖 AI & Agent Runtime

- **CodeAgent** — autonomous coding cycles แบบ bounded (Inspect → Plan → Edit → Test → Validate)
- **Tool Parity** — Read, Write, Edit, Glob, Grep, LS, Bash, WebFetch พร้อม security boundaries
- **Sessions** — resume, rewind, branch conversations
- **Subagents** — bounded budgets, permissions, frontmatter validation
- **Hooks** — lifecycle events แบบ fail-closed
- **MCP** — server discovery, tool trust policy, resource validation
- **Memory** — scoped CLAUDE.md hierarchy (enterprise → user → project)
- **Skills & Commands** — loader containment, install/remove/info lifecycle

### 🏗️ Architecture

```text
                    +----------------------+
                    |      Interfaces      |
                    | CLI / TUI / Web/API  |
                    +----------+-----------+
                               |
                               v
                    +----------------------+
                    |       Services       |
                    | agents / workflows   |
                    | orchestration / API  |
                    +----------+-----------+
                               |
               +---------------+---------------+
               |                               |
               v                               v
     +-------------------+         +--------------------+
     | Core / Domain     |         | Provider Adapters  |
     | jobs / policy /   |         | local / Claude /   |
     | tenants / models  |         | external optional  |
     +---------+---------+         +---------+----------+
               |                               |
               +---------------+---------------+
                               |
                               v
                    +----------------------+
                    |   Infrastructure     |
                    | SQLite / PostgreSQL  |
                    | GitHub / workers /   |
                    | deploy / telemetry   |
                    +----------------------+
```

See [`ARCHITECTURE.md`](ARCHITECTURE.md) สำหรับรายละเอียดเต็ม

### 🏢 Enterprise Features

| Domain | Components |
|---|---|
| **Multi-Tenancy** | Organization → Project → Resources hierarchy, RLS policies |
| **Identity** | OIDC/JWT, SCIM 2.0 provisioning, API keys, break-glass admin |
| **RBAC** | 8 enterprise roles, 30+ permissions, provider-neutral enforcement |
| **Quotas** | Concurrent jobs, monthly budget, project/repository limits |
| **Audit** | Immutable append-only audit log, structured JSONL export |
| **Billing** | Provider-neutral interface, Stripe adapter, usage metering |
| **Deployment** | Health checks, backup/restore, rollback, DR rehearsal |
| **Observability** | Prometheus `/metrics`, OTel OTLP, structured JSON logs |

### 🔒 Security Boundaries

| ID | Surface | Status |
|---|---|---|
| SEC-001 | Deep Research SSRF | ✅ FIXED |
| SEC-002 | Sandbox filesystem traversal | ✅ FIXED |
| SEC-003 | Sandbox network bypass | ✅ FIXED |
| SEC-004 | CodeAgent filesystem containment | ✅ FIXED |
| SEC-005 | CodeAgent WebFetch SSRF | ✅ FIXED |
| SEC-006 | MCP/tool-output trust boundary | ✅ FIXED |
| SEC-007 | RAG/document trust + tenant isolation | ✅ FIXED |
| SEC-008 | Secrets/environment inheritance | ✅ FIXED |
| SEC-009 | Authorization/approval boundaries | ✅ FIXED |
| SEC-010 | CI/dependency/supply-chain | ✅ FIXED |

See [`SECURITY.md`](SECURITY.md) สำหรับรายละเอียด

---

## เริ่มต้นใช้งาน

### ตrequirements

- Python 3.9+
- pip
- (Optional) PostgreSQL 16+ สำหรับ enterprise mode
- (Optional) Ollama/llama.cpp สำหรับ local AI

### Installation

```bash
git clone https://github.com/cvsz/zcoder.git
cd zcoder

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -e .
```

Development dependencies:

```bash
pip install -e '.[dev]'
```

Optional groups: `web`, `tui`, `excel`, `pptx`, `all`

### Verification

```bash
zcoder --version
zcoder --help
python main.py --help
```

### การใช้งานพื้นฐาน

```bash
# Coding request with Anthropic
export ANTHROPIC_API_KEY='sk-ant-...'
zcoder -p 'Write a Python function to reverse a string'

# File analysis
zcoder -f app.py -p 'Review this file and propose a minimal fix'

# Terminal UI
zcoder --tui

# Web console
make build
make start
```

---

## No-Cost-First Execution Model

ZCoder แยก **cost classification** จาก **runtime availability**:

```text
Cost Classes:
  FREE_LOCAL     → Ollama, llama.cpp, local embeddings
  FREE_REMOTE    → Public/free model endpoints
  CUSTOMER_KEY   → Customer-supplied API keys
  PAID_PLATFORM  → Commercial provider APIs
  UNKNOWN        → Unclassified routes

Policy Modes:
  ZERO_COST_ONLY   → Block all paid/unknown transports
  PREFER_ZERO_COST → Use free first, paid only with explicit opt-in
  PERMIT_PAID      → Allow paid routes with logging
```

**กฎสำคัญ:** Zero-cost routing **ต้องไม่ silent fallback** ไป paid transport

---

## Local AI Stack

### Runtime Adapters

- **llama.cpp / llama-server** — process ownership, structured output
- **Ollama** — local gateway (`http://127.0.0.1:11434`)
- **vLLM** — high-throughput local inference
- **OpenAI-compatible** — generic loopback servers

### Hardware Profiling

`HardwareProfiler` ตรวจสอบ:
- OS และ architecture
- CPU core count
- RAM (total/available)
- NVIDIA GPU (`nvidia-smi`)
- Apple Silicon
- VRAM (เมื่อสามารถระบุได้)

### Model Lifecycle

```text
CATALOG → DISCOVERED → DOWNLOADING → DOWNLOADED →
VERIFIED → LOADABLE → LOADED → FAILED → REMOVED
```

### Local RAG

- Offline TF-IDF/cosine retrieval
- ไม่ต้องพึ่ง hosted embedding service หรือ vector DB
- Secret-aware filtering สำหรับ repository content

---

## Autonomous Engineering

ZCoder มี durable agent runtime สำหรับ bounded coding cycles:

| Component | Description |
|---|---|
| **EngineeringTask** | Durable job state with status, metadata, lease |
| **Worker** | Process execution boundaries, cancellation, retry |
| **Outbox** | Durable outbox สำหรับ external mutations |
| **Fencing** | Monotonic fencing tokens ป้องกัน stale claims |
| **Approval** | Approval-aware actions แบบ fail-closed |
| **GitHub Orchestration** | PR/CI orchestration, bounded repair |
| **Policy Engine** | require_approval, sandbox, max_budget obligations |
| **Scheduler** | Maintenance campaigns, lease-gated execution |

---

## CLI Commands

```bash
# Core coding
zcoder -p "prompt"                    # One-shot coding
zcoder -f file.py -p "review"         # File analysis
zcoder --tui                           # Terminal UI

# Code agent (autonomous)
zcoder --code-agent "fix auth bug"    # Autonomous coding cycle
zcoder --code-agent-permission ask   # Permission mode

# Provider routing
zcoder --provider anthropic           # anthropic | gemini | xai | ollama | local
zcoder --base-url http://localhost:11434  # Custom gateway

# GitHub
zcoder --gh-issue 123                 # GitHub issue operations
zcoder --gh-pr 456                    # PR orchestration

# Embeddings/RAG
zcoder --embed "query"                # Embedding lookup
zcoder --embed-file doc.md            # Index file

# Observability
zcoder --metrics-show                 # Show metrics
zcoder --health-check                 # Health endpoints

# Maintenance
zcoder --maintenance                  # Run maintenance campaign
zcoder --backup                       # Create backup
zcoder --dr-rehearsal                 # DR rehearsal
```

---

## Configuration

### Environment Variables

| Variable | Description | Required |
|---|---|---|
| `ANTHROPIC_API_KEY` | Anthropic Claude API key | Optional |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | Google Gemini API key | Optional |
| `XAI_API_KEY` | xAI Grok API key | Optional |
| `OLLAMA_BASE_URL` | Ollama gateway URL | Optional |
| `ZCODER_LOCAL_MODE` | Enable local-only mode (0/1) | Optional |
| `DATABASE_URL` | PostgreSQL connection string | Optional (SQLite default) |
| `ZCODER_OTEL_ENDPOINT` | OpenTelemetry collector endpoint | Optional |
| `ZCODER_PROVIDER` | Default provider (anthropic/gemini/xai/ollama/local) | Optional |
| `ZCODER_BASE_URL` | Default API gateway URL | Optional |

### Cost Policy

```bash
# Zero-cost only — block all paid transports
export ZCODER_COST_POLICY=ZERO_COST_ONLY

# Prefer free, allow paid with logging
export ZCODER_COST_POLICY=PREFER_ZERO_COST

# Permit paid routes
export ZCODER_COST_POLICY=PERMIT_PAID
```

---

## Security Principles

1. **No provider secrets in client-side code**
2. **Mutating actions behind explicit policy/approval boundaries**
3. **Tenant-scoped data isolation** (RLS, fail-closed boundaries)
4. **Filesystem path validation** (safe_resolve, traversal rejection)
5. **No silent paid-provider fallback** in zero-cost mode
6. **Model artifacts as data** — not automatically trusted executables
7. **Audit/evidence visible** — no mocks presented as real-runtime proof

See [`SECURITY.md`](SECURITY.md) สำหรับรายละเอียด

---

## Development

### Prerequisites

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

### Quality Checks

```bash
# Lint & format
ruff check .
black --check .

# Security
bandit -r src/zcoder -ll

# Type checking
mypy src/zcoder --ignore-missing-imports

# Tests with coverage
pytest --cov --cov-report=term-missing

# Minimum coverage: 70%
```

### CI Matrix

| Python Version | Status |
|---|---|
| 3.9 | ✅ Supported |
| 3.10 | ✅ Supported |
| 3.11 | ✅ Supported |
| 3.12 | ✅ Supported |

### Additional CI Checks

- CodeQL security scanning
- Dependency Review (Dependabot)
- Helm lint/template
- Release Gate validation
- SDK/TypeScript compatibility
- Docker build
- Reproducibility (`uv lock --check`, `uv sync --locked`)

---

## Docker

```bash
# Build
docker build -t zcoder:local .

# Verify
docker run --rm zcoder:local --version

# Run with provider key
docker run --rm -e ANTHROPIC_API_KEY=sk-ant-... zcoder:local
```

---

## Operations

### Health Endpoints

```bash
GET /health/live    # Liveness probe
GET /health/ready   # Readiness probe (fail-closed 503 on DB failure)
GET /metrics        # Prometheus exposition format
```

### Backup & Restore

```python
from zcoder.services.backup_restore import BackupManager

bm = BackupManager()

# Create backup
record = bm.run_pg_dump_backup()

# Restore drill
result = bm.run_restore_drill(
    backup_id=record.backup_id,
    target_database_url="postgresql://...",
    expected_job_ids=["job_1", "job_2"]
)
```

### Deployment

```python
from zcoder.domain.services.deployment import DeploymentEngine

engine = DeploymentEngine(store)

# Health check
health = engine.evaluate_health()

# Deployment history
history = engine.get_deployment_history(limit=20)

# Rollback
success, msg = engine.rollback_to_version("v1.40.0")

# Artifact revocation
engine.revoke_artifact(manifest, "Supply chain compromise")

# Deployment rehearsal
result = engine.run_deployment_rehearsal("v1.41.0-rc1", dry_run=True)
```

### DR Rehearsal

ดู [`docs/operations/dr-rehearsal.md`](docs/operations/dr-rehearsal.md) สำหรับ quarterly procedure

---

## Observability

### Metrics (Prometheus)

```
zcoder_jobs_queued
zcoder_jobs_running
zcoder_job_duration_seconds
zcoder_worker_active
zcoder_worker_lease_expirations
zcoder_outbox_pending
zcoder_webhooks_total
zcoder_github_api_errors
zcoder_db_pool_in_use
zcoder_backup_last_success_timestamp
zcoder_api_requests
zcoder_cost_usd
zcoder_maintenance_campaigns
```

### Logging

- **Format:** JSON (non-TTY) หรือ text (interactive TTY)
- **Correlation ID:** หนึ่งต่อ CLI invocation
- **Redaction:** `sk-ant-...`, `Authorization`, `x-api-key` filtered อัตโนมัติ
- **Destination:** stderr only (stdout reserved for CLI output)

### OpenTelemetry

```bash
export ZCODER_OTEL_ENDPOINT=http://collector:4317
zcoder --health-check  # OTel bootstrap happens automatically
```

Dashboard config: [`docs/observability/dashboard.json`](docs/observability/dashboard.json)

---

## Documentation

| Document | Description |
|---|---|
| [`QUICKSTART.md`](QUICKSTART.md) | Basic setup and first commands |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | System architecture and boundaries |
| [`ROADMAP.md`](ROADMAP.md) | Engineering direction |
| [`CHANGELOG.md`](CHANGELOG.md) | Release history |
| [`SECURITY.md`](SECURITY.md) | Security guidance |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Contribution workflow |
| [`IMPLEMENTATION_CHECKLIST.md`](IMPLEMENTATION_CHECKLIST.md) | Implementation tracking |
| [`exec-planning.md`](exec-planning.md) | Production readiness execution plan |
| [`docs/operations/`](docs/operations/) | Deployment, DR, observability runbooks |
| [`docs/security/`](docs/security/) | Security audits and remediation |

---

## Evidence Tiers

| Tier | Description |
|---|---|
| **1. Source** | Implemented in `src/zcoder/` |
| **2. Unit** | Contract/unit tests (1255+ tests) |
| **3. Integration** | Controlled dependency testing |
| **4. Live Runtime** | Verified against real local/external runtime |
| **5. Production** | Verified in target deployment environment |

> **Important:** A model catalog entry is NOT proof of installed/runnable model. An adapter contract test is NOT proof of real inference. Evidence must match the claim tier.

---

## License

ZCoder is released under the [MIT License](LICENSE).

---

## Project Status

**Actively maintained.** The repository contains mature integration surfaces and active development on local-AI and control-plane subsystems. When evaluating production readiness, use CI results, release gates, real-runtime evidence, and documented subsystem limitations — not feature names alone.

**Current Baseline:** `main@2d8b4a2` (exec-planning.md implementation sweep complete)

**Security:** SEC-001 through SEC-010 closed and verified.

---

## Contributing

Contributions must preserve:

- ✅ No mandatory commercial dependency for no-cost core
- ✅ No silent downgrade of security, tenant isolation, or approval semantics
- ✅ No provider secrets in client-side code
- ✅ No fake/simulated evidence presented as real-runtime proof
- ✅ Deterministic tests for routing, policy, and failure paths
- ✅ Backward compatibility where practical

Before opening a PR:

```bash
ruff check .
black --check .
bandit -r src/zcoder -ll
pytest --cov --cov-report=term-missing
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full workflow.
