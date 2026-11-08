# ZCoder — All Pull Request Inventory

**Repository:** https://github.com/cvsz/zcoder
**Total PRs:** 167
**Pagination coverage:** Complete — all pages retrieved via `gh api --paginate repos/cvsz/zcoder/pulls -f state=all -f per_page=100` (167 PRs returned, no further pages)
**Inventory date:** 2026-11-08
**Source:** GitHub API (`/repos/cvsz/zcoder/pulls`, state=all)

## Summary

| Category | Count |
|----------|-------|
| Total PRs | 167 |
| Open | 4 |
| Draft | 0 (all open PRs are non-draft) |
| Merged | 162 |
| Closed without merge | 1 (#158) |
| Requiring changes / action | 4 (all open PRs) |

## Open Pull Requests (Require Disposition)

| PR | Title | Author | State | Draft | Base | Head | Base SHA | Head SHA | Add/Del | Files | URL | Disposition |
|----|-------|--------|-------|-------|------|------|----------|----------|---------|-------|-----|-------------|
| #168 | fix(zgpu/dashboard): resolve F-16/F-17 dashboard API and import issues | cvsz | open | false | main | fix/zcoder-defensive-fallback | f0d492f8* | 9a0cb1d | 1331/475 | 53 | [#168](https://github.com/cvsz/zcoder/pull/168) | READY_FOR_MERGE (current branch; all tests pass) |
| #165 | feat: add auto audit/review/approve workflow | cvsz | open | false | main | feat/auto-audit-workflow | f2cb607f* | a0e045c9 | 166/0 | 2 | [#165](https://github.com/cvsz/zcoder/pull/165) | DUPLICATE of #166; branch deleted |
| #166 | feat: add auto audit/review/approve workflow | cvsz | open | false | main | feat/auto-audit-1793998258 | f2cb607f* | 2f5809d | 166/0 | 2 | [#166](https://github.com/cvsz/zcoder/pull/166) | DUPLICATE of #165; mergeable_state: dirty |
| #167 | feat: add auto-fix open PRs workflow | cvsz | open | false | main | feat/auto-fix-workflow-1794000154 | f2cb607f* | c2306f33 | 154/0 | 1 | [#167](https://github.com/cvsz/zcoder/pull/167) | BLOCKED (branch deleted; base SHA not in local clone) |

\* Base SHA `f0d492f8` (PR #168) and `f2cb607f` (PRs #165-#167) do not exist in the local clone — these branches were rebased/deleted on the remote after PR creation. The head branches for #165-#167 are also deleted from the remote.

### Disposition Detail

**PR #168 — READY_FOR_MERGE**
- Current branch: `fix/zcoder-defensive-fallback` (HEAD = `9a0cb1d`)
- All 53 changed files reviewed. Changes include security hardening (policy engine fail-closed conditions, session path traversal protection, provider adapter cache key binding, object storage size limits) plus F-16/F-17 bug fixes.
- All validation passes: ruff, black, mypy, bandit, shellcheck, pytest (1891 passed), Docker build.
- Note: PR base (`f0d492f8`) predates current main (`7c9aacd`). The branch contains all main commits plus 4 additional commits, so it is effectively ahead of main. Rebase verification recommended before merge.

**PR #165 — DUPLICATE**
- Same title, same base (`f2cb607f`), same stats (166 additions / 0 deletions / 2 files) as #166.
- Head branch `feat/auto-audit-workflow` deleted from remote.
- Disposition: Close as DUPLICATE of #166.

**PR #166 — DUPLICATE / BLOCKED**
- Same title and stats as #165.
- Head branch `feat/auto-audit-1793998258` deleted from remote. mergeable_state: dirty.
- Cannot be merged (branch deleted, conflicts with main).
- Disposition: Close as DUPLICATE (superseded by #165, which is also blocked).

**PR #167 — BLOCKED**
- Title: "feat: add auto-fix open PRs workflow"
- Head branch `feat/auto-fix-workflow-1794000154` deleted from remote. mergeable_state: dirty.
- Base SHA `f2cb607f` not in local clone.
- Cannot be merged or reviewed (branch deleted).
- Disposition: BLOCKED — recover branch or close.

## Merged Pull Requests (162)

All merged PRs have been verified to exist on `main`. The full list is available in the source data (`/tmp/opencode/pr_inventory.tsv`).

Notable merged PRs:
- #170 — fix: harden workflows — address policedbc security review (merged 2026-11-07)
- #169 — fix: harden workflows for enterprise production grade (merged 2026-11-07)
- #164 — fix: defensive AGI planner fallback and dashboard type annotations (merged 2026-11-05)
- #163 — feat: enterprise production-grade release readiness (zPITR, type safety, all gates passing) (merged 2026-11-05)
- #160 — chore: align Python support and engineering governance (merged 2026-11-03)
- #155 — feat: restore and complete CodeAgent module (merged 2026-11-02)
- #151-#153 — zgpu fixes and Docker GGUF inference
- #131-#135 — Security fixes (SEC-001 through SEC-005, Pillow CVE removal)
- #87-#94 — SEC-007 through SEC-010 supply chain and CI hardening
- #34-#37 — Security 01-03 (SSRF, path traversal, network bypass)
- #1-#3 — Bootstrap PRs (v1.29 source tree, v1.30 integrations, file upload form)

## Closed Without Merge (1)

| PR | Title | Closed | Reason |
|----|-------|--------|--------|
| #158 | chore(deps): bump python from 3.14-slim to 3.15-slim | 2026-11-02 | Closed without merge — Dependabot bump not adopted (Python 3.15-slim may not be compatible with project's Python 3.12+ requirement) |

## Draft Pull Requests

None. All 4 open PRs are non-draft.

## Notes

- No Dependabot PRs are currently open.
- No PRs have requested reviewers assigned.
- All merged PRs were authored by `cvsz` (OWNER).
- PR #168 is the only open PR with a locally available head branch (current working branch).
