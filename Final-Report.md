# ZCoder Repository Audit and Engineering Report

## Current Verification Checkpoint — 2026-11-04

This checkpoint supersedes the mutable branch, PR, and release-gate status
below. The historical audit record is retained for traceability.

- Local branch: `audit/engineering-baseline-2026-11-03`; tracked `HEAD`:
  `92ffeaaac100786dbd3492fde684770fbe94c85e`.
- `origin` is `git@github.com:cvsz/zcoder.git`. The working tree is dirty:
  `docker-compose.yml` has two uncommitted `container_name` additions, and
  `docs/engineering/master-prompt-next.md` is untracked. Neither change is
  present in the tracked HEAD or covered by the hosted checks below.
- PR #160 is open and draft, targeting `main`, at the tracked HEAD SHA. GitHub
  reports `REVIEW_REQUIRED`; all 16 release-required check names are successful
  on that SHA. This does not qualify the uncommitted worktree.
- `python scripts/release_gate.py --check` returned exit code 1 and
  `NOT QUALIFIED`. `VERSION_INTEGRITY`, `TEST_ACCOUNTING`, `PITR`, `SECURITY`,
  and `FINAL` are `UNKNOWN`; the other reported criteria are `PASS`.
- Exact-SHA evidence import was not run: the checkout is dirty, and the
  importer rejects dirty trees. No evidence was fabricated or imported.
- `gh auth status` reports invalid credentials for the configured accounts.
  A direct branch-protection query returned HTTP 404, so current branch-rule
  details and authenticated account identity were not verified. No review,
  approval, push, merge, publication, or deployment was performed.
- The existing [DR rehearsal runbook](docs/operations/dr-rehearsal.md) already
  contains physical PITR steps and an evidence template. Production WAL archive
  ownership, retention/access policy, and an Operations-run isolated restore
  remain unverified; the production PITR gate therefore remains `UNKNOWN`.

To qualify a later candidate, first review and commit only the intended
repository changes, restore valid authorized GitHub authentication, re-query
rules and checks for the resulting exact SHA, import its hosted evidence, and
obtain Operations evidence for production PITR. Then rerun the release gate.

**Audit date:** 2026-11-03
**Status:** `PARTIAL` — local WAL-G configuration and persistent ZCoder-to-`zPostgreSQL` container connectivity are implemented and locally verified. NVIDIA route fallback is also verified against a live trial endpoint. Production PITR evidence and hosted checks for the current working-tree changes are still missing, so release qualification remains blocked.

## 1. Executive Summary

The audit started on `main` at base commit `ecead2df575ba2dc3d9aec84c0ce7ce266833b25`, equal to the live `origin/main` observed during verification. The pre-existing untracked `docs/engineering/en.md` and `docs/engineering/th.md` were preserved, then committed on the audit branch. Draft PR #160 now carries the changes.

The audit corrected Python 3.12 configuration drift, moved uv development dependencies to the standardized dependency-group table, corrected the active Python release matrix, and added mypy to CI. `make check`, Black, lock validation, PostgreSQL integration tests, and the Upgrade-11 PostgreSQL evidence suite passed locally.

The follow-up configures Compose to attach the loopback-only `llama-server` network namespace to `zPostgreSQL_network`, mount the dedicated PostgreSQL password file read-only, and construct the ZCoder `DATABASE_URL` only in container memory. A rebuilt image connected as `zcoder` to `zcoder_db` on PostgreSQL 16.15 using a read-only `SELECT`. The package version sources all resolve to `1.60.0`; stale CLI/router version labels were corrected. The current candidate still has no exact-head hosted evidence, and the production cluster has `archive_mode=off`.

The repository is **not release-qualified**. Exact-head evidence import exposed two repository defects: the importer expected hardcoded version strings while runtime code reads installed package metadata, and imported evidence was not ignored so the gate rejected the resulting dirty worktree. Both fixes are committed. At verified SHA `d7e1741497dc87faa316353dee4365866bbe05a0`, all 16 required hosted checks passed, evidence import succeeded, and `VERSION_INTEGRITY`, `TEST_ACCOUNTING`, `SECURITY`, and `FINAL` promoted to `PASS`; `PITR` is the only `UNKNOWN` gate. It requires an actual production WAL archive and restore drill, which is not configured in the repository. GitHub reports 185 open Code Scanning alerts, including 3 high and 10 medium security-severity alerts. Source inspection did not confirm an exploit in the reviewed paths, but alert disposition remains open.

