# ZCoder — Test Results (Independent Audit)

**Repository:** https://github.com/cvsz/zcoder  
**Branch:** `feat/zcoder-universal-remediation` (from `main` @ `121cc27`)  
**Audit date:** 2026-11-09  
**Auditor:** cvsz (independent re-verification)

## Scope

All checks below were executed locally against the working tree of this branch.
No production data, no external provider calls, no destructive operations.
PostgreSQL-backed integration/e2e tests were run via the disposable local
Docker container (`zPostgreSQL_network`, database `zcoder_db`, role `zcoder`)
provisioned by `scripts/local_postgres.py` (status: `zcoder_db ready for
zcoder (PostgreSQL 15.19)`). Python interpreter: the project validation venv
(`python 3.14` inside `.venv-validation`, per this machine's toolchain).

## Static analysis results

| Check | Command | Result | Evidence / notes |
|-------|---------|--------|------------------|
| Ruff lint | `ruff check .` | PASS | "All checks passed!" |
| Black format | `black --check .` | PASS | "508 files would be left unchanged" |
| mypy | `mypy src/zcoder webapp --ignore-missing-imports` | PASS | "Success: no issues found in 198 source files" |
| Bandit | `bandit -r src -q -ll` (exact CI command) | PASS | exit 0; 0 results (JSON verified) |
| pip-audit | `pip-audit -r requirements.txt -r requirements-dev.txt` (v2.10.1) | PASS | "No known vulnerabilities found" |
| ShellCheck | `shellcheck -S warning scripts/*.sh`; `shellcheck .github/scripts/post-review-comment.sh` | PASS | exit 0 (SC2034 fixed this round) |
| actionlint | `actionlint` v1.7.12 on all workflows | PASS | exit 0 (14 shellcheck + 1 invalid-`uses` issues fixed this round) |
| gitleaks | `gitleaks detect` full history (v8.30.1) | PASS | 723 commits; 0 leaks (8 reviewed historical FPs fingerprinted) |
| CodeQL | local CLI 2.27.4; suite `python-security-and-quality.qls` | PASS | tracked tree: 39 findings at baseline → **0** now |
| uv lock consistency | `uv lock --check` | PASS | exit 0 (93 packages) |
| Python compile (wheel import sanity) | `pip wheel --no-deps .` + wheel content assertions | PASS | zgpu packaged; zgpu tests excluded; dashboard assets present |

## Unit tests

`pytest tests/unit -q -p no:cacheprovider` — PASS (subset of full run below).

## Integration tests (with local PostgreSQL)

`scripts/local_postgres.py run -- pytest -q -p no:cacheprovider -p no:warnings`
— PASS. PostgreSQL-dependent live tests are exercised against the local
container (no unreachable-instance skips when provisioned).

## End-to-end tests

`pytest tests/e2e -q` — PASS (part of the full suite below).

## Full test suite (with PostgreSQL)

`scripts/local_postgres.py run -- pytest -q` — **exit 0** (PASS)

- **Collected:** 1947 tests
- **Failed:** 0
- **PostgreSQL-gated tests:** executed against the local container (the same
  run without DATABASE_URL skips them cleanly, exit 0 as well)

## Targeted regression tests added/updated this round

| Test | Purpose |
|------|---------|
| `src/zgpu/tests/test_model_registry_logging.py::test_model_registry_log_values_never_contain_line_breaks` (new) + updated strip test | asserts CR/LF cannot reach log sinks (log-injection) |
| `tests/unit/test_provider_adapter_cache.py::test_adapter_cache_uses_opaque_credential_id` (updated) | asserts opaque surrogate keying; no plaintext credential in cache keys |
| `tests/unit/test_observability_otel.py::test_trace_model_call_counts_success_and_failure` (updated) | reachable CFG form of the failing-call assertion |
| `tests/unit/test_public_api_safety.py`, `tests/unit/test_public_api_queue.py` (existing, still passing) | constant-message 403/409 envelopes retain visible permission scope |
| `tests/unit/codeagent/test_sessions_memory.py` (existing, still passing) | traversal + symlink rejection with the new `_path()` |

## Coverage

- Coverage target: `fail_under = 70` (`[tool.coverage.report]` in pyproject.toml).
- Coverage was not re-measured as a gating step this round; all tests pass and
  the CI test job measures coverage on the PR.

## Negative / failure-path testing

Exercised by existing suites plus this round's additions: invalid session IDs,
symlink targets, CRLF-forged log values, missing sandbox module (now
fail-closed), malformed API input, unauthorized/forbidden API access,
unavailable queue. No new failure-path regressions introduced.

## Status

**Overall: PASS** — all executable static-analysis, dependency, secret-scan
and test gates green on this branch's tree; CodeQL suite at 0 findings.

## What was NOT verified (disclosed)

- External provider integrations (Anthropic, Gemini, Ollama, xAI, NVIDIA NIM):
  no authorized budget; NOT VERIFIED for live calls (mocked only).
- GPU hardware / llama.cpp local inference runtime: not exercised beyond
  existing mocked tests this round.
- Production PostgreSQL / multi-tenant operation: not tested against
  production data.
- Windows-only installers (`install.cmd`, `setup.bat`, `build.bat`): not
  runnable on this Linux environment.
- `ruff format --check`: differs from black on pre-existing files (P3; CI gate
  is `black --check`).
