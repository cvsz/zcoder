# ZCoder — Issue Backlog (Independent Audit)

**Repository:** https://github.com/cvsz/zcoder  
**Owner:** cvsz  
**Audit date:** 2026-11-08  
**Auditor:** cvsz  
**Source:** GitHub API `GET /repos/cvsz/zcoder/issues?state=all&per_page=100`, paginated until exhausted via `gh api --paginate`.

## Enumeration result

| Category | Count |
|----------|-------|
| Total issues discovered | 173 |
| Open | 0 |
| Closed | 173 |
| Pagination coverage | Complete (all pages returned; no further pages) |

## Open issues

None. There are **no open issues** requiring triage or action.

## Security alerts / dependency updates

No open security alerts or dependency updates were found in this enumeration. Dependabot PRs (closed without merge) are catalogued in `docs/audit/PR-INVENTORY.md` (#100, #106, #107, #110, #112, #139, #141); their dependency changes were either superseded by later updates or not adopted, and no functionality is missing from `main`.

## TODO / FIXME / HACK / placeholder markers in source

Reviewed across `src/zcoder`, `src/zgpu`, `scripts` (Python). Findings:
- All `pass` statements in interface/abstract classes are intentional Protocol/abstract contracts (not defects).
- Broad `except Exception` handlers are intentional fail-closed / keep-alive patterns:
  - Domain admission rejects on backend error (`admission.py:100`) — fail-closed.
  - Deployment health degrades to DEGRADED on DB error (`deployment.py:78`) — graceful.
  - TUI/GUI stay alive on generation/stream failure — intentional UX resilience.
  - Several are bandit-`#nosec`-suppressed with justification.
- `raise NotImplementedError` in `domain/models/product.py` `BillingProvider` — abstract base; concrete providers (Stripe, etc.) implement these.
- No critical TODOs, FIXMEs, XXX, HACK, or temporary workarounds found that require remediation.

## Stale / duplicate / abandoned work

- All closed draft PRs (#62, #117, #123, #136, #137, #138, #146) are abandoned/incomplete; branches deleted from remote; no functionality missing from `main`.
- No unresolved review threads requiring action on current `main`.

## Test gaps / flaky test reports

- No flaky tests reported; full suite deterministic.
- 4 tests skip when optional deps (httpx, jwt, psutil) are missing — expected, not defects.
- PostgreSQL-backed integration tests skip when the local `zpostgresql` container is unavailable — expected; pass when provisioned.
- zGPU tests (`src/zgpu/tests/`) are not in pytest `testpaths` — observation GZ-01 (see BUG-AND-GAP-REGISTER).

## Release blockers

None. No open release blockers.

## Backlog status

**Status: CLEAR** — 0 open issues, 0 open PRs, no security alerts, no release blockers, no critical TODO/FIXME/HACK markers requiring remediation. All discovered items have a documented disposition.
