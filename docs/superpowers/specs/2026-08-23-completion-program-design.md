# zcoder Completion Program Design

**Date:** 2026-08-23  
**Repository:** `cvsz/zcoder`  
**Status:** Proposed design approved in chat; implementation not yet authorized  
**Baseline:** `main@786579a048574dbf52d4807d3bc1c7923b08a27a`

## 1. Goal

Drive `zcoder` from its current advanced-but-not-fully-qualified state to a defensible completion state without weakening security, CI, release, tenancy, durability, or supply-chain gates.

“Complete” means all repository-owned implementation gaps are either closed and verified on exact heads, or explicitly classified as external-environment qualification items with reproducible handoff evidence. Historical TODO text is not authoritative when later merged code has already superseded it.

## 2. Core Constraints

1. Preserve the repository’s bounded-slice execution model. Do not combine unrelated subsystems into a single high-risk PR.
2. Preserve exact-head verification. A change is complete only when the exact final head has passed all applicable hosted checks.
3. Never weaken tests, coverage, CodeQL, Dependency Review, Bandit, pip-audit, Gitleaks, Helm, Release Gate, SDK/TypeScript, or reproducibility gates to achieve green status.
4. Preserve fail-closed behavior at filesystem, network, identity, approval, tenancy, process-environment, quota, and release boundaries.
5. Do not mark production or disaster-recovery evidence complete without real evidence from the required environment.
6. Do not duplicate already-merged work merely because `exec-planning.md` still contains stale “remaining” text.
7. Keep local/offline/no-cost operation first-class and never introduce hidden paid-provider fallback.

## 3. Observed State Reconciliation

The canonical execution plan contains stale residual statements that predate later merged PRs. Before further implementation, repository truth must be reconciled against merged history.

Already merged work that must be treated as completed unless regression evidence proves otherwise includes:

