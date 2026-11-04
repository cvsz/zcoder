# ROADMAP-NEXT.md

**zcoder — Production Readiness, Release Engineering, and Completion Roadmap**  
Execution baseline: **2026-08-14** (hardening merged); active planning now in [`exec-planning.md`](exec-planning.md)  
Primary delivery branch: `main` (bounded slices via feature branches)  
Primary integration target: `main`  
Hardening pull request: **PR #6 — MERGED**

> This document is the forward-looking roadmap after the architecture/src-layout migration and post-migration consistency work. The historical `ROADMAP.md` remains an audit/history record and MUST NOT be rewritten to imply that current architecture existed in older releases.

---

## 1. Mission

Bring `zcoder` from the current hardening branch to a reproducible, security-reviewed, testable, packageable, containerized, observable, release-ready state where:

- the canonical implementation is `src/zcoder/...`;
- compatibility modules contain no duplicate business logic;
- permanent CI is green on supported Python versions;
- Ruff, Black, Bandit, pytest, docs, package, dependency, and Docker gates execute for real;
- no CI/security gate is weakened merely to obtain a green badge;
- `main` is validated after merge, not only the PR branch;
- release artifacts are built from a clean checkout of the final `main` commit;
- failures have recovery, rollback, and operational documentation;
- a release is marked Production PASS only after all Definition-of-Done gates below pass.

---

## 2. Current Baseline

### Completed

- [x] Architecture/src migration merged.
- [x] Post-migration consistency merged.
- [x] Canonical package established under `src/zcoder`.
- [x] Compatibility layer retained for legacy imports.
- [x] Repository-hardening migration applied on the hardening branch.
- [x] Temporary migration workflow executed successfully.

### Not complete yet

- [x] Permanent PR CI fully green.
- [x] Security findings resolved without lowering Bandit severity gates.
- [x] Test matrix green on Python 3.9–3.12.
- [x] Temporary migration tooling removed.
- [x] Hardening PR merged to `main`.
- [x] Post-merge `main` CI green.
- [ ] Clean-install package validation complete.
- [ ] Docker runtime validation complete.
- [ ] Dependency/security audit complete.
- [ ] Release-candidate validation complete.
- [ ] Production/release checklist signed off.

---

## 3. Non-Negotiable Engineering Rules

1. **Do not bypass required checks.**
2. **Do not lower Ruff/Bandit/pytest gates to hide failures.**
3. `# noqa` and `# nosec` are allowed only at narrow, documented validation boundaries.
4. `shell=True` is prohibited in permanent production code.
5. Intentional shell syntax must execute through an explicit, validated helper with subprocess `shell=False`.
6. Untrusted/generated Python may execute only through the restricted execution boundary.
7. Dynamic SQL identifiers must be allowlisted or replaced with static queries; values must be parameterized.
8. Network URL helpers must reject invalid schemes and missing hosts before opening a URL.
9. Temporary paths must come from the platform temp directory and sanitized components.
10. Production validation must run against the exact candidate commit that will be released.
11. Historical upgrade/prompts documentation must remain historical; repair corruption without inventing past implementation claims.
12. Do not add PyPI/container-registry publishing that depends on undefined secrets or permissions.

---

# Phase P0 — Close PR #6 Correctly

**Goal:** permanent PR validation is green without weakening quality or security policy.

## P0.1 Dependency contract

- [ ] Declare PostgreSQL test/runtime extra using `psycopg2-binary>=2.9.9,<3` where required.
- [ ] Synchronize `pyproject.toml` optional extras: `postgres`, `dev`, and `all`.
- [ ] Synchronize `requirements-dev.txt`.
- [ ] Verify editable install: `python -m pip install -e ".[dev]"`.
- [ ] Verify PostgreSQL extra: `python -m pip install -e ".[postgres]"`.
- [ ] Run `python -m pip check`.

**Exit criteria:** clean environment installs the declared test dependencies without CI-only ad-hoc packages.

## P0.2 Ruff and Black