Follow-up implementation on base SHA `7828a31dc30fda57c1fa5226723e689e46fb26c6` adds WAL-G-generated archive and restore commands for S3-compatible storage and GCS, and documents physical PITR recovery. `make check` passed (1,846 passed, 28 skipped). WAL-G v3.0.9 was installed into the running shared `zPostgreSQL` container and separately exercised in an isolated PostgreSQL 16 container against Cloudflare R2: a base backup and WAL segments were uploaded, WAL replay reached a UTC target, and the pre-target row existed while the post-target row did not. The drill used a temporary prefix under the existing shared `z-platform` bucket and deleted its test objects afterward. A follow-up bucket migration created `zr2` in APAC, copied all nine zero-byte object markers, and moved `r2.zeaz.dev` to `zr2`; the original bucket remains intact for rollback. The shared PostgreSQL cluster still reports `archive_mode=off`; it is managed by ZChat Compose, has a ZChat data volume, and is connected to multiple application networks. No shared-cluster configuration or restart was performed. This synthetic drill does not qualify production PITR. The dirty worktree's release gate remains `NOT QUALIFIED` with `VERSION_INTEGRITY`, `TEST_ACCOUNTING`, `PITR`, `SECURITY`, and `FINAL` as `UNKNOWN`.

At the user's direction, the Google Cloud project display name for project ID `work-512900` was changed from `work` to `zcoder`; the ID remains unchanged. Cloud Shell confirms the project is active. No GCS buckets are present/visible in that project, and the active identity cannot list Cloud SQL or Compute instances, so no production database was identified and no storage or database resources were created.

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

The source review used broad static searches and focused source-to-sink tracing for the reported high and medium Code Scanning alerts. It was not a line-by-line manual review of every file. No production system was exercised. A later, narrowly scoped NVIDIA provider verification is recorded below; it does not change the production or release qualification status.

## 4. Architecture and Module Inventory

The canonical Python package is `src/zcoder/`, with API, config, core, domain, enterprise, infrastructure, interfaces, services, agent, and worker packages. The repository also contains the separate `webapp/` adapter/frontend, the TypeScript SDK, scripts, deployment/Helm assets, and unit/integration/e2e tests. Package metadata requires Python `>=3.12`; CI tests Python 3.12 and 3.13. SQLite supports local use and the dedicated ZCoder PostgreSQL service is PostgreSQL 16.15.

## 5. Findings

