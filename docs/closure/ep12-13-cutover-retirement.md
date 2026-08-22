# EP12-13 — Cutover & Retirement Closure

**Status:** CLOSED  
**Date:** 2026-08-22  
**Cutover SHA:** `2ec89ce5d3dc060e42fed63d1af156b04c87c0c3` (`v1.41.0`)  
**Retired lineage:** flat transitional modules (104 files) + compatibility shim (Upgrade-53)  
**Evidence tier:** E3 (System) + `docs/compliance/RETENTION.md`

## Scope
Bounded cutover from transitional layout (flat modules + `zcoder.*` shim) to canonical `src/zcoder` and retirement of pre-migration artifacts after `46ad61d7` Upgrade-53 merge.

## Cutover checklist

### Pre-cutover (read-only rehearsal)
- [x] `ROADMAP-NEXT.md` synchronized — stale PR #6 / hardening branch references removed
- [x] `exec-planning.md:47` updated `CI supports Python 3.10, 3.11, 3.12` (drop 3.9)
- [x] `docs/migration/evidence/*` captured (see `docs/migration/evidence/README.md`)
- [x] `scripts/release-candidate.mjs --check --sha 2ec89ce` green
- [x] `scripts/post-release-smoke.mjs --target ghcr.io/cvsz/zcoder:1.41.0` green (dry-run)

### Cutover (single bounded PR `2ec89ce`)
- [x] `src-layout migration` complete: all imports `zcoder.*` via `src/zcoder` (`pyproject.toml:package-dir {"": "src"}`)
- [x] Delete 104 transitional flat modules + shim (verified `git diff --stat` between `2a8adcf` and `2ec89ce`)
- [x] Fix `service→infrastructure` dependency + static import cycle hidden before migration
- [x] `uv.lock` regenerated for `>=3.10` (prune `python_full_version < '3.10'` markers), `uvicorn 0.52.4`
- [x] `ruff --fix` + `black` for `py310` target + `B905 strict=False` in `embeddings.py:112,149,179`

### Post-cutover validation
- [x] `pip install -e .` + `pytest --cov` green on `3.10/3.11/3.12` (lint/security/CodeQL/Helm/SDK green)
- [x] `docker build -t zcoder:ci . && docker run --rm zcoder:ci --version` → `1.41.0`
- [x] `CODEOWNERS` + `PULL_REQUEST_TEMPLATE.md:15` updated (no 3.9)
- [x] `CHANGELOG.md` 1.41.0 entry, `README.md:6` badge `3.10+`

## Retirement

| Artifact | Retirement action | Evidence |
|---|---|---|
| Flat modules `src/*.py` (104) | `git rm` in `2a8adcf` | `git log --diff-filter=D --stat 46ad61d7..2a8adcf` |
| Compatibility shim `zcoder_shim.py` | deleted | same |
| Python 3.9 CI jobs | removed from `ci.yml:70` | `2ec89ce` diff |
| `requirements.txt` py39 pins | superseded by `>=3.10` | `pyproject.toml:10` |

Retention per `RETENTION.md`: retired artifacts remain in git history, not in `main` tree. Restore via `git show 2a8adcf^:path`.

## Rollback
- Rollback SHA: `45a91a1` (pre-cutover) — `git revert 2ec89ce` or `git checkout 45a91a1`
- Rollback invalidates `ep11` production execution evidence — re-run `release-candidate.mjs` per `exec-planning.md:12`

## Closure
Cutover and retirement are **closed** on `2ec89ce`. No open PRs remain. Next upgrade (Upgrade-54) is roadmap refresh + branch-protection hardening per initial `ROADMAP-NEXT.md` gap.
