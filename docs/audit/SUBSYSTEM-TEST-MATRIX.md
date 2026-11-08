# ZCoder — Subsystem Test Matrix (Independent Audit)

**Repository:** https://github.com/cvsz/zcoder  
**Branch:** `main`  
**Audit date:** 2026-11-08  
**Auditor:** cvsz  
**Execution:** Local, against `main` at initial HEAD, Python 3.12.15 (`.venv`), local PostgreSQL container (`zpostgresql`) provisioned via `scripts/local_postgres.py`. No production data, no external provider calls.

Legend: Implemented = code exists; Tested = covered by executed tests; Operational = CI gate / real integration verified; Planned = described but not verified.

| Subsystem | Status | Evidence | Remaining risk |
|-----------|--------|----------|----------------|
| Core security (`safe_resolve`, path containment, secret detection, child env isolation, URL validation) | Implemented / Tested / Operational | `bandit -r src/zcoder -ll` PASS; unit tests pass; `src/zcoder/core/security.py` reviewed | None open |
| Domain models & services (tenant, engineering, portfolio, product, admission, policy engine, outbox) | Implemented / Tested | unit + integration tests pass; mypy PASS | None open |
| API server (FastAPI, auth, public v1) | Implemented / Tested | unit tests pass; `src/zcoder/api/` reviewed | External provider calls not live-tested |
| CLI / TUI / maintenance campaign | Implemented / Tested | unit tests pass | Desktop GUI not exercised on Linux headless |
| Services (workers, orchestrator, backup/restore, release gate, maintenance, messaging) | Implemented / Tested | integration tests pass (with Postgres) | Production multi-tenant not tested |
| Database (SQLite default, PostgreSQL enterprise, stores, migrations, outbox, leases, fencing) | Implemented / Tested / Operational | integration tests pass against local `zpostgresql`; `scripts/local_postgres.py status` ready | Production DB not tested |
| zGPU (simulator, compiler, runtime, kernels, cluster, LLM, dashboard, benchmarks) | Implemented / Tested | `pytest src/zgpu/tests` PASS (2 pypdf skips) | Not in CI `testpaths` (observation GZ-01); GPU not available |
| Agent / CodeAgent / orchestration / sessions / RAG / tools | Implemented / Tested | unit tests pass | None open |
| CI / workflows (lint, security, test, docker-build, release, helm, sdk, reproducibility) | Implemented / Operational | workflows inspected; actions pinned to SHAs | Production release gate is manual |
| Supply chain (`uv.lock`, Dependabot, pinned actions, SBOM/provenance in release workflows) | Implemented / Operational | `uv lock --check` PASS; actions pinned | Artifact publishing requires human gate |
| Security scanning (Bandit, ShellCheck, gitleaks, CodeQL) | Implemented / Operational | Bandit/ShellCheck PASS; gitleaks config present | External provider not live-tested |

## Test levels

| Level | Command | Result |
|-------|---------|--------|
| Static analysis | compileall, ruff, black, mypy, bandit, shellcheck, bash -n, uv lock --check | All PASS |
| Unit tests | `pytest tests/unit` | PASS (4 optional-dep skips) |
| Integration tests | `scripts/local_postgres.py run -- pytest tests/integration` | PASS |
| E2E tests | `pytest tests/e2e` | PASS |
| Full suite | `scripts/local_postgres.py run -- pytest -q` | PASS (0 failed) |
| zGPU tests | `pytest src/zgpu/tests` | PASS (not in CI testpaths) |
