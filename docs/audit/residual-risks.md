# ZCoder — Residual Risks

**Repository:** https://github.com/cvsz/zcoder
**Date:** 2026-11-08

## Residual Risk Register

| ID | Risk | Severity | Likelihood | Impact | Mitigation | Owner |
|----|------|----------|------------|--------|------------|-------|
| RR-001 | PR #168 not yet merged to main; security hardening not in production | Medium | High | High | Merge PR #168 via controlled release process after policedbc approval | cvsz |
| RR-002 | PRs #165, #166, #167 have deleted head branches; cannot be merged or reviewed | Low | Medium | Low | Close as DUPLICATE/BLOCKED; recover branches if work is still needed | cvsz |
| RR-003 | `ruff format --check` reports 19 files would be reformatted | Low | High | Low | Run `ruff format` on in-scope files (not a CI gate) | cvsz |
| RR-004 | 28 integration tests skip without PostgreSQL | Low | High | Low | Expected behavior; PostgreSQL is required for integration tests | N/A |
| RR-005 | `commit.gpgsign=true` breaks tests that do `git commit` without overriding | Low | Medium | Medium | Tests now use `-c commit.gpgsign=false`; CI does not run tests with GPG signing | cvsz |

## Accepted Risks

All risks above are accepted with the mitigations described. No risk is unmitigated or unaccepted.

## Risks Requiring Action

| ID | Action | Deadline |
|----|--------|----------|
| RR-001 | Complete policedbc review and cvsz merge of PR #168 | Before production release |
| RR-002 | Close PRs #165, #166 as DUPLICATE; close #167 as BLOCKED or recover branch | Before PR cleanup |
