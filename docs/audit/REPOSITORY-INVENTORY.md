# ZCoder — Repository Inventory (Independent Audit)

**Repository:** https://github.com/cvsz/zcoder  
**Owner:** cvsz  
**Default branch:** `main`  
**Initial HEAD:** `e868ee44dea4df7ae2d7ef1cccc1151e273ee8db`  
**Audit date:** 2026-11-08  
**Auditor:** cvsz  
**Source:** Direct source-tree inspection (single source of truth); no capabilities assumed from README alone.

## Programming languages

| Language | Usage |
|----------|-------|
| Python | Primary application code (`src/zcoder/`, `src/zgpu/`, `scripts/`, `tests/`, `main.py`) |
| TypeScript | ZCoder SDK (`zcoder-sdk.ts`) |
| Shell | Build/deploy scripts (`build.sh`, `setup.sh`, `deploy/`, `.github/scripts/`) |
| JSON / TOML / YAML | Configuration (`pyproject.toml`, `uv.lock`, `config.json`, workflows, Docker Compose) |
| Markdown | Documentation (`docs/`, `README.md`, `CHANGELOG.md`) |
| Dockerfile | Container definition (`Dockerfile`) |
| SVG | Assets (`social-preview.svg`) |
| BAT / CMD | Windows build/install (`build.bat`, `install.cmd`, `setup.bat`) |

## Tracked file count

- 932 tracked files (`git ls-files \| wc -l`)
- Working tree clean at initial HEAD (`main...origin/main`, no uncommitted changes)

## Frameworks and runtimes

| Framework / tool | Purpose |
|------------------|---------|
| Python >=3.12 | Application runtime (`requires-python = ">=3.12"`) |
| FastAPI / uvicorn / starlette | Web console and API server (`web` extra) |
| Textual | Terminal UI (TUI) |
| Click/Typer patterns | CLI commands |
| pytest / pytest-asyncio / pytest-cov | Test framework |
| ruff / black / mypy / bandit | Lint, format, type, security |
| PostgreSQL 15 | Enterprise database (`zcoder_db`, role `zcoder`) |
| SQLite | Single-user default database |
| uv | Python package management (lockfile `uv.lock`) |
| Docker / Docker Compose | Containerization and local stack |
| Helm | Kubernetes deployment (referenced in CI `helm-lint.yml`) |

## Source tree structure

```
src/zcoder/   Core application: domain, agent, api, core, config,
              enterprise, infrastructure, interfaces, services, worker
src/zgpu/     zGPU acceleration layer: dashboard, kernels, runtime,
              compiler, cluster, llm, simulator, agents, agi, tests
scripts/      Utility, maintenance, postgres provisioning, release scripts
tests/        Unit, integration, e2e test suites
webapp/       Web console frontend
deploy/       Deployment configuration (Docker, zPITR)
docs/         Documentation
skills/       Skill definitions
models/       Model artifacts
main.py       CLI entry point (`zcoder` command)
```

## Application entry points

- `main.py` — CLI entry point (`zcoder` command; `zcoder.main:main`)
- `src/zcoder/interfaces/cli/` — CLI, TUI, maintenance campaign modules
- `src/zcoder/api/` — FastAPI API server (`zcoder.api.server:start`)

## Domain modules

- `src/zcoder/domain/models/` — Tenant, engineering, portfolio, product, intelligence, residency models
- `src/zcoder/domain/services/` — Admission, deployment, control plane, policy engine, outbox policy
- `src/zcoder/domain/interfaces/` — Engineering store, portfolio store (Protocol contracts)

## Agent / orchestration

- `src/zcoder/agent/` — Agent runtime: CodeAgent, capabilities, orchestration, sessions, RAG, tools, integrations, eval, enterprise hooks/perms
- `src/zcoder/services/` — Background services: workers, orchestrator, backup/restore, maintenance, release gate, upgrade loop, messaging

## Infrastructure modules

