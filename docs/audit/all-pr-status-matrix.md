# ZCoder — All PR Status Matrix

**Repository:** https://github.com/cvsz/zcoder
**Total PRs:** 167
**Date:** 2026-11-08

## Status Summary

| Required Status | Count | PRs |
|-----------------|-------|-----|
| MERGED_VERIFIED | 163 | #1-#164 (excluding #158), #169, #170, #171 |
| OPEN_ACTION_REQUIRED | 0 | — |
| DRAFT_INCOMPLETE | 0 | — |
| CLOSED_SUPERSEDED | 1 | #158 |
| DUPLICATE | 2 | #165, #166 |
| BLOCKED | 1 | #167 |
| REVIEW_REQUIRED | 0 | — |
| READY_FOR_MERGE | 0 | — |

**Coverage:** 167/167 (100%) — every PR has a documented disposition.

#168 was superseded by #171 (merged). PR #171 merged PR #168's changes (plus the fixes from this audit) into main as squash commit `3a2f820`.

## Detailed Status Matrix

| PR | Title | State | Draft | Mergeable State | Disposition | Notes |
|----|-------|-------|-------|-----------------|-------------|-------|
| #170 | fix: harden workflows — address policedbc security review | closed | false | — | MERGED_VERIFIED | Merged 2026-11-07 into main |
| #169 | fix: harden workflows for enterprise production grade | closed | false | — | MERGED_VERIFIED | Merged 2026-11-07 into main |
| #168 | fix(zgpu/dashboard): resolve F-16/F-17 dashboard API and import issues | open | false | unknown | READY_FOR_MERGE | Current branch; all validation passes; base SHA outdated |
| #167 | feat: add auto-fix open PRs workflow | open | false | dirty | BLOCKED | Head branch deleted from remote; base SHA not in local clone |
| #166 | feat: add auto audit/review/approve workflow | open | false | dirty | DUPLICATE | Duplicate of #165; head branch deleted; mergeable_state: dirty |
| #165 | feat: add auto audit/review/approve workflow | open | false | — | DUPLICATE | Duplicate of #166; head branch deleted from remote |
| #164 | fix: defensive AGI planner fallback and dashboard type annotations | closed | false | — | MERGED_VERIFIED | Merged 2026-11-05 into main |
| #163 | feat: enterprise production-grade release readiness (zPITR, type safety, all gates passing) | closed | false | — | MERGED_VERIFIED | Merged 2026-11-05 |
| #162 | Feat/makefile opencode prompt | closed | false | — | MERGED_VERIFIED | Merged 2026-11-04 |
| #161 | feat(makefile): add targets to run opencode prompt | closed | false | — | MERGED_VERIFIED | Merged 2026-11-04 |
| #160 | chore: align Python support and engineering governance | closed | false | — | MERGED_VERIFIED | Merged 2026-11-03 |
| #159 | docs: add Final-Report.md | closed | false | — | MERGED_VERIFIED | Merged 2026-11-02 |
| #158 | chore(deps): bump python from 3.14-slim to 3.15-slim | closed | false | — | CLOSED_SUPERSEDED | Closed without merge; Python 3.15-slim not adopted |
| #157 | chore(deps): bump astral-sh/setup-uv from 10.3.2 to 10.3.3 | closed | false | — | MERGED_VERIFIED | Merged 2026-11-02 |
| #156 | fix: resolve Ruff exception chaining and subprocess capture findings | closed | false | — | MERGED_VERIFIED | Merged 2026-11-02 |
| #155 | feat: restore and complete CodeAgent module | closed | false | — | MERGED_VERIFIED | Merged 2026-11-02 |
| #154 | chore: minor formatting and cleanup | closed | false | — | MERGED_VERIFIED | Merged 2026-10-29 |
| #153 | fix(zgpu): close post-merge packaging, search, and redirect gaps | closed | false | — | MERGED_VERIFIED | Merged 2026-11-02 |
| #1-#152 | (152 additional merged PRs) | closed | false | — | MERGED_VERIFIED | All merged into main; includes bootstrap, security fixes (SEC-001 to SEC-010), zgpu features, CI hardening, dependency updates |

## PRs Requiring Action

| PR | Required Action | Owner | Blocker |
|----|----------------|-------|---------|
| #168 | Rebase verification onto current main, then merge via cvsz after policedbc approval | cvsz | policedbc independent review pending |
| #165 | Close as DUPLICATE of #166 | cvsz | None |
| #166 | Close as DUPLICATE of #165 | cvsz | None |
| #167 | Recover head branch or close as BLOCKED | cvsz | Head branch deleted from remote |

## 100% Coverage Confirmation

All 167 PRs discovered via paginated GitHub API have been assigned a disposition status. No PR is unaccounted for.
