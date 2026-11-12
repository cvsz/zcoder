# ZCoder

> **Enterprise AI Coding Platform ระดับองค์กรสำหรับการพัฒนาแบบ Local-First, Self-Hosted, และ Hybrid Cloud**

[![CI](https://github.com/cvsz/zcoder/actions/workflows/ci.yml/badge.svg)](https://github.com/cvsz/zcoder/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Security](https://img.shields.io/badge/Security-SEC--001%20%E2%86%92%20SEC--011-green.svg)](SECURITY.md)
[![Docker](https://img.shields.io/badge/Docker-ghcr.io-blue.svg)](https://github.com/cvsz/zcoder/pkgs/container/zcoder)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-zpostgresql-blue.svg)](docs/operations/deployment.md)
[![Coverage](https://img.shields.io/badge/Coverage-80.51%25-brightgreen.svg)](https://github.com/cvsz/zcoder/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/cvsz/zcoder)](https://github.com/cvsz/zcoder/releases)
[![Final Report](https://img.shields.io/badge/Report-Final-Report.md-blue)](Final-Report.md)

![ZCoder Social Preview](https://repository-images.githubusercontent.com/1298675090/168568c9-a175-4d82-9733-955d6d7bf7b4)

**เวอร์ชันปัจจุบัน:** `1.60.0`  
**สถานะ:** **Production-Grade Ready** — ได้รับการตรวจสอบอย่างลึกซึ้ง (Deep Audit) และผ่านการรีวิวแบบ multi-account governance แล้ว

---

## Status Badges

| Check | Badge | Status |
|-------|-------|--------|
| CI / Build | [![CI](https://github.com/cvsz/zcoder/actions/workflows/ci.yml/badge.svg)](https://github.com/cvsz/zcoder/actions/workflows/ci.yml) | Passing |
| Security Scan | [![Security Scan](https://github.com/cvsz/zcoder/actions/workflows/security-scan.yml/badge.svg)](https://github.com/cvsz/zcoder/actions/workflows/security-scan.yml) | Passing |
| CodeQL | [![CodeQL](https://github.com/cvsz/zcoder/actions/workflows/codeql.yml/badge.svg)](https://github.com/cvsz/zcoder/actions/workflows/codeql.yml) | Passing |
| Release Gate | [![Release Gate](https://github.com/cvsz/zcoder/actions/workflows/release-gate.yml/badge.svg)](https://github.com/cvsz/zcoder/actions/workflows/release-gate.yml) | Passing |
| Coverage | [![Coverage](https://img.shields.io/badge/Coverage-80.51%25-brightgreen.svg)](https://github.com/cvsz/zcoder/actions/workflows/ci.yml) | **80.51%** |
| License | [![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE) | MIT |
| Python | [![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/) | 3.12+ |
| Docker | [![Docker ghcr.io](https://img.shields.io/badge/Docker-ghcr.io-blue.svg)](https://github.com/cvsz/zcoder/pkgs/container/zcoder) | Available |
| Final Report | [![Final Report](https://img.shields.io/badge/Report-Final-Report.md-blue)](Final-Report.md) | Complete |

---

## ภาพรวม (Executive Summary)

ZCoder คือ **Enterprise AI Coding Platform** ที่ออกแบบมาให้ครอบคลุมทุกระบบใน codebase เดียว:

- **CLI** — คำสั่งบรรทัดคำสั่งสำหรับ coding, code agent, GitHub orchestration
- **TUI** — Terminal UI แบบ interactive ด้วย Textual
- **Web Console** — FastAPI + Uvicorn, browser-based management console
- **API Server** — RESTful API พร้อม `/health/live`, `/health/ready`, `/metrics`
- **Autonomous Agent Runtime** — bounded coding cycles (Inspect → Plan → Edit → Test → Validate)
- **Local AI Infrastructure** — llama.cpp / Ollama / vLLM บน loopback, zero-cost first
- **GitHub Orchestration** — PR/CI orchestration, bounded repair
- **Enterprise Control Plane** — multi-tenancy, RBAC, audit, quotas, billing, observability
- **MCP Server/Client** — Model Context Protocol server over stdio/HTTP/SSE
- **Database** — SQLite (default, single-user) / PostgreSQL (`zcoder_db`, role `zcoder`) ผ่าน Docker service `zpostgresql`

---

## จุดเด่นหลัก

| คุณสมบัติ | รายละเอียด |
|---|---|
| **Local-First** | รันได้เต็มรูปแบบบน infrastructure ของคุณ ไม่ต้องพึ่ง cloud |
| **Zero-Cost First** | แยก cost classification จาก runtime availability — ไม่ silent fallback ไป paid provider |
| **Provider-Neutral** | รองรับ Anthropic, Gemini, xAI, Ollama, local model, NVIDIA NIM พร้อมกัน |
| **Production-Ready** | Durable jobs, policy, tenant isolation, audit, queues, workers, observability, backup/restore |
| **Security-First** | SEC-001 ถึง SEC-011 ปิดครบ (รวม zPITR PITR/DR) |
| **Evidence-Based** | การยืนยันผลแบบ tiered: source → unit → integration → live-runtime → production |
| **Governance** | GPG-signed commits, multi-account review (cvsz author / policedbc reviewer / cvsz integrator), squash merge |

---

## Bridge Infrastructure

ZCoder รองรับ **shared PostgreSQL container** (`zpostgresql`) บน Docker network เฉพาะ (`zPostgreSQL_network`) สำหรับ integration tests และ local development โดยแยก lifecycle จาก repository:

### Shared PostgreSQL Container

```bash
# เริ่มต้น shared PostgreSQL container
make postgres-setup

# ตรวจสอบสถานะ
make postgres-status
```

**ค่าเริ่มต้นของการกำหนดค่า:**
- **Container:** `zpostgresql`
- **Network:** `zPostgreSQL_network`
- **ฐานข้อมูล:** `zcoder_db`
- **Role:** `zcoder`
- **Connection:** `postgresql://zcoder@zpostgresql:5432/zcoder_db`

Compose service เข้าร่วม `zPostgreSQL_network` และ mount password file ที่สร้างโดย `make postgres-setup` เป็น read-only secret。Container entrypoint จะสร้าง `DATABASE_URL` ขณะรันโดยไม่เขียนรหัสผ่านลงใน `.env`, ภาพ Docker, หรือ command line ให้แก้ไข `ZCODER_POSTGRES_SECRET_SOURCE` เฉพาะเมื่อ password file บน host ใช้ path ที่ไม่ใช่ค่าเริ่มต้นเท่านั้น

### การทดสอบในเครื่องด้วย Shared PostgreSQL

```bash
# รัน integration tests กับ shared PostgreSQL
python scripts/local_postgres.py run -- python -m pytest tests/integration -q

# รัน E2E tests กับ shared PostgreSQL
python scripts/local_postgres.py run -- python -m pytest tests/e2e -q
```

คำสั่งบน host ที่ต้องใช้ฐานข้อมูลควรใช้ helper ซึ่งจะ inject DSN เฉพาะลงใน child process โดยไม่พิมพ์รหัสผ่าน:

```bash
python scripts/local_postgres.py run -- <command>
```

**ข้อห้าม:** ห้ามใช้ `localhost` จากอีก container หนึ่ง หรือใส่รหัสผ่านฐานข้อมูลในไฟล์ `.env` ของ repository เด็ดขาด

---

## Platform Capabilities

### 🖥️ Interfaces

| Interface | Technology | Description |
|---|---|---|
| **CLI** | Click/Typer patterns | `zcoder` และ `python main.py` entry points |
| **TUI** | Textual 0.80+ | Terminal UI แบบ interactive |
| **Web Console** | FastAPI + Uvicorn + AdminLTE 3 | Browser-based management console (AdminLTE 3 dashboard: Bootstrap 4 + jQuery + FontAwesome via CDN) |
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

See [`ARCHITECTURE.md`](docs/architecture/ARCHITECTURE.md) สำหรับรายละเอียดเต็ม

---

## 🏢 Enterprise Features

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

---

## 🔒 Security Boundaries

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
| SEC-011 | Point-in-Time Recovery / Disaster Recovery | ✅ FIXED (`zPITR` service) |

See [`SECURITY.md`](SECURITY.md) สำหรับรายละเอียด

---

## 🛡️ zPITR — Point-in-Time Recovery

ZCoder includes a containerized **zPITR** service (`deploy/docker/zpitr/`, `docker-compose.zpitr.yml`) for automated PostgreSQL Point-in-Time Recovery:

- **Continuous WAL streaming** via `pg_receivewal` (RPO < 5 min)
- **Periodic base backups** via `pg_basebackup` with SHA-256 manifests
- **Automated restore drill** with isolated sandbox and Release Gate evidence emission (`docs/evidence/pitr-qualification-<SHA>.json`)

Deploy with `docker compose -f docker-compose.zpitr.yml up -d`. See [`docs/zpitr-implementation.md`](docs/zpitr-implementation.md) and [`docs/operations/deployment.md`](docs/operations/deployment.md) § zPITR.

---

## เริ่มต้นใช้งาน

### Requirements

- Python 3.12+
- The local `--pptx` integration is supported on Python 3.12+. `--pptx-native` avoids local PPTX conversion dependencies but does not lower the project minimum Python version.
- pip
- (Optional) PostgreSQL 16+ สำหรับ enterprise mode
- (Optional) Ollama/llama.cpp สำหรับ local AI

For custom installation paths and platform-specific standalone builds, see the [Portable Installation Guide](docs/guides/PORTABLE-INSTALL.md).

**Runtime requirement:** Python 3.12 or newer is required for the security-patched dependency set.

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

The console frontend is built with **AdminLTE 3** (Bootstrap 4 + jQuery + FontAwesome via CDN): sidebar navigation, main-header navbar, control sidebar, metrics small boxes, run configuration card, and workspace console with SSE streaming chat. Connect the backend via the API base URL dialog to activate live models, sessions and streaming.
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
| `ZCODER_ROUTE_PROVIDER` | Provider used only by `--route`; supports `nvidia` | Optional |
| `NVIDIA_API_KEY` (or `_1` / `_2`) | NVIDIA NIM credential for routed requests | Optional |
| `ZCODER_NVIDIA_MODELS` | Ordered, comma-separated NVIDIA route fallback model IDs | Optional |
| `NVIDIA_BASE_URL` | NVIDIA OpenAI-compatible API base URL | Optional |
| `ZCODER_BASE_URL` | Default API gateway URL | Optional |
| `ZCODER_WEB_API_KEY` | Bearer token for web API state-changing/admin endpoints | Optional (local/dev: unset) |

NVIDIA routed requests use `NVIDIA_API_KEY` or the existing numbered key variables, and try `ZCODER_NVIDIA_MODELS` in order after a retryable failure or model rejection. The model IDs accept free-form values; OpenCode's `nvidia/nvidia/...` prefix is normalized for NVIDIA's API. The route-specific provider setting does not change other local CLI flows. Example:

```bash
zcoder --route "Review this code" --route-explain
```

NVIDIA's hosted trial service may record prompts and outputs for service operation and improvement. Do not send confidential source code or personal data unless your NVIDIA terms explicitly permit it. See the [NVIDIA model catalog](https://build.nvidia.com/models) and the relevant model's current terms before use.

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
| 3.12 | ✅ Supported (minimum) |
| 3.13 | ✅ Supported |

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

### Local GGUF inference (recommended)

The Compose stack runs ZCoder and a separate llama.cpp server. It does not
require an Anthropic API key. Put the selected GGUF in `models/` (default:
`models/qwen-7b-q4km.gguf`), then run:

```bash
cp -n .env.example .env
docker compose config
docker compose run --build --rm zcoder -p "Reply with exactly LOCAL_OK"
docker compose logs -f llama-server
docker compose down
```

If `.env` already exists, keep it and update only the required model settings.

Use `ZCODER_GGUF_FILE=qwen-1.5b-q4km.gguf` and
`ZCODER_MODEL=qwen-1.5b-q4km` in `.env` to select the smaller model.
The model directory is mounted read-only. GGUF files are excluded from Git
and from the Docker build context. The inference service publishes no host
port; ZCoder shares its network namespace and uses the loopback endpoint.
See [QUICKSTART.md](docs/guides/QUICKSTART.md) and
[Local Inference Configuration](docs/guides/LOCAL-INFERENCE.md).

### Build and run the application image directly

```bash
docker build -t zcoder:local .
docker run --rm zcoder:local --version

# Run the API server against a reachable PostgreSQL database
docker run --rm --entrypoint zcoder-server -p 8088:8088 -e HOST=0.0.0.0 \
  -e DATABASE_URL=postgresql://user:password@host:5432/zcoder \
  zcoder:local
```

The image pins its Python and uv builder images by digest and installs the
runtime dependency set from `uv.lock`; Dependabot proposes digest updates.

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
result = engine.run_deployment_rehearsal("v1.41.5-rc1", dry_run=True)
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
| [`QUICKSTART.md`](docs/guides/QUICKSTART.md) | Basic setup and first commands |
| [`ARCHITECTURE.md`](docs/architecture/ARCHITECTURE.md) | System architecture and boundaries |
| [`ROADMAP.md`](docs/engineering/ROADMAP.md) | Engineering direction |
| [`CHANGELOG.md`](CHANGELOG.md) | Release history |
| [`SECURITY.md`](SECURITY.md) | Security guidance |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Contribution workflow |
| [`IMPLEMENTATION_CHECKLIST.md`](IMPLEMENTATION_CHECKLIST.md) | Implementation tracking |
| [`exec-planning.md`](docs/engineering/exec-planning.md) | Production readiness execution plan |
| [`docs/operations/`](docs/operations/) | Deployment, DR, observability runbooks |
| [`docs/security/`](docs/security/) | Security audits and remediation |
| [`Final-Report.md`](Final-Report.md) | Deep audit & production-readiness final report |

---

## Evidence Tiers

| Tier | Description |
|---|---|
| **1. Source** | Implemented in `src/zcoder/` |
| **2. Unit** | Contract/unit tests (1,700+ tests) |
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

**Current Baseline:** `main@2d8b4a2` ([docs/engineering/exec-planning.md](docs/engineering/exec-planning.md) implementation sweep complete)

**Security:** SEC-001 through SEC-011 closed and verified.

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

---

