# Execution Planning — zcoder Production Completion

Status: **ACTIVE**  
Execution baseline: **2026-08-14**  
Repository: `cvsz/zcoder`  
Primary branch: `chore/complete-repository-hardening`  
Integration target: `main`  
Primary hardening PR: **#6**  
Companion roadmap: [`../ROADMAP-NEXT.md`](../ROADMAP-NEXT.md)

---

## 1. Purpose

This plan converts `ROADMAP-NEXT.md` into an executable sequence of work packages with explicit dependencies, code/document targets, validation commands, CI gates, acceptance criteria, rollback rules, and completion evidence.

The plan is intentionally strict:

- implementation is not completion;
- a passing temporary migration workflow is not production validation;
- no quality/security check may be weakened solely to become green;
- the exact release candidate commit must be the commit that passed validation;
- historical documents are preserved as historical evidence rather than rewritten as current architecture.

---

## 2. Delivery Strategy

### 2.1 Branch and PR policy

Use the existing hardening branch and PR until permanent hardening is green:

```text
chore/complete-repository-hardening
              |
              v
            PR #6
              |
              v
             main
```

Create a new follow-up branch only when:

1. PR #6 is already merged; or
2. branch protection/review policy requires a separate change; or
3. a post-merge `main` failure requires remediation.

Do not force-push `main`. Do not bypass required checks. Do not merge a red candidate and plan to repair it afterward.

### 2.2 Commit policy

Prefer bounded commits that correspond to one workstream, for example:

```text
fix(deps): declare postgres test dependency
fix(security): remove unsafe subprocess shell execution
fix(security): validate outbound URL opening
fix(security): restrict generated Python execution
fix(test): add security regression coverage
ci: finalize permanent validation workflows
docs: complete production-readiness documentation
chore: remove temporary hardening migration tooling
```

A commit may include tightly coupled test changes with the implementation it validates.

### 2.3 Evidence policy

Every completed gate must have one or more of:

- GitHub Actions run/job result;
- commit SHA;
- test report/artifact;
- package/container artifact;
- release checksum/SBOM;
- PR merge state;
- documented manual validation where CI automation is impossible.

---

# 3. Work Breakdown Structure

## WS-00 — Establish One Validation Baseline

**Priority:** P0  
**Blocks:** all subsequent work

### Tasks

- [ ] `WS00-T01` Record current PR #6 head SHA.
- [ ] `WS00-T02` Record permanent workflow run IDs for that SHA.
- [ ] `WS00-T03` Categorize every failure into dependency, lint/format, security, test, docs, package, or Docker.
- [ ] `WS00-T04` Confirm no failure is only from obsolete temporary migration files.
- [ ] `WS00-T05` Avoid mixing logs from different head SHAs while diagnosing a failure.

### Acceptance criteria

A single table can map each failing job to the exact PR head SHA and root-cause class.

### Evidence

- PR #6 metadata.
- workflow run IDs.
- job/log references.

---

## WS-01 — Dependency Contract and Clean Installation

**Priority:** P0  
**Depends on:** WS-00

### Targets

- `pyproject.toml`
- `requirements-dev.txt`
- package metadata/optional extras

### Tasks

- [ ] `WS01-T01` Add PostgreSQL dependency contract using `psycopg2-binary>=2.9.9,<3` where tests/runtime expect `psycopg2`.
- [ ] `WS01-T02` Ensure `postgres` optional extra exists.
- [ ] `WS01-T03` Ensure `dev` includes dependencies required by the CI test suite.
- [ ] `WS01-T04` Ensure `all` includes the intended union of optional runtime capabilities.
- [ ] `WS01-T05` Synchronize `requirements-dev.txt` with the declared development contract.
- [ ] `WS01-T06` Check for dependency conflicts.
- [ ] `WS01-T07` Verify clean editable installation.
- [ ] `WS01-T08` Verify optional PostgreSQL installation.