| ID | Severity | Finding | Status |
|---|---|---|---|
| F-01 | High | Release gate lacked exact-candidate evidence. After the importer and ignore fixes, four evidence gates pass; production `PITR` remains `UNKNOWN`. | Partially resolved; release blocked on PITR |
| F-02 | High | Three high-severity Code Scanning alerts remain open. Two path alerts point to `SessionStore` paths; inspection found strict session-ID validation, resolved-root containment, symlink rejection, and traversal rejection coverage. The third alert is a test assertion that checks exact membership in an allowed-origin set. These appear to be static-analysis false positives, but they remain open pending governed alert disposition. | Open; no exploit confirmed in reviewed paths |
| F-03 | Medium | Ten medium-severity Code Scanning alerts remain open: eight log-injection alerts in `services/coder.py`, one wildcard UDP beacon listener, and one stack-trace exposure alert. The inspected logger fields are JSON-encoded or omitted by the text formatter; the API error path returns a generic 500 body; the UDP listener is intentionally used for LAN beacon discovery. No exploit was confirmed in these reviewed paths. | Open; review and alert disposition still required |
| F-04 | Medium | Python support metadata was inconsistent: README advertised 3.10+, Ruff/Black targeted 3.10, while package and CI require 3.12+. | Fixed locally |
| F-05 | Medium | Hosted CI did not run the configured mypy check, although `make check` did. | Fixed locally by adding the mypy step to CI |
| F-06 | Low | uv warned that `tool.uv.dev-dependencies` is deprecated. | Fixed locally by migrating the same development dependency list to `[dependency-groups].dev`; `uv.lock` remains current |
| F-07 | Medium | The prior `Final-Report.md` and active release matrix contained stale or unsupported status/version claims. | Fixed locally by updating the report and the Python matrix row |
| F-08 | High | `scripts/import_release_evidence.py` searched for literal version assignments, but `main.VERSION` and `zcoder.__version__` use `importlib.metadata.version("zcoder")`. The importer therefore stopped before hosted evidence import with `version constants missing from canonical sources`. | Fixed and verified on exact SHA `d7e1741` |
| F-09 | High | Imported evidence under `docs/evidence/` was untracked and not ignored. After successful import, `_working_tree_dirty()` rejected the same evidence and left all promoted gates `UNKNOWN`. | Fixed and verified on exact SHA `d7e1741`; generated files are ignored and evidence was imported successfully |
| F-10 | High | The WAL helper only generated local `cp` commands, while the logical `pg_restore` rehearsal did not test physical WAL replay. | WAL-G S3 command generation and a physical-recovery procedure are implemented locally; real storage and production restore remain unverified |
| F-11 | High | The original R2 bucket `z-platform` had custom domain `r2.zeaz.dev` enabled and active, making its objects publicly reachable. The hostname was moved to replacement bucket `zr2`; object sensitivity was not inventoried. | Cutover verified; destination ownership and SSL are active. Source bucket retained for rollback; review contents and keep PITR archives separate/private |
| F-12 | Medium | The ZCoder Compose service did not join the external `zPostgreSQL_network` or receive a credential source, so it defaulted to SQLite even though the dedicated database and password file existed. | Fixed locally with a read-only mounted secret and runtime DSN derivation; ephemeral container connectivity verified. Long-running Compose service not started. |
| F-13 | Low | Current CLI/router module headers still displayed `1.30.0` and `1.40.x`, while the package release is `1.60.0`. | Fixed locally. `verify_version_integrity()` reports `pyproject`, `main`, and package init all at `1.60.0`; exact-candidate gate promotion still needs clean-commit hosted evidence. |

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
- `src/zcoder/services/backup_restore.py`: add opt-in `backend="s3"` and `backend="gcs"` modes that generate WAL-G `wal-push`/`wal-fetch` commands without loading or exposing credentials; preserve the existing filesystem default.
- `tests/unit/test_backup_restore.py`: cover WAL-G command generation, binary-path quoting, and invalid backend/path handling.
- `docs/operations/dr-rehearsal.md`: distinguish logical `pg_restore` checks from physical PITR, document WAL-G/S3/GCS prerequisites, and describe isolated target-time recovery and evidence requirements.
- `src/zcoder/agent/orchestration/providers.py`, `router.py`, and `main.py`: add route-scoped NVIDIA provider configuration, numbered-key resolution, free-form OpenCode model ID normalization, and fallback through the configured model chain on transient, rate-limit, and model/request rejection errors. Local model defaults remain separate.
- `docker-compose.yml`, `.env.example`, and local ignored `.env`: configure NVIDIA credentials/model chain for the ZCoder container without copying or displaying credential values; local `.env` remains mode `0600` and ignored by Git.
- `tests/unit/test_router_provider_parity.py` and `README.md`: cover NVIDIA fallback/provider scoping and document configuration and hosted-data handling.
- `Dockerfile`, `docker-compose.yml`, `scripts/docker_entrypoint.py`, `tests/unit/test_docker_entrypoint.py`, and `docs/operations/deployment.md`: connect the ZCoder container to `zPostgreSQL_network`, mount the existing ZCoder password file as a read-only secret, construct the `zcoder_db` DSN in runtime memory, and document the host helper. No password or DSN was added to tracked files.
- `src/zcoder/main.py` and `src/zcoder/agent/orchestration/router.py`: update stale current module version labels to package version `1.60.0`.
- `Final-Report.md`: record the follow-up implementation and its validation limits.
- Google Cloud project metadata: change the display name of project ID `work-512900` from `work` to `zcoder` at the user's request; no project ID or infrastructure resources changed.

