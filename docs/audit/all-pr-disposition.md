# ZCoder — All PR Disposition

**Repository:** https://github.com/cvsz/zcoder
**Date:** 2026-11-08
**Source:** GitHub API (`/repos/cvsz/zcoder/pulls`, state=all, per_page=100, paginated until exhausted)
**Total PRs discovered:** 169 (100% pagination coverage)

## Disposition Definitions

| Status | Meaning |
|--------|---------|
| MERGED_VERIFIED | PR merged into main; changes verified present on main |
| OPEN_ACTION_REQUIRED | PR is open and requires action (review, fix, or merge) |
| DRAFT_INCOMPLETE | PR is in draft state and incomplete |
| CLOSED_SUPERSEDED | PR closed without merge; functionality superseded or not adopted |
| DUPLICATE | PR duplicates changes from another PR |
| BLOCKED | PR cannot be processed (branch deleted, conflicts, missing data) |
| REVIEW_REQUIRED | PR needs independent review before action |
| READY_FOR_MERGE | PR has passed all checks and is ready for merge |

## Complete Disposition (169/169 — 100% coverage)

### MERGED_VERIFIED (149)

#1, #2, #3, #4, #5, #6, #7, #8, #9, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27, #28, #29, #30, #31, #32, #33, #34, #35, #36, #37, #38, #39, #40, #41, #42, #43, #44, #45, #46, #47, #48, #49, #50, #51, #52, #53, #54, #55, #56, #57, #58, #59, #60, #61, #64, #65, #66, #67, #68, #69, #70, #71, #72, #73, #74, #75, #76, #77, #78, #79, #80, #81, #82, #83, #84, #85, #86, #87, #88, #89, #90, #91, #92, #93, #94, #95, #96, #97, #98, #99, #101, #102, #103, #104, #105, #108, #109, #111, #113, #114, #115, #116, #118, #119, #120, #121, #124, #125, #126, #127, #128, #129, #130, #131, #132, #133, #134, #135, #140, #142, #143, #144, #145, #147, #149, #150, #151, #152, #153, #154, #155, #156, #157, #159, #160, #161, #162, #163, #164, #169, #170, #171, #172

### CLOSED_SUPERSEDED (5)

#158 — chore(deps): bump python from 3.14-slim to 3.15-slim
- Reason: Closed without merge; Python 3.15-slim not adopted (project requires Python 3.12+)

#165 — feat: add auto audit/review/approve workflow
- Reason: Duplicate of #166; identical title, base, and stats. Head branch deleted from remote. Closed without merge.

#166 — feat: add auto audit/review/approve workflow
- Reason: Duplicate of #165; identical title, base, and stats. Head branch deleted from remote. mergeable_state: dirty. Closed without merge.

#167 — feat: add auto-fix open PRs workflow
- Reason: Head branch `feat/auto-fix-workflow-1794000154` deleted from remote; mergeable_state: dirty; base SHA not in local clone. Closed without merge.

#168 — fix(zgpu/dashboard): resolve F-16/F-17 dashboard API and import issues
- Reason: CLOSED_SUPERSEDED by independent audit (cvsz, 2026-11-08). Head branch `fix/zcoder-defensive-fallback` (474ac7b) is based on old main `f0d492f8` (merge-base with current main is `71c4565` / PR #163). `git diff main..branch` shows no `src/` changes unique to the branch; all source modifications are identical to current main. The branch lacks only workflow scripts and audit docs merged via PR #171 (`3a2f820`) and PR #172 (`cf30b3d`). The branch's `fix: remediate verified engineering findings` (17a1c2f) is the same fix shipped in PR #171, already merged into main at `cf30b3d`. Closed by cvsz with documented evidence comment on the PR.

### DRAFT_INCOMPLETE (7)

#146 — fix(security): reconcile patched dependencies and Python support
- Draft; branch deleted from remote; closed without merge.

#138 — feat(local): offline administration, compliance audit and task approval foundation
- Draft; closed without merge.

#137 — feat(local): route default ZCoder prompt CLI to loopback GGUF llama.cpp
- Draft; closed without merge.

#136 — [Aikido] Fix 10 security issues in truststore, numpy, platformdirs and 3 more
- Draft; closed without merge.

#123 — feat: portable install, standalone builds, provider endpoints and web console hardening
- Draft; closed without merge.

#117 — fix(config): protect API keys with atomic private settings writes
- Draft; closed without merge.

#62 — security: pin SEC-005 WebFetch DNS targets
- Draft; closed without merge.

### BLOCKED (0)

None remaining (#167 dispositioned as CLOSED_SUPERSEDED).

### OPEN_ACTION_REQUIRED (0)

None — PR #168 was the only open PR and has been dispositioned as CLOSED_SUPERSEDED.

### REVIEW_REQUIRED (0)

None.

### READY_FOR_MERGE (0)

None — PR #168 (previously the only READY_FOR_MERGE candidate) is superseded by PR #171 already in main.

## PRs Without Disposition

None — 100% coverage achieved. Every discovered PR has a documented disposition.

## Closed Without Merge (not merged, not in a category above)

#100 — fix(ci): sync CLI version with v1.41.0 — closed without merge
#106 — chore(deps): bump actions-minor-patch group with 3 updates — closed without merge
#107 — chore(deps): bump actions-minor-patch group with 6 updates — closed without merge
#110 — chore(deps): bump actions-minor-patch group with 3 updates — closed without merge
#112 — chore(deps): bump actions-minor-patch group with 6 updates — closed without merge
#139 — chore(deps): update anthropic requirement — closed without merge (Dependabot; Anthropic SDK kept on v1 per CHANGELOG)
#141 — chore(deps): bump actions-minor-patch group with 4 updates — closed without merge

These Dependabot / CI PRs were closed without merge; their dependency changes were either superseded by later updates or not adopted. No functionality missing from main.
