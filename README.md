# ZCoder CLI — Enterprise Edition

ZCoder is an enterprise-grade, local-first coding agent runtime. It ships a
plugin system, hook bus, autonomous CodeAgent, multi-modal orchestration,
RAG, workflow engine, durable engineering runtime (jobs/leases/fencing),
multi-tenant control plane, and full observability — with all inference
routed through loopback model endpoints by default and no silent cloud
fallback.

- **Package:** `zcoder` (Python >= 3.12)
- **Entry points:** `zcoder`, `zcoder-server` / `zcoder-api`
- **License:** MIT

## Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
zcoder --help
zcoder --health-check          # local component health
zcoder --health-check-deep     # includes local model endpoint probe
```

Local inference uses the loopback model server controller
(`scripts/model_server.py`, GGUF sectors on 127.0.0.1). Hosted model APIs
are never called by the local workflow; when local inference is unavailable
the CLI reports the error explicitly instead of falling back to the cloud.

## Project Layout

| Path | Purpose |
|------|---------|
| `src/zcoder/agent/` | Agent runtime, plugins, hooks, MCP, tools, RAG, workflows, audio, multi-modal, TUI, agent communication (JSON-RPC 2.0) |
| `src/zcoder/enterprise/` | Policy engine, RBAC, audit log, local AI stack, zero-cost platform |
| `src/zcoder/services/` | GitHub orchestration, maintenance intelligence, upgrade ledger, release gates |
| `src/zcoder/infrastructure/` | PostgreSQL/SQLite stores, OTel/Prometheus observability |
| `src/zcoder/interfaces/` | CLI, TUI, REST API, web console |
| `src/zcoder/worker/` | Durable job workers with tenant queues |
| `tests/` | Unit, integration, e2e suites (PostgreSQL-backed tests run via `scripts/local_postgres.py`) |
| `docs/` | Architecture, operations, security, upgrade notes, parity program |

## Quality Gates

All gates run in CI (`.github/workflows/ci.yml`) and are green locally:

| Gate | Command |
|------|---------|
| Lint | `ruff check .` |
| Format | `black --check` (changed files) |
| Types | `mypy src/zcoder webapp --ignore-missing-imports` |
| Security | `bandit -r src -ll` |
| Shell | `shellcheck` on all tracked `.sh` scripts |
| Tests | `pytest tests/ --cov` (coverage gate `fail_under=70`; current 79.47%) |

PostgreSQL-backed tests use the local stack:
`python scripts/local_postgres.py run -- .venv/bin/python -m pytest tests/ -q`

## Documentation

- `Final-Report.md` — release validation report (quality gates, architecture, governance)
- `IMPLEMENTATION_PLAN.md` / `IMPLEMENTATION_PLAN_EXECUTION.md` — phase plan and execution status
- `CHANGELOG.md` — per-release changes
- `docs/DEVELOPER-PORTAL.md` — REST API / SDK integration guide
- `docs/zcoder-master.md`, `docs/architecture/`, `docs/operations/` — deep references

## Governance

Merges to `main` require a GPG-signed commit from the author (`cvsz`) and an
independent approving review from the reviewer account (`policedbc`) via the
protected-branch workflow. No direct pushes; no self-approval.
