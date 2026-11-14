# ZCoder — Repository Inventory

**Repository:** https://github.com/cvsz/zcoder
**Branch:** `fix/zcoder-defensive-fallback` @ `9a0cb1d`
**Date:** 2026-11-08

## Programming Languages

| Language | Usage |
|----------|-------|
| Python | Primary application code (`src/zcoder/`, `src/zgpu/`, `scripts/`, `tests/`, `main.py`) |
| TypeScript | ZCoder SDK (`zcoder-sdk.ts`) |
| Shell | Build scripts (`build.sh`, `setup.sh`, `deploy/docker/zpitr/*.sh`) |
| JSON | Configuration (`pyproject.toml`, `uv.lock`, `config.json`, workflow files) |
| YAML | Docker Compose (`docker-compose.yml`, `docker-compose.zpitr.yml`) |
| Markdown | Documentation (`docs/`, `README.md`, `CHANGELOG.md`) |
| Dockerfile | Container definition (`Dockerfile`) |
| SVG | Assets (`social-preview.svg`) |
| BAT | Windows build (`build.bat`, `install.cmd`, `setup.bat`) |

## Frameworks and Runtimes

| Framework | Purpose |
|-----------|---------|
| FastAPI | Web console and API server |
| Click/Typer | CLI patterns |
| Textual | Terminal UI (TUI) |
| pytest | Test framework |
| ruff | Linting and formatting |
| black | Code formatting |
| mypy | Type checking |
| bandit | Security scanning |
| Docker | Containerization |
| PostgreSQL | Enterprise database |
| SQLite | Single-user default database |
| uv | Python package management |

## Source Tree Structure

```
src/zcoder/           # Core application (domain, agent, services, api, interfaces)
src/zgpu/             # zGPU acceleration layer (dashboard, kernels, runtime, compiler)
scripts/              # Utility and maintenance scripts
tests/                # Unit, integration, e2e tests
webapp/               # Web console frontend
deploy/               # Deployment configuration (Docker, zPITR)
docs/                 # Documentation
skills/               # Skill definitions
```

## Application Entry Points

- `main.py` — CLI entry point (`zcoder` command)
- `src/zcoder/interfaces/cli/` — CLI, TUI, maintenance campaign modules
- `src/zcoder/api/` — FastAPI API server

## Domain Modules

- `src/zcoder/domain/` — Core domain (models, services, interfaces)
- `src/zcoder/agent/` — Agent runtime (CodeAgent, sessions, orchestration)
- `src/zcoder/services/` — Background services (workers, backup, maintenance)
- `src/zcoder/enterprise/` — Enterprise features (no-cost platform, local AI)
- `src/zcoder/api/` — Public and internal API

## Infrastructure Modules

- `src/zcoder/infrastructure/` — Infrastructure concerns (auth, OIDC)
- `src/zgpu/` — zGPU acceleration (dashboard, kernels, runtime, compiler, cluster)

## Database Layers

- SQLite (default, single-user)
- PostgreSQL (enterprise mode, via `zpostgressql` Docker container)
- `EngineeringStore`, `PortfolioStore` abstractions

## External Integrations

- GitHub (PR/issue orchestration)
- Anthropic, Gemini, xAI, Ollama, local model providers
- NVIDIA NIM (routed requests)
- Cloudflare (RSS monitoring for infrastructure changes)
- Stripe (billing adapter interface)

## Build System

- `uv` (Python package management, lockfile)
- `pyproject.toml` (project configuration)
- `Dockerfile` (container build)
- `docker-compose.yml` (local development stack)
- `Makefile` (build, test, deploy targets)

## Dependency Managers

- Python: `uv` with `uv.lock`
- System: Docker containers

## Deployment Methods

- Docker Compose (local development)
- Docker image (`zcoder:latest`)
- Kubernetes (Helm charts referenced in CI)

## Test Framework

- pytest with asyncio support
- Coverage target: 70%
- Unit, integration, and e2e test suites

## CI Workflows

- `.github/workflows/ci.yml` — lint, security, test, docker-build
- `.github/workflows/helm-lint.yml` — Helm lint
- `.github/workflows/security-scan.yml` — Security scanning

## Security Controls

- SEC-001 through SEC-011 (all closed and verified)
- Bandit, gitleaks, CodeQL scanning
- GPG-signed commits
- Actions pinned to immutable SHAs

## Existing TODO/FIXME/HACK Markers

Reviewed; all `pass` statements in interface/abstract classes are intentional. No critical TODOs or FIXMEs found. See docs/audit/bugs-and-todos.md.