- [ ] Run Ruff over permanent source/tests/scripts.
- [ ] Fix unused imports, undefined names, stale migration imports, import ordering, and style violations.
- [ ] Run Black check.
- [ ] Do not introduce repository-wide ignores to conceal migration errors.

**Exit criteria:** Ruff and Black checks pass from a clean checkout.

## P0.3 Security hardening

### Subprocess execution

- [ ] Non-shell commands use `run_command()` and explicit argv semantics.
- [ ] Commands intentionally requiring shell syntax use `run_shell_command()` with explicit shell executable and subprocess `shell=False`.
- [ ] Preserve pipe/redirection semantics only where explicitly required.
- [ ] Enforce timeout and output/error propagation.

### URL opening

- [x] Replace direct canonical `urllib.request.urlopen` calls with `safe_urlopen`.
- [x] Accept only HTTP/HTTPS.
- [x] Require hostname.
- [x] Keep any `# nosec B310` only on the validated primitive inside the helper.

### Generated/dynamic code

- [ ] Route generated execution through `restricted_exec.py`.
- [ ] Reject imports, global/nonlocal, while loops, unsafe builtins, and private attributes.
- [ ] Add negative tests for malicious payloads.

### Temp paths

- [x] Remove hard-coded `/tmp/...` paths.
- [x] Use `tempfile.gettempdir()` plus sanitized path components.
- [x] Add traversal tests.

### SQL

- [ ] Replace dynamic table-name queries with static allowlisted query maps where practical.
- [ ] Parameterize query values.
- [ ] Do not suppress B608 instead of fixing query construction.

**Exit criteria:** `bandit -r src/zcoder -ll` passes with only narrowly documented validated-boundary suppressions.

## P0.4 Test matrix

- [ ] Python 3.9.
- [ ] Python 3.10.
- [ ] Python 3.11.
- [ ] Python 3.12.
- [ ] unit tests.
- [ ] integration tests that are runnable in CI.
- [ ] E2E smoke paths.
- [ ] compatibility import tests.
- [ ] security regression tests.

**Exit criteria:** every supported Python job is green on the same PR head SHA.

## P0.5 Packaging and container gates

- [ ] Build wheel and sdist.
- [ ] Install built wheel in a clean environment.
- [ ] `python -m zcoder.main --health-check` passes from installed artifact.
- [ ] `zcoder --help` resolves correctly.
- [ ] Docker image builds.
- [ ] Container health check succeeds.

## P0.6 Remove migration scaffolding

After all permanent generated changes are committed and verified, remove:

- [x] `.github/workflows/apply-repository-hardening.yml`
- [x] `scripts/apply_repository_hardening.py`
- [x] `scripts/run_repository_hardening.py`

Then rerun all permanent checks on the new PR head SHA. — DONE; permanent workflows only.

**P0 release gate:** PR #6 has no required failing/pending checks and no temporary migration machinery remains.

---

# Phase P1 — Merge and Validate `main`

**Goal:** prove that the integration branch is healthy after the hardening merge.

- [ ] Confirm PR diff contains only intended permanent changes.
- [ ] Confirm review conversations are resolved.
- [ ] Merge PR #6 through normal branch protection.
- [ ] Record merge commit SHA.
- [ ] Wait for all `main` workflows on that exact SHA.
- [ ] Verify CI matrix, docs, package, Docker, and other required checks on `main`.
- [ ] If `main` fails, fix through a new branch/PR; do not force-push or bypass protection.

**Exit criteria:** exact `main` merge SHA is green.

---

# Phase P2 — Production-Grade Architecture and Runtime

## P2.1 Architecture boundaries

- [ ] Add architecture tests for forbidden dependency directions.
- [ ] Domain must not import infrastructure.
- [ ] Core must not depend on concrete adapters.
- [ ] Services orchestrate use cases; interfaces/infrastructure remain adapters.
- [ ] Detect circular imports.
- [ ] Remove duplicate business logic from compatibility modules.
- [ ] Define legacy import deprecation policy.

## P2.2 Database readiness

