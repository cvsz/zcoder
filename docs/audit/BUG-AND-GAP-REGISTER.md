# ZCoder — Bug and Gap Register (Independent Audit)

**Repository:** https://github.com/cvsz/zcoder  
**Branch:** `main`  
**Initial HEAD:** `e868ee44dea4df7ae2d7ef1cccc1151e273ee8db`  
**Audit date:** 2026-11-08  
**Auditor:** cvsz

## Severity definitions

| Severity | Meaning |
|----------|---------|
| P0 | Exploitable security flaw, data corruption, authentication bypass, production outage |
| P1 | Major functionality failure, serious reliability or authorization defect |
| P2 | Incorrect behavior, missing critical validation, substantial maintainability issue |
| P3 | Low-risk cleanup, documentation, noncritical warning |

## Findings discovered

| ID | Severity | Subsystem | Finding | Evidence | Remediation | Test | Status |
|----|----------|-----------|---------|----------|---------------|------|--------|
| GZ-01 | P3 | Test coverage / zGPU | zGPU tests under `src/zgpu/tests/` are not in pytest `testpaths = ["tests"]`, so `make test` / CI `pytest` does not run them (they pass when run directly). | Confirm intent; if CI should run them, add `src/zgpu/tests` to `testpaths` (coverage.source remains `src/zcoder`, so coverage denominator unaffected). | Run `pytest src/zgpu/tests` — PASS (2 skips: pypdf) | NOT FIXED (observation only; no change made pending confirmation of intent) |
| RF-01 | P3 | Code formatting | `ruff format --check` reports 19 files would be reformatted, but CI gate is `black --check .` (PASS). ruff format and black conflict on line-wrapping; applying ruff format breaks black (5 files). | Document as known inconsistency; no change to avoid breaking the CI black gate. | `ruff check .` PASS; `black --check .` PASS | NOT FIXED (documented P3) |

## Bugs fixed

None. No bugs were discovered during this independent audit. All unit, integration, e2e, and zGPU tests pass; static analysis (ruff, black, mypy, bandit, shellcheck) passes.

## Security fixes fixed

None. No P0/P1 security findings; Bandit (0 medium, 0 high), ShellCheck, gitleaks clean.

## TODOs resolved

None required. All `pass`/abstract markers and broad `except Exception` handlers reviewed and confirmed intentional.

## Dependency upgrades

None performed. `uv lock --check` passes; dependencies kept at current pinned versions to avoid unneeded major upgrades (Anthropic SDK kept on v1 per CHANGELOG).

## Missing capabilities addressed

None. All discovered capabilities are either implemented and tested, or documented as limitations (external providers, GPU, production multi-tenant).

## Register status

**Status: CLEAR** — 0 P0, 0 P1, 0 P2 bugs; 2 P3 observations documented (GZ-01, RF-01); no fixes required; no open release blockers.