### Validation

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pip check
python -c "import zcoder"
python -c "import psycopg2"
```

Optional isolated test:

```bash
python -m venv .venv-postgres
. .venv-postgres/bin/activate
python -m pip install -e ".[postgres]"
python -c "import psycopg2; print(psycopg2.__version__)"
```

### Acceptance criteria

- test collection no longer fails because `psycopg2` is undeclared;
- fresh install contains only declared dependencies;
- `pip check` passes.

---

## WS-02 — Ruff and Black Closure

**Priority:** P0  
**Depends on:** WS-01

### Tasks

- [ ] `WS02-T01` Run Ruff against permanent source/tests/scripts.
- [ ] `WS02-T02` Fix undefined names.
- [ ] `WS02-T03` Remove stale/unused migration imports.
- [ ] `WS02-T04` Correct import ordering.
- [ ] `WS02-T05` Correct invalid/unused variables.
- [ ] `WS02-T06` Apply safe autofixes where behavior cannot change.
- [ ] `WS02-T07` Review every remaining manual lint suppression.
- [ ] `WS02-T08` Run Black check and format only intended files.

### Validation

```bash
ruff check src tests scripts
black --check src tests scripts
```

If repository configuration intentionally scopes these tools differently, CI configuration is the source of truth.

### Acceptance criteria

- Ruff passes.
- Black passes.
- no broad repository-level ignore was added merely to hide migration defects.

---

## WS-03 — Subprocess Security Boundary

**Priority:** P0 / Security  
**Depends on:** WS-00

### Targets

- `src/zcoder/core/safe_subprocess.py`
- `src/zcoder/claude/capabilities/code.py`
- `src/zcoder/claude/enterprise/settings.py`
- `src/zcoder/claude/enterprise/hooks_perms.py`
- `src/zcoder/claude/integrations/git.py`
- `src/zcoder/claude/orchestration/sessions.py`
- related tests

### Required design

`run_command()`:

- accepts argv or safely tokenized non-shell command input;
- invokes subprocess with `shell=False`;
- preserves timeout/capture/cwd/input semantics.

`run_shell_command()`:

- exists only for intentional shell syntax;
- invokes explicit shell executable using argv;
- still uses subprocess `shell=False`;
- preserves pipe/redirect semantics intentionally, not accidentally.

### Tasks

- [ ] `WS03-T01` Remove canonical `subprocess.run(..., shell=True, ...)` calls.
- [ ] `WS03-T02` Move non-shell Git/session operations to `run_command()`.
- [ ] `WS03-T03` Move Hook/Bash/status-line operations that require shell syntax to `run_shell_command()`.
- [ ] `WS03-T04` Preserve stdin, cwd, timeout, stdout/stderr behavior.
- [ ] `WS03-T05` Validate POSIX shell executable handling.
- [ ] `WS03-T06` Validate Windows `COMSPEC/cmd.exe` handling.
- [ ] `WS03-T07` Add command-injection/metacharacter regression tests.
- [ ] `WS03-T08` Add timeout/error propagation tests.

### Acceptance criteria

```bash
grep -R "shell=True" -n src/zcoder
```

returns no permanent production use.

Behavioral tests prove that intentional pipes/redirections still work while non-shell commands do not gain shell interpretation.

---

## WS-04 — Safe Network Boundary

**Priority:** P0 / Security  
**Depends on:** WS-00

### Target

`src/zcoder/core/safe_io.py`

### Tasks

- [ ] `WS04-T01` Centralize direct URL opening.
- [ ] `WS04-T02` Permit only `http` and `https` schemes.
- [ ] `WS04-T03` Require hostname.
- [ ] `WS04-T04` Reject file/custom/empty schemes.
- [ ] `WS04-T05` Replace canonical direct `urllib.request.urlopen` calls.
- [ ] `WS04-T06` Keep any Bandit suppression only on the validated primitive inside the helper.
- [ ] `WS04-T07` Add valid/invalid URL tests.
- [ ] `WS04-T08` Add SSRF-oriented input regression cases for malformed/local-style URL forms according to the project's threat model.

### Acceptance criteria

Direct network-open primitives are not scattered through canonical modules; the validation boundary is test-covered and Bandit-clean.

---

## WS-05 — Restricted Generated-Code Execution

**Priority:** P0 / Security  
**Depends on:** WS-00

### Target

`src/zcoder/core/restricted_exec.py`

### Tasks

- [ ] `WS05-T01` Parse generated code with AST before execution.
- [ ] `WS05-T02` Reject `Import` and `ImportFrom`.
- [ ] `WS05-T03` Reject `Global` and `Nonlocal`.
- [ ] `WS05-T04` Reject `While` if policy requires bounded execution.
- [ ] `WS05-T05` Reject unsafe calls: `eval`, `exec`, `open`, `compile`, `__import__`, `globals`, `locals`, dangerous attribute mutation/introspection helpers.
- [ ] `WS05-T06` Reject private attribute access according to policy.
- [ ] `WS05-T07` Route Excel/PowerPoint generated execution through the restricted boundary.
- [ ] `WS05-T08` Keep the single execution primitive documented and narrowly suppressed if required by Bandit.
- [ ] `WS05-T09` Add malicious-code negative tests.
- [ ] `WS05-T10` Add normal supported generated-artifact positive tests.

### Acceptance criteria

No canonical unvalidated direct `exec()` remains outside the restricted boundary.

---

## WS-06 — Secure Temp Paths and SQL Construction

**Priority:** P0 / Security  
**Depends on:** WS-00

### Targets

- `src/zcoder/core/temp_paths.py`
- modules using `/tmp/zcoder_*`
- deployment/database query construction

### Tasks

- [ ] `WS06-T01` Replace hard-coded `/tmp` locations with platform temp directory.
- [ ] `WS06-T02` Sanitize user/identifier-derived path components.
- [ ] `WS06-T03` Add path traversal tests.
- [ ] `WS06-T04` Replace dynamic SQL identifiers with static/allowlisted query selection.
- [ ] `WS06-T05` Parameterize SQL values.
- [ ] `WS06-T06` Remove any broad B608 workaround.

### Acceptance criteria

Bandit no longer reports the original temp-path/dynamic-SQL findings and traversal/injection tests pass.

---

## WS-07 — Permanent Security Gate

**Priority:** P0  
**Depends on:** WS-03, WS-04, WS-05, WS-06

### Validation

```bash
bandit -r src/zcoder -ll
```

### Tasks

- [ ] `WS07-T01` Review every Medium/High result.
- [ ] `WS07-T02` Fix real vulnerabilities at source.
- [ ] `WS07-T03` Document any remaining validated-boundary suppression inline.
- [ ] `WS07-T04` Ensure CI invokes the same or stricter command.

### Acceptance criteria

Permanent Bandit job passes with the intended `-ll` policy; severity is not downgraded to obtain green status.

---

## WS-08 — Test Matrix Closure

**Priority:** P0  
**Depends on:** WS-01 through WS-07 as applicable

### Matrix

| Python | Required |
|---|---:|
| 3.9 | yes |
| 3.10 | yes |
| 3.11 | yes |
| 3.12 | yes |

### Tasks

- [ ] `WS08-T01` Fix collection/import failures.
- [ ] `WS08-T02` Run unit suite.
- [ ] `WS08-T03` Run integration suite available to CI.
- [ ] `WS08-T04` Run E2E smoke suite.
- [ ] `WS08-T05` Test canonical imports.
- [ ] `WS08-T06` Test legacy compatibility imports.
- [ ] `WS08-T07` Add security regression tests for workstreams WS-03..06.
- [ ] `WS08-T08` Verify no Python-version-specific behavior breaks 3.9–3.12.

### Validation

```bash
pytest -q
```

Use the CI command/options as authoritative if markers or split suites are configured.

### Acceptance criteria

All supported Python jobs pass on the same PR head SHA.

---

## WS-09 — Canonical Architecture Validation

**Priority:** P1  
**Depends on:** P0 source stability

### Tasks

- [ ] `WS09-T01` Confirm `src/zcoder/...` is the only canonical implementation.
- [ ] `WS09-T02` Confirm top-level compatibility modules contain no independent business logic.
- [ ] `WS09-T03` Test legacy import behavior.
- [ ] `WS09-T04` Define compatibility deprecation policy.
- [ ] `WS09-T05` Add forbidden-import architecture tests.
- [ ] `WS09-T06` Ensure domain does not import infrastructure.
- [ ] `WS09-T07` Ensure core avoids concrete adapter dependencies.
- [ ] `WS09-T08` Check circular imports.

### Acceptance criteria

Architecture rules fail automatically when dependency direction regresses.

---

## WS-10 — CLI and Entrypoint Qualification

**Priority:** P1  
**Depends on:** WS-01, WS-08

### Required entrypoints

- `zcoder`
- `ai-coder`
- `python -m zcoder.main`
- health-check mode

### Tasks

- [ ] `WS10-T01` Test help output.
- [ ] `WS10-T02` Test health check.
- [ ] `WS10-T03` Test invalid argument behavior.
- [ ] `WS10-T04` Test installed wheel entrypoints, not only editable source.
- [ ] `WS10-T05` Verify canonical package-data loading.

### Acceptance criteria

All entrypoints work from a clean installed wheel.

---

## WS-11 — Permanent CI Workflow

**Priority:** P0/P1  
**Depends on:** WS-01..10

### Target

`.github/workflows/ci.yml`

### Required characteristics

- official current supported checkout/setup-python major versions;
- `permissions: contents: read` unless a job explicitly needs more;
- concurrency cancellation for superseded PR runs;
- Python 3.9–3.12 matrix;
- editable development install;
- import smoke;
- pytest;
- Ruff;
- Black if enforced by repository policy;
- Bandit `-ll`;
- Docker build/health where practical;
- bounded workflow/job timeouts.

### Tasks

- [ ] `WS11-T01` Verify workflow triggers.
- [ ] `WS11-T02` Verify matrix versions.
- [ ] `WS11-T03` Verify dependency install command.
- [ ] `WS11-T04` Verify no secret is required for ordinary PR validation.
- [ ] `WS11-T05` Verify permissions are minimal.
- [ ] `WS11-T06` Verify all jobs execute on PR head, not a stale SHA.

### Acceptance criteria

Permanent CI fully green on PR #6 after temporary migration tooling is removed.

---

## WS-12 — Documentation Validation Workflow

**Priority:** P1  
**Depends on:** documentation updates

### Targets

- `.github/workflows/docs.yml`
- `scripts/check_docs.py`

### Tasks

- [ ] `WS12-T01` Require authoritative current docs.
- [ ] `WS12-T02` Fail empty current Markdown documents.
- [ ] `WS12-T03` Validate local links in active docs.
- [ ] `WS12-T04` Treat historical `docs/upgrades` and `docs/prompts` as archives with appropriate validation scope.
- [ ] `WS12-T05` Repair empty historical documents without inventing claims.

### Acceptance criteria

Docs workflow passes and catches a deliberately broken active link in a negative local test.

---

## WS-13 — Packaging Workflow

**Priority:** P1  
**Depends on:** WS-01, WS-10

### Target

`.github/workflows/package.yml`

### Tasks

- [ ] `WS13-T01` Build wheel.
- [ ] `WS13-T02` Build sdist.
- [ ] `WS13-T03` Install built artifact in a clean environment.
- [ ] `WS13-T04` Run `pip check`.
- [ ] `WS13-T05` Import canonical package.
- [ ] `WS13-T06` Run health check from installed package.
- [ ] `WS13-T07` Upload build artifacts for validation where configured.
- [ ] `WS13-T08` Do not publish externally from this workflow until release credentials/policy exist.

### Acceptance criteria

Wheel and sdist are installable, contain expected files, and pass installed-artifact smoke tests.

---

## WS-14 — Dependency Audit and Supply Chain

**Priority:** P1/P2  
**Depends on:** WS-01

### Targets

- `.github/workflows/dependency-audit.yml`
- optional CodeQL/dependency review/SBOM workflow

### Tasks

- [ ] `WS14-T01` Run `pip-audit` on schedule/manual dispatch.
- [ ] `WS14-T02` Enable CodeQL where repository configuration permits.
- [ ] `WS14-T03` Add dependency review where available.
- [ ] `WS14-T04` Generate SBOM for release candidate.
- [ ] `WS14-T05` Generate checksums for release artifacts.
- [ ] `WS14-T06` Define signing/provenance plan before public publishing.

### Acceptance criteria

Known dependency findings are either fixed or explicitly risk-accepted with owner/scope; release artifacts have inventory evidence.

---

## WS-15 — Governance and Repository Controls

**Priority:** P1  
**Depends on:** none

### Required files

- `.github/CODEOWNERS`
- `.github/pull_request_template.md`
- `.github/ISSUE_TEMPLATE/bug_report.yml`
- `.github/ISSUE_TEMPLATE/feature_request.yml`
- `.github/ISSUE_TEMPLATE/config.yml`
- `.github/dependabot.yml`
- `CODE_OF_CONDUCT.md`
- `GOVERNANCE.md`
- `SUPPORT.md`
- authoritative root `SECURITY.md`
- authoritative root `CONTRIBUTING.md`

### Tasks

- [ ] `WS15-T01` Verify ownership and review routing.
- [ ] `WS15-T02` Verify issue/PR templates render correctly.
- [ ] `WS15-T03` Configure Dependabot for relevant ecosystems.
- [ ] `WS15-T04` Document recommended branch protection.
- [ ] `WS15-T05` Require PRs, required checks, resolved conversations, and no force push on `main` where repository settings permit.

### Acceptance criteria

Repository policy matches the checks relied on by this plan.

---

## WS-16 — Documentation Completion

**Priority:** P1  
**Depends on:** architecture/security decisions stabilized

### Active documentation

- `README.md`
- `ARCHITECTURE.md`
- `SECURITY.md`
- `CONTRIBUTING.md`
- `ROADMAP.md` (historical/current audit context; do not rewrite history)
- `ROADMAP-NEXT.md`
- `CHANGELOG.md`
- `QUICKSTART.md`
- `CHECKLIST.md`
- `IMPLEMENTATION_CHECKLIST.md`
- `docs/README.md`
- `docs/exec-planning.md`
- category index files

### Tasks

- [ ] `WS16-T01` Document canonical `src/zcoder` layout.
- [ ] `WS16-T02` Document security execution boundaries.
- [ ] `WS16-T03` Document clean development setup.
- [ ] `WS16-T04` Document validation commands.
- [ ] `WS16-T05` Document release/rollback flow.
- [ ] `WS16-T06` Add category indexes for architecture/security/compliance/operations/enterprise/guides/upgrades/prompts.
- [ ] `WS16-T07` Repair empty historical upgrade records with an explicit repair note instead of invented historical detail.
- [ ] `WS16-T08` Keep archived prompts/upgrades historical.

### Acceptance criteria

A new maintainer can install, test, package, run, diagnose, secure, and release the project using repository documentation alone.

---

## WS-17 — Remove Temporary Migration Machinery

**Priority:** P0 before final PR merge  
**Depends on:** permanent generated changes are committed and verified

### Remove

- `.github/workflows/apply-repository-hardening.yml`
- `scripts/apply_repository_hardening.py`
- `scripts/run_repository_hardening.py`

### Tasks

- [ ] `WS17-T01` Verify these files are no longer required to reproduce permanent project state.
- [ ] `WS17-T02` Delete them in one bounded cleanup commit.
- [ ] `WS17-T03` Rerun permanent CI/docs/package workflows on the new head SHA.

### Acceptance criteria

No temporary migration mechanism remains in the final PR diff and all permanent validation remains green afterward.

---

## WS-18 — PR #6 Final Gate and Merge

**Priority:** P0  
**Depends on:** WS-01..17 required items

### Tasks

- [ ] `WS18-T01` Review final changed-file list.
- [ ] `WS18-T02` Confirm no generated secret, build junk, or temporary artifact is present.
- [ ] `WS18-T03` Confirm required workflows refer to the current PR head SHA.
- [ ] `WS18-T04` Confirm every required check is green.
- [ ] `WS18-T05` Confirm review conversations are resolved.
- [ ] `WS18-T06` Merge through normal repository protection.
- [ ] `WS18-T07` Record merge SHA.

### Acceptance criteria

PR #6 is merged without bypassing required checks.

---

## WS-19 — Post-Merge `main` Validation

**Priority:** P0  
**Depends on:** WS-18

### Tasks

- [ ] `WS19-T01` Observe workflows triggered by exact merge SHA.
- [ ] `WS19-T02` Verify Python matrix.
- [ ] `WS19-T03` Verify Ruff/Black/Bandit.
- [ ] `WS19-T04` Verify docs.
- [ ] `WS19-T05` Verify package.
- [ ] `WS19-T06` Verify Docker.
- [ ] `WS19-T07` Record evidence.
- [ ] `WS19-T08` If failure occurs, create a new remediation branch/PR rather than declaring completion.

### Acceptance criteria

Exact `main` merge SHA is green.

---

# 4. Production Qualification Workstreams

The following work begins after the hardening baseline is green. Some items may already exist; existing implementations must be validated rather than duplicated.

## WS-20 — PostgreSQL Production Readiness

- [ ] connection pool.
- [ ] transaction boundaries.
- [ ] schema migration/bootstrap strategy.
- [ ] retries only for safe transient errors.
- [ ] connect/query timeouts.
- [ ] health/readiness checks.
- [ ] test fixtures.
- [ ] rollback behavior.
- [ ] backup/restore runbook.

**Exit:** DB failure/recovery behavior is test-covered and documented.

## WS-21 — Reliability and Lifecycle

- [ ] standard timeout policy.
- [ ] retry/backoff policy.
- [ ] idempotency for mutating operations.
- [ ] cancellation propagation.
- [ ] graceful shutdown.
- [ ] subprocess cleanup.
- [ ] temp/resource cleanup.
- [ ] bounded concurrency.
- [ ] backpressure.
- [ ] provider rate-limit behavior.

**Exit:** retry/cancel/shutdown behavior passes fault-injection tests.

## WS-22 — Observability

- [ ] structured logs.
- [ ] correlation/request/job IDs.
- [ ] secret redaction.
- [ ] metrics for counts/errors/latency/timeouts/provider failures.
- [ ] tracing hooks.
- [ ] health/readiness/diagnostic output.

**Exit:** one failed execution can be traced end-to-end without leaking credentials.

## WS-23 — Tool/Agent Execution Policy

- [ ] explicit tool grants.
- [ ] working-directory restrictions.
- [ ] environment allowlist.
- [ ] timeout limits.
- [ ] output-size limits.
- [ ] audit events.
- [ ] dangerous-operation policy.
- [ ] permission regression tests.

**Exit:** tool execution is bounded, auditable, and deny-by-default where appropriate.

## WS-24 — API/Web Security

- [ ] authentication boundary.
- [ ] authorization boundary.
- [ ] request validation.
- [ ] payload limits.
- [ ] timeouts.
- [ ] request IDs.
- [ ] error schema.
- [ ] CORS policy.
- [ ] security headers.
- [ ] API versioning expectations.

**Exit:** API abuse/error paths are predictable and test-covered.

## WS-25 — Generated Artifact Safety

- [ ] Excel generation positive/negative tests.
- [ ] PowerPoint generation positive/negative tests.
- [ ] restricted execution coverage.
- [ ] malformed input handling.
- [ ] formula/content injection review.
- [ ] CPU/time/output limits where applicable.

**Exit:** generated artifact flows cannot bypass the execution policy through known tested vectors.

---

# 5. Qualification Test Matrix

## 5.1 Functional

| Area | Unit | Integration | E2E |
|---|---:|---:|---:|
| CLI | yes | yes | yes |
| Config | yes | yes | smoke |
| Security helpers | yes | yes | targeted |
| PostgreSQL | adapter | yes | yes |
| Git integration | yes | yes | yes |
| Provider adapters | yes | yes | selected |
| Tool execution | yes | yes | yes |
| Excel/PowerPoint | yes | yes | yes |
| Web/API | yes | yes | yes |

## 5.2 Security negative cases

- command injection;
- shell metacharacters;
- path traversal;
- malformed URL schemes;
- SSRF-style inputs according to threat model;
- unsafe AST;
- SQL injection/identifier abuse;
- environment secret leakage;
- secret leakage to logs;
- excessive output/timeouts.

## 5.3 Failure cases

- DB offline;
- provider offline;
- provider rate limited;
- command timeout;
- cancellation;
- permission denied;
- malformed config;
- partial artifact failure;
- corrupted file input;
- rollback after failed mutation.

---

# 6. Release Candidate Plan

## RC-01 — Freeze candidate

- [ ] choose exact `main` SHA;
- [ ] stop unrelated feature changes during validation;
- [ ] update version/changelog only through a reviewed commit if required.

## RC-02 — Clean checkout qualification

From a fresh checkout:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pip check
ruff check src tests scripts
black --check src tests scripts
bandit -r src/zcoder -ll
pytest -q
python -m zcoder.main --health-check
```