- [ ] PostgreSQL adapter contract documented.
- [ ] connection pooling.
- [ ] explicit transaction boundaries.
- [ ] migration framework/schema bootstrap.
- [ ] health/readiness checks.
- [ ] retry and timeout policy.
- [ ] rollback behavior.
- [ ] integration fixtures.
- [ ] backup/restore runbook.

## P2.3 Reliability

- [ ] standardized timeouts.
- [ ] bounded retries with jitter where safe.
- [ ] cancellation propagation.
- [ ] idempotency for mutating job operations.
- [ ] graceful shutdown.
- [ ] subprocess cleanup.
- [ ] resource cleanup.
- [ ] bounded concurrency/backpressure.
- [ ] provider/API rate-limit handling.

## P2.4 Observability

- [ ] structured logs.
- [ ] correlation/request/job/execution IDs.
- [ ] secret redaction.
- [ ] metrics for execution count, failures, latency, timeouts, provider failures.
- [ ] tracing hooks.
- [ ] health endpoint/command.
- [ ] readiness endpoint/command.
- [ ] diagnostics command.

## P2.5 API/runtime security

- [ ] authentication boundary.
- [ ] authorization/tool-grant boundary.
- [ ] input validation.
- [ ] payload/output limits.
- [ ] command working-directory restrictions.
- [ ] environment-variable allowlist for executed tools.
- [ ] output-size limits.
- [ ] audit trail for tool execution.
- [ ] security headers and CORS policy for web/API surfaces.

**P2 exit criteria:** production runtime invariants are encoded in code/tests, not only documentation.

---

# Phase P3 — CI/CD, Governance, and Supply Chain

## P3.1 Permanent workflows

- [ ] `ci.yml`: supported Python matrix, Ruff, Black, pytest, Bandit, import smoke, Docker.
- [ ] `docs.yml`: required docs, non-empty files, active local links.
- [ ] `package.yml`: wheel/sdist build, install, `pip check`, health check, artifact upload.
- [ ] `dependency-audit.yml`: scheduled/manual `pip-audit`.
- [ ] CodeQL if repository/security settings permit.
- [ ] dependency review where available.
- [ ] minimal workflow permissions.
- [ ] concurrency controls.
- [ ] workflow timeouts.
- [ ] supported major versions of official actions.

## P3.2 Repository governance

- [ ] CODEOWNERS.
- [ ] PR template.
- [ ] bug report template.
- [ ] feature request template.
- [ ] issue-template config.
- [ ] Dependabot configuration.
- [ ] Code of Conduct.
- [ ] Governance policy.
- [ ] Support policy.
- [ ] Security policy.
- [ ] contribution policy.
- [ ] branch-protection recommendations documented.

## P3.3 Supply-chain controls

- [ ] dependency audit.
- [ ] container vulnerability scan where runner tooling supports it.
- [ ] SBOM generation.
- [ ] artifact checksums.
- [ ] provenance/signing strategy documented before external publishing.
- [ ] no secret-bearing build artifacts.
- [ ] review package file list before release.

**P3 exit criteria:** repository governance and build supply chain are reproducible and auditable.

---

# Phase P4 — Test Depth and Operational Qualification

## P4.1 Unit/integration/E2E

- [ ] domain and core unit coverage.
- [ ] security-helper negative tests.
- [ ] PostgreSQL integration tests.
- [ ] Git/provider/API integration tests.
- [ ] CLI E2E.
- [ ] health/readiness E2E.
- [ ] tool execution lifecycle E2E.
- [ ] generated Excel/PowerPoint artifact tests.
- [ ] upgrade-suite tests.

## P4.2 Failure testing

- [ ] command timeout.
- [ ] command cancellation.
- [ ] invalid/malicious URL.
- [ ] DB unavailable.
- [ ] provider unavailable/rate-limited.
- [ ] malformed configuration.
- [ ] invalid generated code.
- [ ] permission denied.
- [ ] partial artifact failure.
- [ ] rollback after failed mutation.

## P4.3 Security regression suite