No database schema, lockfile, API contract, credential value, shared PostgreSQL service, or production database setting was changed. No files under the original untracked `docs/engineering/` directory were edited.

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
| `make check` on Python 3.12.15 after the current changes | Exit 0: Ruff, mypy, and Bandit passed; pytest reported 1,859 passed and 28 skipped in 83.86s. Skips are PostgreSQL live cases unavailable to the bare suite; the 78 integration tests and six Upgrade-11 tests passed separately through `scripts/local_postgres.py`. |
| `.venv/bin/python -m mypy scripts/docker_entrypoint.py --ignore-missing-imports` | Exit 0: no issues in the new container entrypoint module. |
| `.venv/bin/python -m pytest -q tests/unit/test_docker_entrypoint.py tests/unit/test_router_provider_parity.py tests/unit/test_backup_restore.py` | Exit 0: 92 passed, including PostgreSQL secret-file handling and NVIDIA fallback behavior. |
| `python scripts/release_gate.py --check` at initial investigation | Exit 1 on pre-fix SHA `9d25921df12c2d847ecbfc7bf95538cdf15e450a`: `VERSION_INTEGRITY`, `TEST_ACCOUNTING`, `PITR`, `SECURITY`, and `FINAL` were `UNKNOWN`. |
| `python scripts/import_release_evidence.py` | Exit 0: imported 16 successful hosted checks bound to `d7e1741497dc87faa316353dee4365866bbe05a0`; evidence file is git-ignored and the worktree remains clean. |
| `python scripts/release_gate.py --check` after import | Exit 1 on SHA `d7e1741497dc87faa316353dee4365866bbe05a0`: only `PITR` remains `UNKNOWN`; `VERSION_INTEGRITY`, `TEST_ACCOUNTING`, `SECURITY`, and `FINAL` are `PASS`. |
| `.venv/bin/pip-audit --locked .` | Exit 1: pip-audit reported no lockfiles found for this project path. Hosted Security Scan's Bandit/pip-audit jobs passed on the base commit; that hosted result is not a local audit of this working diff. |
| `actionlint .github/workflows/ci.yml` | Blocked: actionlint is not installed locally. The modified workflow YAML parses with PyYAML. Hosted actionlint passed on the base commit, before the local workflow edit. |
| `git diff --check` | Exit 0. |
| `.venv/bin/python -m pytest -o addopts='' -q tests/unit/test_backup_restore.py` | Exit 0: 41 passed, including WAL-G/S3 config coverage. |
| `.venv/bin/python -m ruff check src/zcoder/services/backup_restore.py tests/unit/test_backup_restore.py` | Exit 0. |
| `.venv/bin/python -m black --check src/zcoder/services/backup_restore.py tests/unit/test_backup_restore.py` | Exit 0: both files unchanged. |
| `.venv/bin/python -m mypy src/zcoder/services/backup_restore.py` | Exit 0: no issues in the changed module. |
| `make check` on Python 3.12.15 | Exit 0: Ruff, mypy, Bandit passed; pytest reported 1,846 passed and 28 skipped in 85.20s. The PostgreSQL-dependent cases were skipped because the test endpoint was unavailable to this invocation. |
| `python scripts/release_gate.py --check` on the dirty follow-up worktree | Exit 1: `VERSION_INTEGRITY`, `TEST_ACCOUNTING`, `PITR`, `SECURITY`, and `FINAL` are `UNKNOWN`; current changes have no exact-head hosted evidence and production PITR record. |
| `docker exec --user postgres zPostgreSQL /usr/local/bin/wal-g --version` | Exit 0: WAL-G `v3.0.9` runs under the `postgres` OS user. Installed into the current container filesystem; this is not persistent across container recreation. |
| `docker inspect --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' zPostgreSQL` | Exit 0: shared PostgreSQL container remained `running healthy`; no restart was performed. |
| `python scripts/local_postgres.py status` | Exit 0: dedicated `zcoder_db` is reachable on PostgreSQL 16.15. |
| `docker exec zPostgreSQL sh -lc 'psql -X -U "$POSTGRES_USER" -d postgres -Atc "SHOW archive_mode"'` | Exit 0: shared cluster `archive_mode=off`; no WAL is currently archived by this PostgreSQL cluster. |
| `python -m pytest -q tests/unit/test_router_provider_parity.py` | Exit 0: 42 passed, including route-only provider selection, NVIDIA numbered-key resolution, free-form model normalization, ordered fallback, and authentication failure behavior. |
| `python -m ruff check src/zcoder/agent/orchestration/providers.py src/zcoder/agent/orchestration/router.py src/zcoder/main.py tests/unit/test_router_provider_parity.py` | Exit 0: all checks passed. |
| `git diff --check` | Exit 0 after NVIDIA provider changes. |
| `docker compose config --quiet` plus sanitized service-environment inspection | Exit 0: Compose syntax valid; route provider resolved as NVIDIA, one existing key is forwarded, all seven model IDs are configured, and endpoint resolves to `https://integrate.api.nvidia.com/v1`. Secret value was not printed. |
| `docker compose build zcoder` | Exit 0: image `zcoder:latest` built from the modified Dockerfile using the locked runtime dependencies; package metadata reported `zcoder==1.60.0`. |
| Ephemeral `docker run` on `zPostgreSQL_network`, mounted local password file, executed `scripts/docker_entrypoint.py`, then connected with psycopg2 and ran `SELECT current_database(), current_user, version()` | Exit 0: `zcoder_db`, role `zcoder`, PostgreSQL 16.15. Password and DSN were not printed. The test container was removed automatically; no database data was changed. |
| `python scripts/local_postgres.py status` | Exit 0: `zcoder_db` ready for `zcoder` on PostgreSQL 16.15. |
| `python scripts/local_postgres.py run -- .venv/bin/python -m pytest -o addopts='' -q tests/integration` | Exit 0: 78 passed against the dedicated ZCoder PostgreSQL database. |
| `python scripts/local_postgres.py run -- .venv/bin/python -m pytest -o addopts='' -q tests/e2e/upgrade_suites/test_upgrade11_evidence_suite.py` | Exit 0: 6 passed against the dedicated ZCoder PostgreSQL database. |
| Authenticated `GET https://integrate.api.nvidia.com/v1/models` using an existing local NVIDIA key | HTTP 200. Six of seven requested text/chat catalog IDs were listed; `nvidia/nemotron-voicechat` was not listed by the chat API model catalog. |
| Minimal `POST https://integrate.api.nvidia.com/v1/chat/completions` using `nvidia/nemotron-3.5-lightning-30b-a3b` | HTTP 200; one choice returned non-empty text content. The prompt was a generic one-line smoke check; its output was not recorded. |
| `python scripts/release_gate.py --check` after NVIDIA routing changes | Exit 1: `VERSION_INTEGRITY`, `TEST_ACCOUNTING`, `PITR`, `SECURITY`, and `FINAL` remain `UNKNOWN`; no exact-head hosted evidence was imported and production PITR remains unverified. |
| One-off inline Python orchestration; container commands included `docker exec --user postgres <source> wal-g backup-push "$PGDATA"`, `su-exec postgres wal-g backup-fetch "$PGDATA" LATEST`, and recovery with `restore_command = 'wal-g wal-fetch %f %p'` | PASS: WAL-G `backup-push`/`backup-fetch` and R2 `wal-push`/`wal-fetch` worked; recovery to `2026-11-03 15:42:35.80926+00` promoted successfully. Restored `before-target` count=1 and `after-target` count=0. Source archiver reported 7 archived segments, 0 failures, last WAL `000000010000000000000007`. Temporary container/volume were removed; verified 0 objects remain under the drill namespace. The orchestration script was transient and not retained, so the run is not directly reproducible from this checkout. This is local synthetic evidence only. |
| Cloudflare R2 bucket inventory and S3-compatible `ListBuckets` using `.env` values | Exit 0 before migration: one visible bucket, `z-platform`; S3-compatible authentication succeeded. The bucket was not dedicated to ZCoder and had no Bucket Lock rules at inspection. No credentials were printed. |
| Cloudflare R2 replacement migration: create `zr2` in APAC/Standard, copy and compare object keys/sizes, move `r2.zeaz.dev` custom-domain binding | PASS with caveat: 9 zero-byte objects copied and key/size verification passed. `r2.zeaz.dev` is enabled on `zr2`; ownership and SSL are active. Original `z-platform` bucket and its objects were retained for rollback. |
| `gcloud cloud-shell ssh --authorize-session --command=true` | Exit 0: Cloud Shell connection and session authorization succeeded. |
| `gcloud config set project work-512900 --quiet` via Cloud Shell, followed by `gcloud config get-value project --quiet` | Exit 0: selected project ID verified. |
| `gcloud projects update work-512900 --name=zcoder --quiet`, followed by `gcloud projects describe work-512900 --format="value(name,lifecycleState)"` | Exit 0: display name verified as `zcoder`; lifecycle state `ACTIVE`; project ID unchanged. |
| `gcloud storage buckets list --format=json` | Exit 0 in project `work-512900`: no GCS buckets were visible. |
| `gcloud sql instances list --format=json`; `gcloud compute instances list --format=json` | Blocked: the Cloud Shell identity could not list these resource types. No production database target was verified. |

