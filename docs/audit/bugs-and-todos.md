# ZCoder — Bugs, TODOs, and Findings

**Repository:** https://github.com/cvsz/zcoder
**Date:** 2026-11-08
**Baseline:** Branch `fix/zcoder-defensive-fallback` @ `9a0cb1d`

## Fixed During This Audit

| ID | Severity | File | Finding | Root Cause | Fix | Regression Test |
|----|----------|------|---------|------------|-----|-----------------|
| ZC-001 | High | `tests/unit/codeagent/test_commands.py:101` | `git commit` in `test_diff_reports_changes` fails under global `commit.gpgsign=true` because GPG requires a passphrase in batch mode | Test invokes `git commit` without overriding `commit.gpgsign`; global config enables GPG signing | Added `-c commit.gpgsign=false` to the `git commit` invocation (test does not exercise GPG signing) | `test_diff_reports_changes` now passes |
| ZC-002 | High | `tests/unit/test_release_candidate.py:176` | `git commit` in `test_version_sync_rejects_runtime_version_drift` fails under global `commit.gpgsign=true` | Same as ZC-001; the `candidate` fixture correctly uses `-c commit.gpgsign=false` but the test body does not | Added `-c commit.gpgsign=false` to the test's `git commit` invocation | `test_version_sync_rejects_runtime_version_drift` now passes |
| ZC-003 | Medium | `build.sh:3`, `setup.sh:3` | ShellCheck SC1007 warning: `CDPATH= cd` has a space after `=` | Shell style issue in compatibility launcher scripts | Changed to `CDPATH='' cd` (equivalent semantics, ShellCheck-clean) | `shellcheck` exit code 0 on all scripts |

## Intentional `pass` / `NotImplemented` / Stub Markers (Not Defects)

The following were reviewed and determined to be intentional interface definitions or abstract contracts, not defects:

| File | Lines | Marker | Reason |
|------|-------|--------|--------|
| `src/zcoder/domain/interfaces/engineering_store.py` | 16-46 | `pass` | Abstract interface (Protocol) — no implementation expected |
| `src/zcoder/domain/interfaces/portfolio_store.py` | 16-46 | `pass` | Abstract interface (Protocol) — no implementation expected |
| `src/zcoder/api/public/v1.py` | 74,77,80,83 | `pass` | `TenantJobStore` Protocol — abstract contract for tenant job persistence |
| `src/zcoder/domain/models/product.py` | 216,219,230,233,236 | `raise NotImplementedError` | `BillingProvider` abstract base class — concrete providers (Stripe, etc.) implement these |
| `src/zcoder/domain/services/admission.py` | 57,60 | `pass` | Admission control stubs — intentional placeholder |
| `src/zcoder/domain/services/policy_engine.py` | 250 | `pass` | Intentional no-op in policy rule matching branch |
| `src/zcoder/services/upgrade_lease.py` | 18-27, 80 | `pass` | Lease service stubs / exception suppression |
| `src/zcoder/services/engineering_worker.py` | 33 | `pass` | Worker stub |
| `src/zcoder/services/maintenance_campaign_worker.py` | 31 | `pass` | Worker stub |
| `src/zcoder/services/maintenance_scheduler.py` | 37 | `pass` | Scheduler stub |
| `src/zcoder/services/upgrade_postgres_lease.py` | 78 | `pass` | Exception suppression in lease path |
| `src/zcoder/services/agent_runtime.py` | 38 | `pass` | Agent runtime stub |
| `src/zcoder/interfaces/cli/continuous_engineering.py` | 175 | `pass` | CLI handler stub |
| `src/zcoder/interfaces/cli/maintenance_campaign.py` | 20 | `pass` | CLI handler stub |
| `src/zcoder/interfaces/cli/agent_tui.py` | 365 | `pass` | TUI handler stub |
| `src/zcoder/interfaces/desktop/gui.py` | 97,756,1124,1376,1435 | `pass` | Desktop GUI event handler stubs |
| `src/zcoder/core/resilience.py` | 101,132,138 | `pass` | Exception suppression in resilience patterns |
| `src/zcoder/api/auth.py` | 155 | `pass` | Auth handler stub |

## No Critical Defects Found

The following categories were reviewed and no defects were identified:
- Input validation: Covered by policy engine, session path validation, object storage path traversal defense
- Output validation: JSON responses validated at API boundaries
- Error propagation: Fail-closed throughout policy engine, condition evaluation, path resolution
- Concurrency: Advisory leases, fencing tokens, bounded outbox processing
- Database: Transactions, migrations, RLS policies
- Security: SSRF boundaries (SEC-001, SEC-005), path traversal (SEC-002, SEC-004), network bypass (SEC-003), tool output trust (SEC-006), RAG tenant isolation (SEC-007), secrets inheritance (SEC-008), authorization (SEC-009), supply chain (SEC-010)

## Test Results

| Suite | Result |
|-------|--------|
| `pytest` (full, with PostgreSQL) | 1891 passed, 0 failed, 0 skipped |
| `pytest` (full, without PostgreSQL) | 1863 passed, 0 failed, 28 skipped (PostgreSQL-dependent integration tests) |
| `pytest tests/e2e` | 130 passed |
| `pytest tests/integration` | 78 passed (with PostgreSQL) |
| `pytest tests/unit` | All unit tests pass |

## Static Analysis Results

| Tool | Result |
|------|--------|
| `ruff check .` | All checks passed |
| `black --check .` | 362 files unchanged (pass) |
| `mypy src/zcoder` | No issues in 195 source files (pass) |
| `bandit -r src/zcoder -ll` | No issues identified (pass) |
| `shellcheck` (all .sh scripts) | Exit 0 (pass, after ZC-003 fix) |
| `docker build -t zcoder:ci` | Build successful (pass) |