Then build from source metadata:

```bash
python -m build
```

Install the resulting wheel in another clean environment and rerun import/CLI/health smoke tests.

## RC-03 — Container qualification

- [ ] clean Docker build.
- [ ] start container.
- [ ] health check.
- [ ] expected signal/shutdown behavior.
- [ ] non-root runtime where supported.
- [ ] no secret embedded in image history/config.

## RC-04 — Artifact inspection

- [ ] wheel contents.
- [ ] sdist contents.
- [ ] license/metadata.
- [ ] no temp migration tools unless intentionally part of source distribution.
- [ ] no `.env`, tokens, logs, local databases, caches, or credentials.
- [ ] SBOM/checksums if release workflow supports them.

## RC-05 — Upgrade and rollback

- [ ] install/upgrade from prior supported version.
- [ ] preserve expected configuration/data.
- [ ] document incompatibilities.
- [ ] validate rollback instructions.

### RC exit criteria

All release checks pass on the exact frozen candidate SHA.

---

# 7. Release Policy

Do not publish to PyPI or a container registry merely because package/container builds succeed.

External publishing requires explicit confirmation of:

- package/registry ownership;
- release version;
- repository/environment secrets;
- workflow permissions;
- provenance/signing policy;
- rollback/removal procedure;
- artifact retention policy.

