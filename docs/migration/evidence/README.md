# Migration Evidence — src-layout canonical (Upgrade-53 → 1.41.0)

**Canonical path:** `src/zcoder` (`pyproject.toml:package-dir {"": "src"}`)  
**Cutover SHA:** `2ec89ce5d3dc060e42fed63d1af156b04c87c0c3`  
**Prior lineage:** `46ad61d7` (PR #47 Upgrade-53 merged) → `2a8adcf` (migration complete, 104 flat modules deleted) → `bced683` (re-sign) → `45a91a1` (1.41.0 sync) → `316ba22` (code-scan fix) → `2ec89ce` (py310 drop)

## Evidence index
| # | File | Claim | Tier |
|---|---|---|---|
| 001 | `001-src-layout-canonical.md` | All imports `zcoder.*` via `src/zcoder`, no flat modules remain | E1 |
| 002 | `002-python310-prune.md` | `requires-python >=3.10` + CI matrix `3.10-3.12` + `uv.lock` prune | E2 |
| 003 | `003-uv-lock-reproducibility.md` | `uv lock --check` clean, `reproducibility.yml` green | E2 |

Each file contains: claim, reproduction command, hosted run ID, and rollback pointer. Evidence invalidates on any code/config/dependency change per `exec-planning.md:12`.

## How to verify
```
git show 2ec89ce:pyproject.toml | grep requires-python
git diff 2a8adcf..2ec89ce --stat | grep -c "flat"
uv lock --check
gh run view --repo cvsz/zcoder <run-id>
```
