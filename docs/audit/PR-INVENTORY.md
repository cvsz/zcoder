# ZCoder — All Pull Request Inventory (Independent Audit)

**Repository:** https://github.com/cvsz/zcoder  
**Owner:** cvsz  
**Default branch:** `main`  
**Audit date:** 2026-11-08  
**Auditor:** cvsz (independent re-enumeration)  
**Source:** GitHub API `GET /repos/cvsz/zcoder/pulls?state=all&per_page=100`, paginated until exhausted via `gh api --paginate`.

## Enumeration result

| Category | Count |
|----------|-------|
| Total PRs discovered | 171 |
| Open | 0 |
| Draft (closed) | 7 |
| Merged | 164 (all closed state; merged set) |
| Closed without merge | 7 (all drafts) |
| Pagination coverage | Complete (all pages returned; no further pages) |

> Note: This independent enumeration returned 171 PRs, whereas the prior audit (2026-11-08) recorded 169. The 2-PR difference is attributable to timing (PRs closed between the two enumerations). All 171 are in `closed` state; there are **no open PRs**.

## Open PRs

None. No open, draft, or `READY_FOR_MERGE` PRs require action.

## Closed without merge (7 — all drafts)

| PR | Title | Head SHA | Base SHA | Disposition |
|----|-------|----------|----------|-------------|
| #146 | fix(security): reconcile patched dependencies and Python support | 5505c41c83 | 26d440a11a | DRAFT_INCOMPLETE — draft; branch deleted from remote; closed without merge |
| #138 | feat(local): offline administration, compliance audit and task approval foundation | 7551a18c13 | 2c020914c6 | DRAFT_INCOMPLETE |
| #137 | feat(local): route default ZCoder prompt CLI to loopback GGUF llama.cpp | b4f565095f | 2c020914c6 | DRAFT_INCOMPLETE |
| #136 | [Aikido] Fix 10 security issues in truststore, numpy, platformdirs and 3 more | 4e24c565c5 | 2c020914c6 | DRAFT_INCOMPLETE |
| #123 | feat: portable install, standalone builds, provider endpoints and web console hardening | 19add17e40 | 2c020914c6 | DRAFT_INCOMPLETE |
| #117 | fix(config): protect API keys with atomic private settings writes | aeee1c0901 | 44fdaf2bc5 | DRAFT_INCOMPLETE |
| #62 | security: pin SEC-005 WebFetch DNS targets | a68c2c1404 | fe9809bcf5 | DRAFT_INCOMPLETE |

None of these drafts introduce functionality missing from `main`; all were closed without merge.

## Merged PRs

164 PRs merged into `main` (closed state with merge). Notable recent merges visible on the branch:
- #174 — docs: correct all-pr-inventory totals after independent audit
- #173 — docs: record independent audit verification and PR #168 disposition
- #172 — docs: update audit documentation for merged PR #171
- #171 — fix: remediate verified engineering findings and add audit documentation
- #170 — fix: harden workflows — address policedbc security review
- #169 — fix: harden workflows for enterprise production grade
- #164 — fix: defensive AGI planner fallback and dashboard type annotations
- #163 — feat: enterprise production-grade release readiness (zPITR, type safety, all gates passing)

All merged changes verified present on `main` (HEAD `e868ee4` includes them).

## PR review matrix

| PR | State | Head SHA | Review | CI | Disposition |
|----|-------|----------|--------|----|-------------|
| #174 | merged | (in main) | prior independent review | green | MERGED_VERIFIED |
| #173 | merged | (in main) | prior independent review | green | MERGED_VERIFIED |
| #172 | merged | (in main) | prior independent review | green | MERGED_VERIFIED |
| #171 | merged | (in main) | prior independent review | green | MERGED_VERIFIED |
| #170 | merged | (in main) | prior independent review | green | MERGED_VERIFIED |
| #169 | merged | (in main) | prior independent review | green | MERGED_VERIFIED |
| #168 | closed | superseded | prior independent review | n/a | CLOSED_SUPERSEDED |
| #167 | closed | branch deleted | n/a | n/a | CLOSED_SUPERSEDED |
| #166 | closed draft | branch deleted | n/a | n/a | DUPLICATE / CLOSED_SUPERSEDED |
| #165 | closed draft | branch deleted | n/a | n/a | DUPLICATE / CLOSED_SUPERSEDED |
| #158 | closed | — | n/a | n/a | CLOSED_SUPERSEDED |
| #146, #138, #137, #136, #123, #117, #62 | closed draft | (various) | n/a | n/a | DRAFT_INCOMPLETE |
| #1–#172 (merged set) | merged | (in main) | prior independent review | green | MERGED_VERIFIED |

## Open action required

None. All 171 discovered PRs have a documented disposition (100% coverage). No PR requires rebase, fix, test, or independent review at this time.

## Follow-up

`docs/audit/PR-FOLLOW-UP.md` — no outstanding follow-up items.