The 28 skipped tests require a PostgreSQL test container/endpoint that the regular full-suite invocation could not reach. The two helper-based PostgreSQL runs above separately passed on the dedicated `zcoder_db` service. Other skipped e2e/live cases remain unverified by those two runs.

## 8. Security Assessment

- Hosted Security Scan, including Bandit/pip-audit and Gitleaks, passed on base commit `ecead2df575ba2dc3d9aec84c0ce7ce266833b25` on 2026-11-02.
- Hosted CodeQL completed successfully on the same base commit, but 185 open alerts remain and require triage.
- Local Bandit `-ll` found no medium/high issues in `src/zcoder`, `webapp`, or `scripts`.
- Current Dependabot open-alert count is zero.
- NVIDIA routing is scoped to `--route` through `ZCODER_ROUTE_PROVIDER`; other CLI inference flows retain their existing provider behavior. The configured credential remains in ignored local `.env` and is forwarded only to the ZCoder service container.
- NVIDIA's hosted trial notice states that prompts and outputs may be recorded for service operation and improvement. The route must not receive confidential code or personal data unless applicable NVIDIA terms permit it. The API credential was validated without disclosure; this does not verify account quota, ongoing availability, or organizational data-processing approval.
- PostgreSQL credentials remain in `/home/cvsz/.config/zcoder/postgresql.password` (mode `0600`) and are passed to the container as a read-only file secret. The image build does not copy that file; the entrypoint validates its format and never prints the derived DSN. The ephemeral connection exercised no write or migration.
- The API, session path, local model client logging, and UDP discovery alert paths reviewed here did not produce a confirmed exploit. This is limited source evidence, not a complete penetration test or a security-gate pass.
- PostgreSQL RLS/tenant isolation evidence is limited to the passed Upgrade-11 suite and existing repository evidence; production identity, backup, and recovery controls were not exercised.

