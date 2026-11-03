# ZCoder Repository Audit and Engineering Report

**Audit date:** 2026-11-03
**Status:** `PARTIAL` — local quality checks pass; release qualification remains blocked by missing exact-candidate evidence and open Code Scanning alerts.

## 1. Executive Summary

The audit started on `main` at base commit `ecead2df575ba2dc3d9aec84c0ce7ce266833b25`, equal to the live `origin/main` observed during verification. The pre-existing untracked `docs/engineering/en.md` and `docs/engineering/th.md` were preserved, then committed on the audit branch. Draft PR #160 now carries the changes.

The audit corrected Python 3.12 configuration drift, moved uv development dependencies to the standardized dependency-group table, corrected the active Python release matrix, and added mypy to CI. `make check`, Black, lock validation, PostgreSQL integration tests, and the Upgrade-11 PostgreSQL evidence suite passed locally.

The repository is **not release-qualified**. Exact-head evidence import initially exposed two repository defects: the importer expected hardcoded version strings while runtime code reads installed package metadata, and imported evidence was not ignored so the gate rejected the resulting dirty worktree. Both fixes are implemented locally and require fresh exact-head hosted checks. PITR remains dependent on production WAL archive and restore-drill evidence, which is not configured in the repository. GitHub reports 185 open Code Scanning alerts, including 3 high and 10 medium security-severity alerts. Source inspection of the high and medium alerts reviewed in this audit did not confirm an exploitable vulnerability, but alert disposition remains open.

## 2. Repository Identity

- Repository: `cvsz/zcoder`
- Branch at audit start: `main`
- Base HEAD: `ecead2df575ba2dc3d9aec84c0ce7ce266833b25`
- Local `origin/main`: same SHA at audit start
- Remote: `github.com:cvsz/zcoder.git`
- `docs/engineering/en.md` and `docs/engineering/th.md` were preserved and committed on the audit branch.
- PR #160 is draft; no approval, merge, release, or deployment was performed.

## 3. Scope and Investigation Coverage

Inspected repository instructions, README and architecture/contribution/governance/security documents; Python package metadata and lockfile; CI, security, release, and packaging workflows; release-gate implementation and output; current GitHub PR, workflow, branch, Dependabot, and Code Scanning state; and representative API, session-path, logging, and network-discovery paths.

The source review used broad static searches and focused source-to-sink tracing for the reported high and medium Code Scanning alerts. It was not a line-by-line manual review of every file. No production system, external provider, or live model inference was exercised.

## 4. Architecture and Module Inventory

The canonical Python package is `src/zcoder/`, with API, config, core, domain, enterprise, infrastructure, interfaces, services, agent, and worker packages. The repository also contains the separate `webapp/` adapter/frontend, the TypeScript SDK, scripts, deployment/Helm assets, and unit/integration/e2e tests. Package metadata requires Python `>=3.12`; CI tests Python 3.12 and 3.13. SQLite supports local use and the dedicated ZCoder PostgreSQL service is PostgreSQL 16.15.

## 5. Findings

| ID | Severity | Finding | Status |
|---|---|---|---|
| F-01 | High | Release gate lacks evidence bound to the current release candidate. `VERSION_INTEGRITY`, `TEST_ACCOUNTING`, `PITR`, `SECURITY`, and `FINAL` are `UNKNOWN`. | Open; release blocked |
| F-02 | High | Three high-severity Code Scanning alerts remain open. Two path alerts point to `SessionStore` paths; inspection found strict session-ID validation, resolved-root containment, symlink rejection, and traversal rejection coverage. The third alert is a test assertion that checks exact membership in an allowed-origin set. These appear to be static-analysis false positives, but they remain open pending governed alert disposition. | Open; no exploit confirmed in reviewed paths |
| F-03 | Medium | Ten medium-severity Code Scanning alerts remain open: eight log-injection alerts in `services/coder.py`, one wildcard UDP beacon listener, and one stack-trace exposure alert. The inspected logger fields are JSON-encoded or omitted by the text formatter; the API error path returns a generic 500 body; the UDP listener is intentionally used for LAN beacon discovery. No exploit was confirmed in these reviewed paths. | Open; review and alert disposition still required |
| F-04 | Medium | Python support metadata was inconsistent: README advertised 3.10+, Ruff/Black targeted 3.10, while package and CI require 3.12+. | Fixed locally |
| F-05 | Medium | Hosted CI did not run the configured mypy check, although `make check` did. | Fixed locally by adding the mypy step to CI |
| F-06 | Low | uv warned that `tool.uv.dev-dependencies` is deprecated. | Fixed locally by migrating the same development dependency list to `[dependency-groups].dev`; `uv.lock` remains current |
| F-07 | Medium | The prior `Final-Report.md` and active release matrix contained stale or unsupported status/version claims. | Fixed locally by updating the report and the Python matrix row |
| F-08 | High | `scripts/import_release_evidence.py` searched for literal version assignments, but `main.VERSION` and `zcoder.__version__` use `importlib.metadata.version("zcoder")`. The importer therefore stopped before hosted evidence import with `version constants missing from canonical sources`. | Fixed locally using TOML metadata plus AST verification; exact-head hosted checks must rerun |
| F-09 | High | Imported evidence under `docs/evidence/` was untracked and not ignored. After successful import, `_working_tree_dirty()` rejected the same evidence and left all promoted gates `UNKNOWN`. | Fixed locally by ignoring only generated, exact-SHA `release-evidence-*.json` and `pitr-qualification-*.json` records; regression test added |

