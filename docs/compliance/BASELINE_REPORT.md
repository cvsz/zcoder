# SUPER ULTRA AI ORC — ZCODER BASELINE REPORT

**Repository:** https://github.com/cvsz/zcoder
**Owner:** cvsz
**Organization:** ZEAZDEV COMPANY LIMITED
**Default Branch:** main
**Baseline Version:** 1.60.0
**Current Commit:** fffcf08 feat(makefile): add opencode-bg and opencode-free-bg targets
**Baseline Date:** 2026-11-04
**Report ID:** baseline-20261104-fffcf08

---

## 1. REPOSITORY STATE

- **Branch:** feat/makefile-opencode-prompt (checked out)
- **Remote:** origin (git@github.com:cvsz/zcoder.git)
- **Upstream branches:** 38 branches tracked
- **Local modifications:** 13 files modified, 38 untracked files/directories
- **Baseline version:** 1.60.0 (consistent across pyproject.toml, main branch, init)

---

## 2. GIT STATE

- **Current branch:** feat/makefile-opencode-prompt
- **Branch ahead/behind:** Branch is up to date with origin/feat/makefile-opencode-prompt
- **Uncommitted changes:** 13 modified files (see CHANGES detailed below)
- **Untracked files:** 38 files/directories including skills/, docs/, .gemini/, .claude/, .opencode.pid, .worker.pid, .api.pid, AUSI_ARCHITECTURE.md, etc.

---

## 3. DEPENDENCIES

- **Python:** >=3.12 (runtime: 3.14.4)
- **Package manager:** uv (via setuptools-backend)
- **Key dependencies:** python-dotenv, Pillow, textual
- **Optional:** fastapi, uvicorn, starlette (web), pandas, openpyxl, pandas (excel), python-pptx (pptx)
- **Provider SDKs:** anthropic>=1.2.0,<2.0.0

---

## 4. CI/CD STATE

### GitHub Actions Workflows (9 files)

| Workflow | Trigger | Status |
|---|---|---|
| `ci.yml` | push to main, PR to main, tags v* | Lint, Ruff check, Black check, mypy |
| `release-gate.yml` | push to main, PR to main, workflow_dispatch | Production Release Gate Audit |
| `security-scan.yml` | push to main, PR to main, schedule (Mon 05:30), dispatch | Bandit + pip-audit |
| `dependency-review.yml` | pull_request | Dependency review |
| `helm-lint.yml` | pull_request | Helm lint |
| `pages.yml` | push to main, tags | Pages deploy |
| `publish-container.yml` | push to main, tags | Container publish |
| `release.yml` | push to main, tags | Release workflow |
| `sdk-check.yml` | pull_request | SDK compatibility check |

### CI Job Status (from evidence files)

- **Lint:** PASS (seen in evidence records)
- **Security (Bandit):** PASS (seen in evidence records)
- **test (3.12/3.13):** PASS (seen in evidence records for prior commits)
- **PITR:** UNKNOWN (no evidence bound to current commit)
- **FINAL:** UNKNOWN (no evidence bound to current commit)

---

## 5. RELEASE TAGS AND VERSIONS

- **Tags:** v1.41.1, v1.41.2, v1.41.5
- **Baseline version:** 1.60.0 (set in pyproject.toml)
- **Version sources:** pyproject.toml=1.60.0, main=1.60.0, init=1.60.0
- **Release evidence:** 4 evidence JSON files in docs/evidence/ bound to prior commits

---

## 6. OPEN PULL REQUESTS

(Not directly inspectable without GitHub API; would require checking GitHub)

---

## 7. MODIFIED FILES SUMMARY

13 files modified (unstaged):

| File | Change Type | Lines |
|---|---|---|
| `.github/workflows/ci.yml` | Modified | 12 |
| `Makefile` | Modified | 138 |
| `pytest-structural.txt` | Modified | 12 |
| `scripts/local_postgres.py` | Modified | 4 |
| `src/zcoder/services/backup_restore.py` | Modified | 2 |
| `tests/e2e/test_enterprise_suite.py` | Modified | 2 |
| `tests/e2e/test_fleet_e2e.py` | Modified | 4 |
| `tests/integration/test_postgres_multiprocess.py` | Modified | 4 |
| `tests/integration/test_postgres_store.py` | Modified | 4 |
| `.../integration/test_upgrade_fence_multiprocess.py` | Modified | 2 |
| `tests/unit/test_backup_restore.py` | Modified | 48 |
| `tests/unit/test_production_config.py` | Modified | 8 |
| `tests/unit/test_sec008_env_inheritance.py` | Modified | 16 |

---

## 8. EVIDENCE INVENTORY

### Existing Evidence Files (docs/evidence/)

| File | SHA | Version | Checks |
|---|---|---|---|
| release-evidence-4ed90120.json | 4ed90120 | 1.60.0 | lint, security, test (3.12), test (3.13) |
| release-evidence-7828a31d.json | 7828a31d | 1.60.0 | lint, security, test (3.12), test (3.13) |
| release-evidence-d7e17414.json | d7e17414 | 1.60.0 | lint, security, test (3.12), test (3.13) |
| release-evidence-f7de7412.json | f7de7412 | 1.60.0 | lint, security, test (3.12), test (3.13) |

### Evidence Status

- Evidence exists for prior commits but NOT for current commit (fffcf08)
- All evidence records have schema version 1
- Checks include: lint, security, test (3.12), test (3.13)

---

## 9. NON-NEGOTIABLE GOVERNANCE CHECKS

Per AGENTS.md and full-master-aee.md, the following must be verified before any modifications:

- [x] README.md inspected
- [x] AGENTS.md inspected
- [ ] CLAUDE.md — not found in root
- [ ] CODEX.md — not found in root
- [ ] GEMINI.md — not found in root
- [ ] ARCHITECTURE.md — not found in root
- [ ] SECURITY.md — not found in root
- [ ] pyproject.toml inspected (version 1.60.0)
- [ ] uv.lock — not found
- [ ] Makefile inspected (modified)
- [ ] CHANGELOG.md — not found in root
- [ ] docs/compliance/ — needs inspection
- [ ] docs/security/ — needs inspection
- [ ] docs/operations/ — needs inspection
- [ ] docs/upgrades/ — needs inspection
- [ ] .github/workflows/ inspected (9 files)
- [ ] tests/ — needs inspection
- [ ] scripts/ — needs inspection
- [ ] src/zcoder/ — needs inspection
- [ ] webapp/ — needs inspection

---

## 10. BASELINE FINDINGS

1. **Repository version** is correctly set to 1.60.0 across all metadata sources
2. **Evidence gap:** No release evidence bound to current commit (fffcf08) — this will cause ALL gates to show UNKNOWN until evidence is imported
3. **Modified files:** 13 files have unstaged changes, primarily Makefile, CI workflows, and test files
4. **Untracked files:** 38 files/directories suggest significant work in progress (skills, docs, etc.)
5. **CI workflows:** Generally well-configured but need evidence binding for release qualification
6. **Release gates:** 23 mandatory gates defined; current state has many UNKNOWN due to missing evidence

---

## NEXT STEPS — PHASE 1: ARCHITECTURE AUDIT

Proceed to map the entire source tree, identify duplicate modules, dead code, incomplete implementations, and dependency violations.