## 9. CI, PR, Review, and Approval Status

Draft PR #160 targets `main` from `audit/engineering-baseline-2026-11-03`. All required hosted checks passed on exact SHA `d7e1741497dc87faa316353dee4365866bbe05a0`, including Python 3.12/3.13 tests, Docker build, CodeQL, Bandit/pip-audit, Gitleaks, Dependency Review, Helm, SDK, actionlint, lock-check, and sync-locked. The importer recorded 16 checks for that SHA. Main branch metadata reports `protected: true`; branch-protection details were not available through the direct settings endpoint.

The latest observed hosted workflows for base SHA `ecead2df575ba2dc3d9aec84c0ce7ce266833b25` reported success for CI, Security Scan, CodeQL, Release Gate, Helm Lint, SDK & TypeScript Check, and Reproducibility Check. The `Release Gate` run on `main` ran its report-only step; the enforcement step was skipped because the ref was not a release tag. These results predate the local uncommitted changes in this report and do not qualify those changes.

PR #160 remains draft at head `7828a31dc30fda57c1fa5226723e689e46fb26c6`; its 18 hosted checks succeeded on that head, before the current uncommitted changes. Review is required. No independent review or approval exists for the current diff.

## 10. Deployment and Release Status

No release tag, artifact publication, container publication, deployment, or production migration was performed. Local release qualification remains `NOT QUALIFIED`. Do not use the green report-only main workflow as a production release approval.

NVIDIA configuration is present in `.env` and Compose; the rebuilt image and an ephemeral PostgreSQL connection test passed, but the long-running ZCoder Compose service was not started. Live provider smoke verification was performed directly against NVIDIA's trial endpoint. The `nemotron-voicechat` entry is a speech model and is not listed by the text chat catalog; it remains in the requested fallback list and may be rejected before the next candidate is tried.

## 11. Residual Risks and Known Limitations