- [ ] command injection.
- [ ] shell metacharacters.
- [ ] path traversal.
- [ ] SSRF-style URL inputs.
- [ ] unsafe AST constructs.
- [ ] SQL identifier/value injection.
- [ ] secrets in logs.
- [ ] dangerous environment leakage.

## P4.4 Performance qualification

- [ ] CLI startup benchmark.
- [ ] large-repository benchmark.
- [ ] large artifact benchmark.
- [ ] memory profile.
- [ ] bounded subprocess concurrency test.
- [ ] API/load baseline where applicable.

**P4 exit criteria:** expected failure modes are tested and performance has a reproducible baseline.

---

# Phase P5 — Release Candidate and Production Release

## P5.1 Release metadata

- [ ] validate package name/version/description/license/classifiers/URLs.
- [ ] define SemVer release version.
- [ ] prepare release notes from CHANGELOG.
- [ ] create release checklist tied to exact commit SHA.

## P5.2 Clean release-candidate validation

From a fresh checkout of candidate `main`:

- [ ] create fresh virtual environment.
- [ ] install development dependencies from declared metadata.
- [ ] run full tests.
- [ ] run Ruff/Black/Bandit.
- [ ] run dependency audit.
- [ ] build wheel/sdist.
- [ ] install built wheel in another clean environment.
- [ ] run CLI/import/health smoke tests.
- [ ] build container.
- [ ] run container health check.
- [ ] inspect wheel/sdist contents.
- [ ] generate SBOM/checksums if configured.
- [ ] validate upgrade and rollback procedures.

## P5.3 Release

Only after P5.2 passes:

- [ ] tag release candidate or stable version according to release policy.
- [ ] create GitHub Release with validated artifacts when desired.
- [ ] publish externally only after repository secrets, permissions, ownership, provenance, and rollback policy are explicitly configured.

**P5 exit criteria:** release artifacts are derived from the exact validated commit and all release evidence is retained.

---

# 4. Definition of Done — Production PASS

`zcoder` may be marked **COMPLETE / PRODUCTION READY** only when every required gate is true:

| Gate | Required |
|---|---:|
| Architecture/src migration merged | ✅ |
| Post-migration consistency merged | ✅ |
| Repository hardening permanent changes committed | ✅ |
| Temporary migration tooling removed | ✅ |
| Ruff | ✅ |
| Black | ✅ |
| Bandit `-ll` | ✅ |
| pytest Python 3.9–3.12 | ✅ |
| Docs validation | ✅ |
| Package build + install | ✅ |
| `pip check` | ✅ |
| Docker build + health | ✅ |
| Dependency audit | ✅ |
| PR #6 required checks green | ✅ |
| Hardening merged to `main` | ✅ |
| Exact `main` merge SHA green | ✅ |
| Clean checkout validation | ✅ |
| Security regression suite | ✅ |
| E2E qualification | ✅ |
| Release artifacts inspected | ✅ |
| Release/rollback documentation validated | ✅ |

No item may be marked green from expectation alone; it must be backed by a real local/CI execution or repository state.

---

# 5. Recommended Execution Order

```text
PR #6 hardening branch
    |
    +-- dependency contract
    +-- Ruff / Black
    +-- Bandit / security fixes
    +-- pytest 3.9-3.12
    +-- docs + package + Docker
    +-- remove temporary migration tooling
    |
    v
rerun permanent PR checks on one SHA
    |
    v
all required checks GREEN
    |
    v
merge through branch protection
    |
    v
validate exact main merge SHA
    |
    v
architecture/runtime/reliability qualification
    |
    v
supply-chain + governance qualification
    |
    v
E2E / security / performance qualification
    |
    v
clean release-candidate build
    |
    v
PRODUCTION PASS / stable release
```

---

# 6. Tracking Convention

Use task IDs from `exec-planning.md` (canonical, root) in commits/PR comments when useful. Keep evidence for each gate as one of:

- GitHub Actions run URL/ID;
- test/report artifact;
- commit SHA;
- PR review/merge state;
- release artifact/checksum;
- documented manual qualification result where automation is impossible.

A task is not complete when code is merely written. It is complete when its acceptance criteria execute successfully against the intended commit.
