# ZCoder — Test Results (Independent Audit)

**Repository:** https://github.com/cvsz/zcoder  
**Branch:** `main`  
**Initial HEAD:** `e868ee44dea4df7ae2d7ef1cccc1151e273ee8db`  
**Audit date:** 2026-11-08  
**Auditor:** cvsz (independent re-verification of prior audit baseline)

## Scope

All checks below were executed locally against a clean checkout of `main` at the initial HEAD. No production data, no external provider calls, no destructive operations. PostgreSQL-backed integration tests were run against a disposable local Docker container (`zpostgresql:15-alpine` on `zPostgreSQL_network`, database `zcoder_db`, role `zcoder`) provisioned via `scripts/local_postgres.py`. Python interpreter: `3.12.15` (project venv `.venv`).

## Python toolchain

| Tool | Version | Source |
|------|---------|--------|
| Python | 3.12.15 | `.venv` |
| ruff | 0.16.5 | dev dependency |
| black | (bundled) | dev dependency |
| mypy | 2.3.1 | dev dependency |
| bandit | 1.9.4 | dev dependency |
| pytest | 9.1.1 | dev dependency |
| uv | (system) | lockfile management |

## Static analysis results

| Check | Command | Result | Evidence / notes |
|-------|---------|--------|------------------|
| Python compile | `python -m compileall -q src tests` | PASS | exit 0; all modules compile |
| Ruff lint | `ruff check .` | PASS | "All checks passed!" exit 0 |
| Black format | `black --check .` | PASS | "500 files would be left unchanged" exit 0 |
| mypy | `mypy src/zcoder webapp --ignore-missing-imports` | PASS | "Success: no issues found in 197 source files" exit 0 |
| Bandit | `bandit -r src/zcoder -ll` | PASS | "No issues identified"; 95 low informational, 0 medium, 0 high; 23 justified `#nosec` |
| ShellCheck | `shellcheck` on all `*.sh` (excl. `.git`, venvs) | PASS | exit 0; one informational SC2034 (unused var) in `.github/scripts/post-review-comment.sh` |
| bash -n | `bash -n` on all `*.sh` | PASS | no syntax errors |
| uv lock consistency | `uv lock --check` | PASS | "Resolved 64 packages" exit 0 |
| ruff format | `ruff format --check .` | NOT GATE | 19 files would be reformatted; conflicts with black (see P3 observation RF-01) |

## Unit tests

`pytest tests/unit -q -p no:cacheprovider` — PASS

- All unit tests pass.
- 4 skips (missing optional dependencies, not defects):
  - `tests/unit/codeagent/test_web.py` — `httpx` not installed
  - `tests/unit/test_oidc_token_validation.py` — `jwt` not installed
  - `tests/unit/test_webapp_local_security.py` — `httpx` not installed
  - `tests/unit/test_performance_targets.py` — `psutil` not installed

## Integration tests (with local PostgreSQL)

`scripts/local_postgres.py run -- pytest tests/integration -q -p no:cacheprovider` — PASS

- All runnable integration tests pass.
- PostgreSQL-dependent live tests were exercised against the local `zpostgresql` container; tests that require an unreachable instance skip cleanly (not defects).

## End-to-end tests

`pytest tests/e2e -q -p no:cacheprovider` — PASS (part of full suite below).

## Full test suite (with PostgreSQL)

`scripts/local_postgres.py run -- pytest -q -p no:cacheprovider` — PASS

- **Passed:** all collected tests
- **Skipped:** 4 (optional deps httpx/jwt/psutil) — not defects
- **Failed:** 0
- PostgreSQL-dependent integration tests were run against the local container and passed; none were skipped for PostgreSQL-unreachable when the container was provisioned.

## zGPU tests (observed, not in CI `testpaths`)

`pytest src/zgpu/tests -q -p no:cacheprovider` — PASS

- zGPU tests pass when run directly.
- Gap: `pyproject.toml` `testpaths = ["tests"]`, so `src/zgpu/tests/` is **not** executed by `make test` / CI `pytest`. Documented as observation GZ-01 (see BUG-AND-GAP-REGISTER). No change made without confirming intent.

## Coverage

- Coverage target: `fail_under = 70` (`[tool.coverage.report]` in pyproject.toml)
- Coverage measured over `src/zcoder` only; legacy/optional compatibility surfaces excluded from aggregate denominator (documented in pyproject.toml `[tool.coverage.run]` omit list).
- Coverage was not re-measured as a gating step for this audit; all tests pass.

## Negative / failure-path testing

Failure-path behavior is exercised by existing unit/integration suites (invalid config, missing env, unavailable services, unauthorized access, malformed input, database disconnect, retry exhaustion, migration failure). No new failure-path regressions introduced in this audit.

## Status

**Overall: PASS** — all applicable static-analysis and test gates green on the initial HEAD. No regressions introduced.

## What was NOT verified (disclosed)

- External provider integrations (Anthropic, Gemini, Ollama, xAI, NVIDIA NIM): no authorized budget; marked NOT VERIFIED / BLOCKED for live calls. Mocked only.
- GPU hardware / llama.cpp local inference runtime: not exercised beyond existing mocked tests.
- Production PostgreSQL / multi-tenant operation: not tested against production data.
- Windows-only installers (`install.cmd`, `setup.bat`, `build.bat`): not runnable on this Linux environment.
- `ruff format --check`: 19 files differ from ruff format style; CI gate is `black --check` which passes. Documented as P3 RF-01.