Code Scanning currently lists **185 open alerts**: 3 with high, 10 with medium, and 172 without a security-severity level. Dependabot currently lists **0 open alerts**. A successful CodeQL workflow run means analysis completed; it does not mean the open alert list is empty.

## 6. Changes Implemented

- `README.md`: Python badge now says `3.12+`.
- `pyproject.toml`: Ruff and Black target Python 3.12; the uv development dependency list uses `[dependency-groups].dev`.
- `scripts/install.py`: retained the pre-install Python version guard and documented its `UP036` exemption because the standalone installer runs before package metadata enforcement.
- `tests/unit/test_version_metadata.py`: corrected import ordering required after setting the Python 3.12 lint target.
- `.github/workflows/ci.yml`: added `mypy src/zcoder webapp --ignore-missing-imports`.
- `exec-planning.md`: active release matrix now states Python 3.12/3.13.
- `Final-Report.md`: replaced stale status with current audit evidence and limitations.
- `scripts/import_release_evidence.py`: verify project version metadata against the runtime modules' distribution-metadata lookup instead of requiring obsolete literal constants.
- `.gitignore`: exclude only generated candidate-bound release/PITR evidence so importing evidence does not make the checkout dirty or alter the SHA being validated.
- `tests/unit/test_release_evidence.py`: cover the real dynamic version source, reject mismatched exports, and ensure generated evidence paths are ignored.
- `docs/engineering/en.md` and `docs/engineering/th.md`: add the English and Thai repository governance guides.

No database schema, lockfile, API contract, credential, or production setting was changed. No files under the original untracked `docs/engineering/` directory were edited.

## 7. Tests and Verification Evidence

| Command | Result |
|---|---|
| `make check` | Exit 0 on Python 3.12.15: Ruff passed; mypy passed with no issues in 190 source files; Bandit reported no medium/high issues at `-ll`; pytest reported 1,841 passed, 28 skipped, 74.58% coverage. |
| `.venv/bin/python -m pytest -o addopts='' -q tests/unit/test_release_evidence.py tests/unit/test_release_gate_cli.py` | Exit 0: 29 passed, including regression coverage for runtime metadata version lookup and ignored generated evidence. |
| `.venv/bin/python -c 'from scripts.import_release_evidence import verify_version_integrity; print(verify_version_integrity())'` | Exit 0: `pyproject`, `main`, and `init` all resolve to `1.60.0`. |
| `.venv/bin/black --check .` | Exit 0: 487 files unchanged. |
| `uv lock --check` | Exit 0: 64 packages resolved; no lock changes required and no deprecation warning after migration. |
| `python scripts/local_postgres.py run -- .venv/bin/python -m pytest -o addopts='' -q tests/integration` | Exit 0: 78 passed against the dedicated ZCoder PostgreSQL database. |
| `python scripts/local_postgres.py run -- .venv/bin/python -m pytest -o addopts='' -q tests/e2e/upgrade_suites/test_upgrade11_evidence_suite.py` | Exit 0: 6 passed against the dedicated ZCoder PostgreSQL database. |
| `python scripts/release_gate.py --check` | Exit 1: not qualified; five evidence gates remain `UNKNOWN`. |
| `.venv/bin/pip-audit --locked .` | Exit 1: pip-audit reported no lockfiles found for this project path. Hosted Security Scan's Bandit/pip-audit jobs passed on the base commit; that hosted result is not a local audit of this working diff. |
| `actionlint .github/workflows/ci.yml` | Blocked: actionlint is not installed locally. The modified workflow YAML parses with PyYAML. Hosted actionlint passed on the base commit, before the local workflow edit. |
| `git diff --check` | Exit 0. |