- uv.lock drift detection / reproducibility gate (#88);
- keyless cosign container signing (#89);
- Helm package + SHA256 artifact generation (#90);
- release-tag semver gate linkage (#91);
- DR rehearsal runbook (#92);
- backup/restore strictness, weekly retention, dry-run support (#93);
- `/metrics`, `/health/live`, `/health/ready` (#94);
- OTel bootstrap wiring behind `ZCODER_OTEL_ENDPOINT` (#95);
- cross-process claim/fence/crash/reclaim durability evidence (#96);
- SQLite claim CAS + EngineeringWorker drain (#97);
- bounded maintenance scheduler + CLI composition (#98);
- admission-control domain/service seam (#99);
- clear-text sensitive tool-argument logging remediation (#101).

The completion program therefore starts from verified current behavior, not from stale backlog prose.

## 4. Remaining Completion Domains

### 4.1 Functional Placeholder Closure

The skills lifecycle currently exposes an install operation whose implementation was introduced as a placeholder. This is a real incomplete user-facing path and must be replaced with a secure implementation or explicitly removed from advertised capability.

Completion properties:

- no placeholder response remains for an advertised install path;
- installation source/provenance is explicit;
- destination paths remain contained;
- archive/path traversal and symlink escape are rejected;
- permission/provenance metadata remains enforced;
- duplicate/conflict behavior is deterministic;
- tests cover successful install, invalid source, traversal, collision, rollback/failure behavior, and lifecycle info/remove compatibility.

### 4.2 Fleet Admission Composition

PR #99 intentionally introduced an unwired `AdmissionGate` seam. The seam is useful but does not enforce quota/backpressure until composed at actual job-admission paths.

Completion properties:

- every production-relevant engineering/job submission entrypoint crosses one admission boundary before durable enqueue/claim;
- reservation occurs atomically enough to avoid oversubscription under concurrent submissions;
- failure to check or reserve fails closed;
- reservation release semantics are explicit for reject/cancel/failure paths;
- worker claim/fencing behavior remains independent from admission accounting;
- metrics/audit events expose admitted, rejected, throttled, and released decisions;
- JSON/SQLite/PostgreSQL or other active backends preserve documented parity where applicable.

### 4.3 Agent/Subagent Lifecycle Completion

Budget enforcement, tool validation, loader containment, sessions, rewind/branch, hooks, plugins, MCP validation, and CI/headless output already exist, but “subagent/team lifecycle” must be audited for true end-to-end completeness rather than inferred from partial controls.

Completion properties:

- creation, invocation, bounded execution, cancellation/termination, result propagation, and failure propagation are explicit;
- permission inheritance cannot widen authority silently;
- budget inheritance/caps remain monotonic or otherwise policy-defined;
- tenant/session identity is preserved across child execution;
- child output is treated as untrusted when crossing into elevated tool authority;
- lifecycle is observable/auditable;
- remote/headless/CI behavior is deterministic and has stable exit/output contracts.

If a “team” abstraction is not actually present or required by current product scope, the plan must not invent one merely to satisfy stale parity wording; scope should be narrowed to supported subagent orchestration.

### 4.4 Production Qualification

Implementation presence is insufficient for final release. The final release candidate must be qualified as one immutable exact SHA.

Required evidence categories:

- Python 3.10/3.11/3.12 test matrix;
- coverage threshold;
- Ruff/Black;
- Bandit, pip-audit, Gitleaks;
- CodeQL and Dependency Review;
- reproducibility/lock checks;
- Docker build and health behavior;
- Helm lint/template/package/checksum;
- SDK/TypeScript validation;
- release artifact checksums/SBOM/provenance/signature verification;
- tenancy/security regressions;
- durability/restart/fencing/crash-recovery regressions;
- backup/restore and DR procedure evidence;
- observability bootstrap/health/metrics smoke;
- bounded performance/backpressure targets where repository policy requires them.

Production-only or infrastructure-dependent checks must produce a `HANDOFF / REQUIRES ENVIRONMENT` record if the connected execution environment cannot validly run them. They must never be fabricated as green.

### 4.5 Governance Hardening

At design time, `main` is not protected and required status checks are not enforced at branch level. This creates a process gap even when workflows themselves are strong.

Completion properties:

- actual current check names are enumerated from successful current-head runs before rules are applied;
- branch protection/rulesets require the intended release-blocking checks;
- force-push/deletion policy is explicit;
- merge methods align with the repository’s signature/history policy;
- automation/bot exceptions are minimal and documented;
- governance changes are applied only after proving they will not deadlock normal maintenance or Dependabot workflows.

## 5. Bounded Completion Train

### C1 — Truth & Completion Ledger

Purpose: reconcile `exec-planning.md` and related release docs against current merged state.

Changes:

- update baseline SHA/date;
- mark #88–#101 completed where evidence supports it;
- remove obsolete “remaining” statements;
- retain only verified residuals;
- create a concise completion ledger mapping each residual to primary code path/owner, tests, hosted gates, and evidence requirement.

Acceptance:

- no contradictory state labels for the same capability;
- no `TODO`/`remaining` entry that is already closed by merged history;
- no completed state without evidence reference.

### C2 — Functional Placeholder Closure

Purpose: eliminate advertised placeholder behavior, starting with skills installation.

Changes are limited to the skills lifecycle and its tests unless audit proves another directly-coupled path is required.

Acceptance:

- placeholder behavior removed or intentionally de-advertised;
- security containment/provenance tests added first;
- exact-head CI/security gates green.

### C3 — Fleet Admission Composition

Purpose: wire the existing admission seam into real enqueue/submission paths.

Acceptance:

- all reachable submission paths audited;
- double-admission and bypass paths absent;
- concurrency/backpressure/quota regressions included;
- fail-closed backend-error behavior proven;
- no change weakens lease/fencing guarantees.

### C4 — Agent Lifecycle Completion

Purpose: close the remaining supported child-agent lifecycle gaps without inventing unsupported abstractions.

Acceptance:

- lifecycle state machine documented by tests;
- permissions, budget, tenancy, cancellation, and output trust boundaries covered;
- deterministic CLI/headless behavior covered;
- no child execution can silently broaden parent authority.

### C5 — Exact-RC Production Qualification

Purpose: choose one release-candidate SHA and run all repository-owned qualification gates plus environment-backed smoke/drill evidence.

Acceptance:

- one immutable SHA identifies the RC;
- all applicable hosted checks green on that SHA;
- artifact/SBOM/provenance/signature verification attached to that RC;
- required external evidence recorded against the same SHA;
- any code/config/dependency mutation after qualification invalidates the evidence and starts a new RC.

### C6 — Governance Hardening

Purpose: protect the now-qualified delivery path.

Acceptance:

- required checks use verified current context names;
- protected branch/ruleset configuration does not permit bypass of release-blocking checks except narrowly documented administrative recovery paths;
- documented operator recovery procedure exists;
- normal PR, Dependabot, and release automation remain operable.

## 6. Testing Strategy

Behavior changes use TDD where practical:

1. add/adjust the smallest regression that proves the incomplete or unsafe behavior;
2. observe the intended failure;
3. implement the minimal production change;
4. run targeted tests;
5. run full repository-relevant unit/e2e tests;
6. run Ruff/Black/Bandit locally where supported;
7. push only a bounded branch;
8. require exact-head hosted verification before merge.

Tests must validate properties, not only happy-path outputs. Security and durability tests must include negative/bypass cases.

## 7. Error Handling and Safety

- Configuration or backend uncertainty at admission/security boundaries fails closed.
- External-provider/network failures return stable client-facing errors and avoid secret-bearing raw exception output.
- Partial installation/mutation must avoid leaving trusted-looking incomplete state.
- Rollback strategy must be documented per slice; config-only slices should be single-commit reversible where practical.
- Connector/tool limitations must never be worked around by replacing whole large files when a bounded edit cannot be guaranteed.

## 8. Evidence Model

Every completion ledger row has one of four states:

- `COMPLETE / VERIFIED` — implementation merged and exact-head evidence exists;
- `IMPLEMENTED / QUALIFICATION PENDING` — code exists but final RC evidence is not yet attached;
- `INCOMPLETE / ACTIONABLE` — repository-owned implementation remains;
- `HANDOFF / REQUIRES ENVIRONMENT` — valid completion requires an environment or credential boundary unavailable to the current executor.

No other ambiguous “mostly done” state is allowed in the final ledger.

## 9. Non-Goals

- Rewriting already-secure subsystems for style reasons.
- Reintroducing Python 3.9 compatibility after the repository intentionally moved to Python >=3.10.
- Adding unrelated product features during completion work.
- Expanding parity claims beyond capabilities the repository actually intends to support.
- Re-signing or rewriting repository history as part of this completion train unless separately authorized and required.

## 10. Definition of Final Completion

`zcoder` may be declared complete for this program only when:

1. all repository-owned completion ledger rows are `COMPLETE / VERIFIED`;
2. all environment-dependent rows are backed by valid exact-RC evidence, not merely handoff placeholders;
3. no confirmed high/critical security blocker remains;
4. no advertised user-facing placeholder remains;
5. no known admission/authorization/tenant/security bypass remains;
6. one exact immutable RC SHA has passed the complete qualification matrix;
7. release artifacts are reproducible enough for the documented policy and include checksums, SBOM, provenance, and signature evidence;
8. deployment/health/rollback/DR evidence refers to that same RC;
9. governance prevents accidental merge around the required gates;
10. `exec-planning.md` and release docs accurately describe the verified state.

## 11. Implementation Order

Execute strictly in this order unless a newly discovered security blocker requires preemption:

`C1 -> C2 -> C3 -> C4 -> C5 -> C6`

C1 prevents duplicate work. C2/C3/C4 close repository-owned functionality before qualification. C5 freezes and qualifies an exact RC. C6 then hardens governance using the verified final check names, minimizing the risk of locking the repository with stale contexts.