Until those are configured, a successful GitHub Release or validated local/CI artifact may be used as the completion boundary.

---

# 8. Rollback Rules

1. **Before merge:** revert/fix on the hardening branch and rerun PR checks.
2. **After merge but before release:** create a remediation branch from `main`, fix via PR, and validate the new merge SHA.
3. **After tagged release:** prefer a forward fix when safe; otherwise document and perform a release rollback according to artifact/package constraints.
4. Never rewrite protected `main` history to make a failed validation disappear.
5. Never delete failure evidence needed to explain a release incident.

---

# 9. Agent/Automation Operating Rules

An automated coding agent executing this plan MUST:

1. read the current PR head SHA before using workflow logs;
2. use logs produced from that SHA;
3. make the smallest coherent fix that addresses the root cause;
4. add/regress tests for security-sensitive fixes;
5. avoid weakening validation config;
6. commit to the active hardening branch until its merge;
7. rerun permanent workflows after deleting temporary migration machinery;
8. merge only after required checks are green;
9. validate `main` after merge;
10. report exact unresolved blockers instead of marking work complete prematurely.

---

# 10. Completion Board

| ID | Gate | Status |
|---|---|---|
| C01 | Architecture/src migration merged | DONE |
| C02 | Post-migration consistency merged | DONE |
| C03 | Repository hardening permanent state applied | DONE/VERIFY |
| C04 | Dependency contract green | TODO |
| C05 | Ruff green | TODO |
| C06 | Black green | TODO |
| C07 | Bandit `-ll` green | TODO |
| C08 | pytest 3.9–3.12 green | TODO |
| C09 | Docs workflow green | TODO |
| C10 | Package workflow green | TODO |
| C11 | Docker validation green | TODO |
| C12 | Temporary migration tooling removed | TODO |
| C13 | PR #6 all required checks green | TODO |
| C14 | PR #6 merged | TODO |
| C15 | exact `main` merge SHA green | TODO |
| C16 | architecture/runtime qualification | TODO |
| C17 | security regression qualification | TODO |
| C18 | dependency/supply-chain qualification | TODO |
| C19 | clean release-candidate qualification | TODO |
| C20 | release/rollback evidence complete | TODO |

`DONE/VERIFY` means implementation exists but must still be validated as part of the final permanent workflow state.

---

# 11. Final Definition of Complete

The project is **COMPLETE / PRODUCTION PASS** only when:

```text
source migration        PASS
post-migration cleanup  PASS
hardening               PASS
lint/format              PASS
security                PASS
test matrix             PASS
docs                    PASS
package                 PASS
container               PASS
PR merge                PASS
main post-merge CI      PASS
runtime qualification   PASS
security regressions    PASS
clean RC validation     PASS
release evidence        PASS
```

A green temporary migration workflow, a locally successful edit, or a merged architecture PR alone is insufficient to satisfy this definition.