- `src/zcoder/core/security.py` — Centralized path containment (`safe_resolve`), secret detection, child-process env isolation (`build_child_env`), URL scheme validation
- `src/zcoder/core/outbound_security.py` — Outbound network security review
- `src/zcoder/core/provider_policy.py` — Provider policy (local-mode disables hosted API access)
- `src/zcoder/core/resilience.py` — Retry/backoff with explicit argv (no implicit shell=True)
- `src/zcoder/infrastructure/auth/` — Auth / OIDC infrastructure
- `src/zcoder/infrastructure/stores/` — Postgres/SQLite store implementations
- `src/zcoder/api/auth.py` — API authentication
- `src/zcoder/api/public/v1.py` — Public API v1

## zGPU component

- `src/zgpu/` — GPU simulator, compiler, runtime, kernels, cluster, LLM client/loaders (GGUF/safetensors), integrations, dashboard, benchmarks, self-coding, with dedicated tests under `src/zgpu/tests/`.

## Database layers

- SQLite (default, single-user)
- PostgreSQL (enterprise mode, via `zpostgressql` Docker container)
- `EngineeringStore`, `PortfolioStore` abstractions; `upgrade_postgres_*` lease/fence/runtime services; outbox and upgrade store ledger

## External integrations

- GitHub (PR/issue orchestration via `github_orchestrator.py`)
- Anthropic, Gemini, xAI, Ollama, local model providers
- NVIDIA NIM (routed requests)
- Cloudflare (RSS monitoring for infrastructure changes)
- Stripe (billing adapter interface — abstract `BillingProvider`)
- MCP servers / plugins / hooks (tool boundaries documented in SECURITY.md)

## Build system

- `uv` with `uv.lock` (deterministic, reproducible; `uv lock --check` passes)
- `pyproject.toml` (setuptools build backend, src layout)
- `Dockerfile` (container build)
- `docker-compose.yml` / `docker-compose.zpitr.yml` (local dev stack)
- `Makefile` (build, test, lint, typecheck, security, check targets)

## Test framework

- pytest with asyncio support
- Coverage target `fail_under = 70`
- Unit (`tests/unit`), integration (`tests/integration`), e2e (`tests/e2e`) suites
- zGPU tests under `src/zgpu/tests/` (not in pytest `testpaths`; see observation GZ-01)

## CI workflows (`.github/workflows/`)

| Workflow | Purpose |
|----------|---------|
| ci.yml | lint, security (bandit), test (py 3.12/3.13 + postgres service), docker-build |
| security-scan.yml | Security scanning |
| dependency-review.yml | Dependency review on PRs |
| codeql.yml | CodeQL analysis |
| release.yml / release-gate.yml | Release and release gating |
| publish-container.yml | Container publication (gated) |
| helm-lint.yml | Helm chart lint |
| sdk-check.yml | SDK/TypeScript validation |
| reproducibility.yml | Reproducibility check |
| auto-fix-open-prs.yml | Auto-fix workflow |
| automated-audit-review-approve.yml | Automated audit review |
| pages.yml | Pages deployment |

All `uses:` action refs pinned to immutable full-length commit SHAs (per SECURITY.md SEC-010).

## Security controls

- Centralized canonical path containment via `zcoder.core.security.safe_resolve()`
- Secret detection/redaction (`sk-ant-...`, `Authorization`, `x-api-key` redacted in logs)
- Child-process environment isolation (`is_secret_env_name` / `build_child_env`)
- HTTPS-only scheme validation
- Fail-closed authorization/approval boundaries (policy engine mini-parser, no `eval()`)
- Non-root container execution; build-context secret exclusions
- CodeQL, Dependency Review, Release Gate, Bandit, gitleaks scanning
- GPG-signed commits; actions pinned to immutable SHAs
- SEC-001 through SEC-011 (all closed per prior audit)

## Existing TODO/FIXME/HACK markers

Reviewed; all `pass` statements in interface/abstract classes are intentional (see prior audit `bugs-and-todos.md`). No critical TODOs or FIXMEs found. Broad `except Exception` handlers are intentional fail-closed / keep-alive patterns (domain admission rejects on backend error; deployment health degrades gracefully; UI stays alive on generation failure).
