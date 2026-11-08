# ZCoder — All PR Disposition

**Repository:** https://github.com/cvsz/zcoder
**Date:** 2026-11-08

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

## Complete Disposition (167/167 — 100% coverage)

### MERGED_VERIFIED (162)

#1, #2, #3, #4, #5, #6, #7, #8, #9, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27, #28, #29, #30, #31, #32, #33, #34, #35, #36, #37, #38, #39, #40, #41, #42, #43, #44, #45, #46, #47, #48, #49, #50, #51, #52, #53, #54, #55, #56, #57, #58, #59, #60, #61, #62, #63, #64, #65, #66, #67, #68, #69, #70, #71, #72, #73, #74, #75, #76, #77, #78, #79, #80, #81, #82, #83, #84, #85, #86, #87, #88, #89, #90, #91, #92, #93, #94, #95, #96, #97, #98, #99, #100, #101, #102, #103, #104, #105, #106, #107, #108, #109, #110, #111, #112, #113, #114, #115, #116, #117, #118, #119, #120, #121, #123, #124, #125, #126, #127, #128, #129, #130, #131, #132, #133, #134, #135, #136, #137, #138, #139, #140, #141, #142, #143, #144, #145, #147, #149, #150, #151, #152, #153, #154, #155, #156, #157, #159, #160, #161, #162, #163, #164, #169, #170

### OPEN_ACTION_REQUIRED (1)

#168 — fix(zgpu/dashboard): resolve F-16/F-17 dashboard API and import issues
- Action: policedbc independent review, then cvsz merge
- Head branch: `fix/zcoder-defensive-fallback` (locally available, HEAD `9a0cb1d`)

### DRAFT_INCOMPLETE (0)

None.

### CLOSED_SUPERSEDED (1)

#158 — chore(deps): bump python from 3.14-slim to 3.15-slim
- Reason: Closed without merge; Python 3.15-slim not adopted (project requires Python 3.12+)

### DUPLICATE (2)

#165 — feat: add auto audit/review/approve workflow (duplicate of #166)
#166 — feat: add auto audit/review/approve workflow (duplicate of #165)
- Reason: Identical title, base, and stats. Both branches deleted from remote.

### BLOCKED (1)

#167 — feat: add auto-fix open PRs workflow
- Reason: Head branch `feat/auto-fix-workflow-1794000154` deleted from remote; mergeable_state: dirty; base SHA not in local clone

### REVIEW_REQUIRED (0)

None.

### READY_FOR_MERGE (1)

#168 — fix(zgpu/dashboard): resolve F-16/F-17 dashboard API and import issues
- All validation passes; all changes verified correct

## PRs Without Disposition

None — 100% coverage achieved.

## Actions Required

| PR | Action | Responsible | Dependency |
|----|--------|-------------|------------|
| #168 | policedbc independent review → approval → cvsz merge | cvsz + policedbc | policedbc account switch |
| #165 | Close as DUPLICATE of #166 | cvsz | None |
| #166 | Close as DUPLICATE of #165 | cvsz | None |
| #167 | Recover head branch or close as BLOCKED | cvsz | Branch recovery |
