# ZCoder — All Pull Request Inventory

**Repository:** https://github.com/cvsz/zcoder
**Total PRs:** 169
**Pagination coverage:** Complete — all pages retrieved via `gh api --paginate repos/cvsz/zcoder/pulls -f state=all -f per_page=100` (169 PRs returned, no further pages)
**Inventory date:** 2026-11-08
**Source:** GitHub API (`/repos/cvsz/zcoder/pulls`, state=all)
**Independent audit:** cvsz (implementation) / policedbc (independent review)

## Summary

| Category | Count |
|----------|-------|
| Total PRs | 169 |
| Open | 0 (PR #168 closed as CLOSED_SUPERSEDED during independent audit) |
| Draft | 0 (all drafts closed without merge) |
| Merged | 149 |
| Closed without merge | 20 |
| Dispositioned | 169/169 (100% coverage) |

## Disposition by Status

| Status | Count | PRs |
|--------|-------|-----|
| MERGED_VERIFIED | 149 | #1-#172 merged set (see all-pr-disposition.md) |
| CLOSED_SUPERSEDED | 5 | #158, #165, #166, #167, #168 |
| DRAFT_INCOMPLETE | 7 | #62, #117, #123, #136, #137, #138, #146 |
| OPEN_ACTION_REQUIRED | 0 | — |
| DUPLICATE | 0 | subsumed under CLOSED_SUPERSEDED (#165, #166) |
| BLOCKED | 0 | subsumed under CLOSED_SUPERSEDED (#167) |
| REVIEW_REQUIRED | 0 | — |
| READY_FOR_MERGE | 0 | — |

## Closed Without Merge Detail (20)

Superseded / not adopted:
- #158 — chore(deps): bump python from 3.14-slim to 3.15-slim (Python 3.15-slim not adopted)
- #165 — feat: add auto audit/review/approve workflow (duplicate of #166; branch deleted)
- #166 — feat: add auto audit/review/approve workflow (duplicate of #165; branch deleted)
- #167 — feat: add auto-fix open PRs workflow (head branch deleted; base SHA not in clone)
- #168 — fix(zgpu/dashboard): resolve F-16/F-17 dashboard API and import issues (CLOSED_SUPERSEDED by independent audit — content already in main via PR #171)

Drafts closed without merge:
- #62 — security: pin SEC-005 WebFetch DNS targets
- #117 — fix(config): protect API keys with atomic private settings writes
- #123 — feat: portable install, standalone builds, provider endpoints and web console hardening
- #136 — [Aikido] Fix 10 security issues in truststore, numpy, platformdirs and 3 more
- #137 — feat(local): route default ZCoder prompt CLI to loopback GGUF llama.cpp
- #138 — feat(local): offline administration, compliance audit and task approval foundation
- #146 — fix(security): reconcile patched dependencies and Python support

Dependabot / CI PRs closed without merge (no functionality missing from main):
- #100 — fix(ci): sync CLI version with v1.41.0
- #106 — chore(deps): bump actions-minor-patch group with 3 updates
- #107 — chore(deps): bump actions-minor-patch group with 6 updates
- #110 — chore(deps): bump actions-minor-patch group with 3 updates
- #112 — chore(deps): bump actions-minor-patch group with 6 updates
- #139 — chore(deps): update anthropic requirement (Anthropic SDK kept on v1 per CHANGELOG)
- #141 — chore(deps): bump actions-minor-patch group with 4 updates

## Merged Pull Requests (149)

All merged PRs verified present on `main`. Notable recent merges:
- #172 — docs: update audit documentation for merged PR #171 (#172)
- #171 — fix: remediate verified engineering findings and add audit documentation (#171)
- #170 — fix: harden workflows — address policedbc security review
- #169 — fix: harden workflows for enterprise production grade
- #164 — fix: defensive AGI planner fallback and dashboard type annotations
- #163 — feat: enterprise production-grade release readiness (zPITR, type safety, all gates passing)

The full per-PR list is in `docs/audit/all-pr-disposition.md`.

## Notes

- No open PRs remain after the independent audit.
- All 169 PRs have a documented disposition (100% coverage).
- PR #168 was the only open PR at audit start; closed as CLOSED_SUPERSEDED because its head branch `fix/zcoder-defensive-fallback` introduces no `src/` changes beyond current `main` (its remediated-findings content shipped in PR #171, commit `3a2f820`).
