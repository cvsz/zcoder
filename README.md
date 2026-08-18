# ZCoder

> **No-cost-first AI coding and agent platform for local, self-hosted, and optional cloud workflows.**

[![CI](https://github.com/cvsz/zcoder/actions/workflows/ci.yml/badge.svg)](https://github.com/cvsz/zcoder/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Current package version:** `1.40.0`

ZCoder is a modular Python platform for AI-assisted software engineering. It combines a CLI, TUI, browser UI, autonomous agent runtime, local/self-hosted AI infrastructure, GitHub orchestration, enterprise control-plane capabilities, and optional provider integrations in one codebase.

The current architecture is intentionally **no-cost first**: local and self-hosted execution can be used without making a commercial AI provider mandatory. Paid or customer-supplied provider credentials are optional integration paths rather than a requirement for the platform core.

---

## Why ZCoder

ZCoder is designed around a few hard constraints:

- **Local/self-hosted first** — keep core workflows runnable on infrastructure you control.
- **Zero-cost policy support** — distinguish local/free execution from customer-key, paid-platform, and unknown-cost routes.
- **Provider portability** — keep model/provider-specific behavior behind adapters.
- **Autonomous engineering workflows** — inspect, plan, edit, test, validate, review, and orchestrate bounded coding jobs.
- **Production architecture** — durable jobs, policy, tenant boundaries, auditability, queues, workers, observability, backup/restore, and deployment concerns are first-class.
- **Evidence over claims** — catalog entries, mocks, contract tests, and real runtime verification are treated as different evidence levels.
- **Backward compatibility** — the package keeps compatibility shims for legacy flat-module imports while the implementation is organized under `src/zcoder/`.

---

## Platform at a glance

| Area | What is in the repository |
|---|---|
| CLI | `zcoder` and source-compatible `python main.py` entry points |
| TUI | Textual-based terminal interface |
| Web | FastAPI/Uvicorn browser console with optional web dependencies |
| Local AI | Hardware profiling, model registry, local model gateway, llama.cpp/Ollama/vLLM/OpenAI-compatible adapters, local embeddings/RAG; `ZCODER_LOCAL_MODE` offline synthesis for keyless/air-gapped smoke use |
| No-cost core | Cost classification and routing policy, local object storage, local analytics, notifications, workflows, agent catalog |
| Agents | Durable agent runtime, bounded coding cycles, approvals, cancellation/retry semantics |
| GitHub automation | Repository jobs, PR/CI orchestration, review and bounded repair workflows |
| Enterprise control plane | Multi-tenancy, PostgreSQL-backed state, policy, identity, quotas, audit, residency and compliance-oriented components |
| Public product layer | Public API, SDK client, customer webhooks, product/plan/entitlement boundaries |
| Operations | Deployment, observability, health, resilience, backup/restore, security and release gates |
| Claude integration | Extensive optional Anthropic/Claude API, admin, compliance, tools, files, batch, agents, memory, model and workflow support |

---

## Quick start

### 1. Clone and create a virtual environment

```bash
git clone https://github.com/cvsz/zcoder.git
cd zcoder

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -e .
```

For development tooling:

```bash
pip install -e '.[dev]'
```

Optional feature groups are available through `pyproject.toml`, including `web`, `tui`, `excel`, `pptx`, and `all`.

### 2. Verify the installation

```bash
zcoder --version
zcoder --help
```

The legacy-compatible entry point also remains available:

```bash
python main.py --help
```

### 3. Run a basic coding request

For an Anthropic-backed request, configure your own key explicitly:

```bash
export ANTHROPIC_API_KEY='sk-ant-...'
zcoder -p 'Write a Python function to reverse a string'
```

Analyze an existing file:

```bash
zcoder -f app.py -p 'Review this file, identify defects, and propose a minimal fix'
```

### 4. Terminal UI

```bash
zcoder --tui
```

### 5. Web console

```bash
make build
make start
```

The existing web lifecycle targets include `start`, `stop`, `restart`, `status`, and `logs`. See [`QUICKSTART.md`](QUICKSTART.md) and the web documentation for the current details.

---

## No-cost-first execution model

ZCoder separates **cost classification** from **runtime availability**.

The no-cost platform defines these cost classes:

```text
FREE_LOCAL
FREE_REMOTE
CUSTOMER_KEY
PAID_PLATFORM
UNKNOWN
```

and policy modes including:

```text
ZERO_COST_ONLY
PREFER_ZERO_COST
PERMIT_PAID
```

The important rule is that **zero-cost routing must not silently fall back to a paid or unknown-cost transport**.

A model being present in a catalog is not the same as the model being downloaded, installed, loaded, benchmarked, or proven on the current host. ZCoder's local model lifecycle keeps these concepts separate so operational decisions can be made from actual state rather than labels.

---

## Local AI stack

The local AI subsystem lives primarily in:

```text
src/zcoder/enterprise/local_ai_stack.py
src/zcoder/enterprise/no_cost_platform.py
```

### Runtime adapters

The codebase contains local execution abstractions and adapters for:

- **llama.cpp / llama-server**
- **Ollama**
- **vLLM**
- **generic loopback OpenAI-compatible servers**

The adapters are intended to sit behind the local model gateway rather than leaking runtime-specific behavior into coding workflows.

### Hardware profiling

`HardwareProfiler` detects host characteristics used by routing and fit decisions, including:

- operating system and architecture
- CPU core count
- total and available RAM
- NVIDIA GPU detection when `nvidia-smi` is available
- Apple Silicon detection
- CPU-only fallback
- VRAM where it can be determined

Hardware detection is advisory. A claimed GPU/runtime capability must still be verified on the machine where the workload actually runs.

### Model registry and lifecycle

The local model registry distinguishes model state instead of treating every catalog entry as installed:

```text
CATALOG
DISCOVERED
DOWNLOADING
DOWNLOADED
VERIFIED
LOADABLE
LOADED
FAILED
REMOVED
```

Model metadata can include source type, repository/path, revision, filename, format, size, digest, license, parameter count, quantization and gated-access status.

### Local embeddings and RAG

ZCoder includes an offline repository-indexing path using deterministic local TF-IDF/cosine retrieval. It is designed to avoid a mandatory hosted embedding service or vector database and includes secret-aware filtering for repository content.

### Local MCP and agent runtime

The local stack also contains MCP-oriented tooling and a bounded autonomous coding cycle built around:

```text
Inspect -> Plan -> Edit -> Test -> Validate
```

The local agent path is designed to be independent from a proprietary cloud agent SDK.

### Important verification rule

Some contract or development paths can operate with simulated/fallback behavior when a real local daemon or model is unavailable. Therefore:

> **Do not interpret a model catalog entry or contract test as proof of real local inference.**

A real-runtime claim should include an actual local process, actual model identity/artifact, actual generated output, and zero-paid-call evidence for the run.

---

## Autonomous engineering platform

ZCoder has evolved beyond one-shot code generation. The repository includes components for durable engineering jobs and orchestration, including:

- durable agent job state
- worker execution boundaries
- cancellation and retry handling
- approval-aware actions
- GitHub repository and pull-request orchestration
- CI observation and bounded repair workflows
- policy enforcement
- audit events
- scheduling and leases
- SQLite and PostgreSQL-backed persistence paths
- observability and operational health components

These capabilities are organized across `core`, `domain`, `services`, `infrastructure`, `worker`, and enterprise-oriented modules instead of being embedded entirely inside the CLI.

---

## Enterprise and SaaS-oriented capabilities

The repository contains architecture and implementation for larger deployments, including components for:

- organizations, projects and tenant boundaries
- PostgreSQL-backed control-plane state
- row-level tenant isolation work
- identity/OIDC integration
- SSO/SCIM-oriented services
- service accounts and policy controls
- quotas and usage accounting
- residency/compliance models
- audit evidence
- public API and SDK boundaries
- customer webhooks
- product/plan/entitlement models
- provider-neutral billing boundaries
- deployment and resilience
- backup/restore and recovery workflows
- OpenTelemetry-oriented observability

These components do **not** imply that every external production dependency is bundled with ZCoder. Production PostgreSQL HA, external identity infrastructure, object storage, physical multi-region deployment and other environment-specific systems remain deployment responsibilities unless explicitly implemented by the selected deployment profile.

---

## Optional Claude / Anthropic integration

ZCoder retains extensive Claude integration for users who choose to provide Anthropic credentials. The repository includes modules for areas such as:

- Messages and streaming
- model catalog/preflight behavior
- tool use and structured output
- prompt caching and token management
- Files and Batch APIs
- citations, search and research helpers
- memory and sessions
- Claude Code / agent-oriented integrations
- Managed Agents
- Admin API and compliance-oriented APIs
- GitHub, routing, metrics and prompt-optimization helpers
- Excel and PowerPoint-oriented workflows

Cloud-backed features are optional integrations. They are not evidence that a zero-cost execution profile is using a paid provider.

For historical Anthropic-specific changes, see [`CHANGELOG.md`](CHANGELOG.md) and the dated documents under [`docs/`](docs/).

---

## Architecture

A simplified view of the current repository architecture:

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
                    +-------------+-------------+
                    |                           |
                    v                           v
          +--------------------+      +--------------------+
          | Core / Domain      |      | Provider Adapters  |
          | jobs / policy /    |      | local / Claude /   |
          | tenants / models   |      | external optional  |
          +---------+----------+      +---------+----------+
                    |                           |
                    +-------------+-------------+
                                  |
                                  v
                       +----------------------+
                       |   Infrastructure     |
                       | SQLite / PostgreSQL  |
                       | GitHub / workers /   |
                       | deploy / telemetry   |
                       +----------------------+
```

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the detailed system view.

---

## Repository layout

```text
zcoder/
├── src/
│   ├── zcoder/
│   │   ├── api/              # API specifications/resources
│   │   ├── claude/           # Claude-specific integration modules
│   │   ├── config/           # configuration package
│   │   ├── core/             # core application behavior
│   │   ├── domain/           # domain models and boundaries
│   │   ├── enterprise/       # local AI and no-cost enterprise stack
│   │   ├── infrastructure/   # persistence/integration infrastructure
│   │   ├── interfaces/       # interface adapters
│   │   ├── services/         # application services
│   │   ├── worker/           # worker/runtime processes
│   │   └── main.py           # primary CLI entry point
│   └── *.py                  # backward-compatible module aliases
├── tests/                    # unit/integration/e2e suites
├── webapp/                   # browser application
├── docs/                     # implementation, audit and upgrade docs
├── .github/workflows/ci.yml  # CI pipeline
├── ARCHITECTURE.md
├── CHANGELOG.md
├── QUICKSTART.md
├── ROADMAP.md
├── SECURITY.md
└── pyproject.toml
```

---

## Development

Install development dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

Run the test suite:

```bash
pytest
```

Run the same primary quality checks used by CI:

```bash
ruff check .
black --check .
bandit -r . -ll -x ./tests,./build,./dist
pytest --cov --cov-report=term-missing
```

The project currently declares a **70% minimum coverage threshold** in `pyproject.toml`.

### CI matrix

The GitHub Actions workflow currently defines test jobs for:

```text
Python 3.9
Python 3.10
Python 3.11
Python 3.12
```

and separately checks linting, formatting, security scanning, coverage, import/package behavior, and Docker image construction.

The CI badge at the top of this README is the source of truth for the current branch state; historical test counts in old upgrade reports should not be treated as current CI status.

---

## Docker

Build the image locally:

```bash
docker build -t zcoder:local .
```

Verify the packaged CLI:

```bash
docker run --rm zcoder:local --version
```

Credentials should be passed explicitly at runtime only for the provider paths you choose to enable.

---

## Security principles

ZCoder's security model is built around explicit boundaries rather than implicit trust:

- do not expose provider secrets to browser clients
- keep mutating actions behind explicit policy/approval boundaries
- isolate tenant-scoped data and operations
- validate filesystem paths and imported configuration
- avoid silent paid-provider fallback in zero-cost mode
- treat downloaded model artifacts as data, not automatically trusted executable code
- distinguish user-owned external runtimes from ZCoder-owned processes before lifecycle operations
- keep local analytics and telemetry local unless an external exporter is explicitly configured
- make audit/evidence status visible instead of upgrading mocks into production claims

See [`SECURITY.md`](SECURITY.md) for project security guidance.

---

## Evidence and release semantics

When evaluating a capability, ZCoder documentation should distinguish at least these situations:

1. **Implemented in source**
2. **Unit/contract tested**
3. **Integration tested with a controlled dependency**
4. **Verified against a real local/external runtime**
5. **Production verified in the target deployment**

Examples:

- A model listed in the catalog is **not** automatically installed.
- An adapter contract test is **not** proof that llama.cpp/Ollama/vLLM generated real tokens.
- A skipped browser test is **not** a web E2E pass.
- A zero-cost policy test is only strong evidence when prohibited paid transports are also observed to remain unused.

This distinction is intentional and is part of the project's release discipline.

---

## Documentation

Start here:

- [`QUICKSTART.md`](QUICKSTART.md) — basic setup and first commands
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — architecture and system boundaries
- [`ROADMAP.md`](ROADMAP.md) — planned and historical engineering direction
- [`CHANGELOG.md`](CHANGELOG.md) — release/change history
- [`SECURITY.md`](SECURITY.md) — security guidance
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — contribution workflow
- [`IMPLEMENTATION_CHECKLIST.md`](IMPLEMENTATION_CHECKLIST.md) — implementation tracking
- [`docs/`](docs/) — detailed audits, implementation reports and upgrade material

---

## Contributing

Contributions should preserve the project's primary invariants:

- no mandatory commercial dependency for the no-cost core
- no silent downgrade of security, tenant isolation or approval semantics
- no provider secrets in client-side code
- no fake/simulated evidence presented as real-runtime proof
- deterministic tests for routing, policy and failure paths
- backward compatibility where practical

Before opening a pull request, run:

```bash
ruff check .
black --check .
bandit -r . -ll -x ./tests,./build,./dist
pytest --cov --cov-report=term-missing
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full workflow.

---

## License

ZCoder is released under the [MIT License](LICENSE).

---

## Project status

ZCoder is an actively evolving engineering platform. The repository contains both mature integration surfaces and newer local-AI/control-plane subsystems. When deciding whether a capability is ready for a production environment, use the current CI result, release gates, real-runtime evidence, deployment-specific validation, and the documented limitations for that subsystem rather than relying on feature names alone.