- Updating this report changes HEAD and invalidates previously imported exact-SHA evidence; checks and evidence import must be repeated on the report commit before any release decision.
- PITR still requires exact-candidate production WAL archive verification and an Operations-run restore drill against the production archive. The local synthetic drill does not satisfy that gate.
- WAL-G is installed only in the current `zPostgreSQL` container filesystem; it is not declared in the service's managing Compose configuration and will not survive normal container recreation unless installed through its owner-managed image. The temporary drill image was removed after the test.
- Cloudflare R2 access was tested with the existing `.env` credentials. The 9 source objects in `z-platform` were zero-byte markers; copied object keys/sizes matched in `zr2`. The source bucket had no Bucket Lock Rules at inspection.
- `r2.zeaz.dev` was moved to `zr2` with custom-domain access enabled to preserve the prior public-domain behavior. Ownership and SSL are active. Object contents were not inventoried beyond key/size metadata; keep database backups out of this public bucket.
- The shared PostgreSQL container is managed by `/mnt/d/data/zchat/control-server/compose.yaml`, uses volume `zchat_postgres_data`, and is attached to multiple application networks. Its `archive_mode` is `off`. Changing cluster-wide archive settings or recreating it can affect other applications; no such change was made.
- No production database target or isolated production recovery host is verified. The ZWorkforce Supabase credentials were not reused; Supabase Storage documents no S3 versioning or Object Lock support.
- In selected project `work-512900` (display name `zcoder`), no GCS buckets were visible and Cloud SQL/Compute inventory was denied. No production DB target or isolated restore target is verified.
- Open Code Scanning alerts have not been dismissed, fixed, or accepted by the designated reviewer. The current source review does not change their GitHub state.
- Four release gates are verified `PASS` on SHA `d7e1741497dc87faa316353dee4365866bbe05a0`; PITR remains `UNKNOWN`.
- actionlint was unavailable locally; PyYAML confirmed the edited workflow parses.
- 28 PostgreSQL-dependent cases were skipped in the regular full suite; only `tests/integration` and the Upgrade-11 evidence suite were run against the dedicated local database.
- No production backup restore, PITR, rollback, DR, or performance qualification was performed. Read-only inventory across seven accessible GCP projects found Cloud SQL and Compute enumeration unavailable in each; GCS inventory calls timed out in this run. The local shared PostgreSQL cluster still reports `archive_mode=off`. The NVIDIA inference smoke check proves only that the selected key and one chat model worked at that moment; it does not prove all seven candidates or sustained availability.

## 12. Rollback and Recovery

The repository changes contain no database schema migration. The temporary PITR drill's containers, volume, image, and objects were removed. The WAL-G binary and `gcompat` package remain only in the current `zPostgreSQL` container writable layer; recreating that container from its owner-managed image removes them. The R2 migration is reversible while `z-platform` is retained: remove the domain from `zr2` and reattach it to `z-platform` using its existing zone ID, then verify domain/SSL status. The old bucket has not been deleted. Do not recreate the shared PostgreSQL container solely as rollback without coordinating with its ZChat service owner. If the project display-name change must be rolled back, run `gcloud projects update work-512900 --name=work` from the authorized Cloud Shell session. Revert only the relevant reviewed code changes if code rollback is needed; `uv.lock` was not changed.

## 13. Next Actions

1. Identify the production PostgreSQL host/instance and isolated recovery target; current Cloud Shell identity could not inventory Cloud SQL/Compute, and the local shared container is not established as production.
2. Provision an approved, dedicated Cloudflare R2 bucket/prefix with the required retention/deletion protection and a least-privilege credential for the database workload.
3. Inventory and repoint any direct S3 clients from `z-platform` to `zr2`; the source bucket remains intact for rollback and must not be deleted until clients are verified.
4. Coordinate with the owner of `/mnt/d/data/zchat/control-server/compose.yaml` before building a persistent WAL-G-enabled PostgreSQL image or changing cluster-wide archive settings; protect all databases on the shared cluster.
5. Configure the approved production primary to archive WAL and schedule physical base backups, then have Operations restore to an isolated target and file sanitized evidence against the exact release-candidate SHA.
5. Commit the reviewed implementation, then rerun exact-head hosted checks and import evidence; have an independent reviewer assess PR #160 and triage open high/medium Code Scanning alerts.
6. Re-run `python scripts/release_gate.py --check` from a clean checkout after exact-head evidence is imported; complete production rollback, observability, and DR evidence before any production-readiness claim.