The 28 skipped tests require a PostgreSQL test container/endpoint that the regular full-suite invocation could not reach. The two helper-based PostgreSQL runs above separately passed on the dedicated `zcoder_db` service. Other skipped e2e/live cases remain unverified by those two runs.

## 8. Security Assessment

- Hosted Security Scan, including Bandit/pip-audit and Gitleaks, passed on base commit `ecead2df575ba2dc3d9aec84c0ce7ce266833b25` on 2026-11-02.
- Hosted CodeQL completed successfully on the same base commit, but 185 open alerts remain and require triage.
- Local Bandit `-ll` found no medium/high issues in `src/zcoder`, `webapp`, or `scripts`.
- Current Dependabot open-alert count is zero.
- The API, session path, local model client logging, and UDP discovery alert paths reviewed here did not produce a confirmed exploit. This is limited source evidence, not a complete penetration test or a security-gate pass.
- PostgreSQL RLS/tenant isolation evidence is limited to the passed Upgrade-11 suite and existing repository evidence; production identity, backup, and recovery controls were not exercised.

## 9. CI, PR, Review, and Approval Status

Draft PR #160 targets `main` from `audit/engineering-baseline-2026-11-03`. On commit `4ed90120fa0ed327a4aea77d43a3350d802d3284`, every required hosted check passed, including Python 3.12/3.13 tests, Docker build, CodeQL, Bandit/pip-audit, Gitleaks, Dependency Review, Helm, SDK, actionlint, lock-check, and sync-locked. Evidence import then exposed F-09. This report records the pre-commit state of the F-09 fix; hosted checks must rerun on the next exact SHA before evidence import. Main branch metadata reports `protected: true`; branch-protection details were not available through the direct settings endpoint.

The latest observed hosted workflows for base SHA `ecead2df575ba2dc3d9aec84c0ce7ce266833b25` reported success for CI, Security Scan, CodeQL, Release Gate, Helm Lint, SDK & TypeScript Check, and Reproducibility Check. The `Release Gate` run on `main` ran its report-only step; the enforcement step was skipped because the ref was not a release tag. These results predate the local uncommitted changes in this report and do not qualify those changes.

PR #160 remains draft. No independent review or approval exists for the diff.

## 10. Deployment and Release Status

No release tag, artifact publication, container publication, deployment, or production migration was performed. Local release qualification remains `NOT QUALIFIED`. Do not use the green report-only main workflow as a production release approval.

## 11. Residual Risks and Known Limitations

- The F-09 fix and updated report are not yet committed or checked by hosted workflows on their exact SHA; current release qualification remains pending.
- PITR requires exact-candidate production WAL archive verification and a successful restore drill; no repository variable or operational record was available.
- Open Code Scanning alerts have not been dismissed, fixed, or accepted by the designated reviewer. The current source review does not change their GitHub state.
- Hosted checks passed on `4ed90120fa0ed327a4aea77d43a3350d802d3284`, but that SHA predates the evidence-ignore fix.
- actionlint was unavailable locally; PyYAML confirmed the edited workflow parses.
- 28 PostgreSQL-dependent cases were skipped in the regular full suite; only `tests/integration` and the Upgrade-11 evidence suite were run against the dedicated local database.
- No production backup restore, PITR, rollback, DR, performance qualification, or real model inference was performed.

## 12. Rollback and Recovery

The changes contain no schema or runtime-state migration. Revert only the relevant signed implementation commit if rollback is needed; retain the documentation commit unless it is independently in scope. `uv.lock` was not changed.

## 13. Next Actions

1. Commit and push the evidence-ignore fix, then rerun all required hosted checks on the resulting exact PR head and import their evidence.
2. Have an independent reviewer assess PR #160 and triage the open high/medium Code Scanning alerts; no author may approve their own work.
3. Provide verified production WAL archive and restore-drill metadata bound to the eventual exact release-candidate SHA.
4. Re-run `python scripts/release_gate.py --check` from a clean checkout after exact-head evidence is imported; complete production rollback, observability, and DR evidence before any production-readiness claim.
