# zcoder Production Readiness & Execution Planning

**Document Status:** ACTIVE // CANONICAL EXECUTION PLAN  
**Current Baseline:** `main@2a8adcf817c66aa7fa032ce26c376782c705c939`  
**Last Updated:** 2026-08-19  
**Scope:** Drive `cvsz/zcoder` from the verified Clean Architecture baseline to enterprise-grade-ready, production-grade-ready final release while preserving Upgrade-20/24 bounded execution, provider-neutral model routing, security gates, test/coverage thresholds, and exact-head hosted verification.

---

## 1. Executive State

The repository has completed the original Upgrade-01..25 foundation, durable engineering runtime, bounded continuous engineering loop, canonical `src/zcoder` migration, and service/infrastructure architecture hardening. The active program now has two coordinated tracks:

1. **Security closure first** — remediate confirmed source-to-sink vulnerabilities before stacking feature work on the affected runtime boundary.
2. **Production/Claude-Code-like parity** — complete provider-neutral terminal/agent UX, permissions, tools, hooks, skills, MCP, subagents/teams, plugins, sessions, observability, deployment, and live fleet wiring without using Claude Free/Pro consumer OAuth credentials.

Implementation is not completion. A slice is complete only when its exact PR head is green across the applicable CI, CodeQL, Dependency Review, Release Gate, Helm, SDK/TypeScript, security, and supported Python matrix, with no unresolved blocker.

---

## 2. Non-Negotiable Execution Rules

1. **Upgrade-20/24 bounded execution:** one bounded vertical slice at a time; no recursive autonomous stacking on an unverified baseline.
2. **Exact-head verification:** merge only the exact head SHA that passed hosted verification.
3. **No gate weakening:** never lower coverage, skip/xfail security regressions, relax permissions, suppress CodeQL/Dependency Review findings to obtain green status, or weaken Release Gate/Helm/SDK checks.
4. **Security source-to-sink rule:** validate reachability before calling a hypothesis a finding; patch only confirmed findings.
5. **Smallest secure architectural change:** reuse existing centralized primitives instead of duplicating validators or introducing compatibility hacks.
6. **Provider-neutral authentication:** do not depend on Claude Free/Pro consumer OAuth tokens. Support explicit provider API keys, enterprise gateways, and local/free runtimes where available.
7. **No third-party/production attacks:** security validation stays within repository tests, controlled local fixtures, and non-production resources.
8. **Fail closed:** permission, filesystem, network, tenant, and approval boundaries must deny ambiguous or unsafe operations.
9. **No unsafe broad rewrites:** if a connector mutation would rewrite a large source file beyond the bounded diff, reset the branch rather than carrying a risky replacement.
10. **Docs are evidence:** update this file and release evidence when a slice is actually verified/merged; do not mark pending work complete.

---

## 3. Current Verified Architecture Baseline

- Canonical implementation lives under `src/zcoder/`.
- Domain/application dependency direction is guarded by architecture tests.
- Upgrade-20 remains the task-level engineering authority; Upgrade-24 owns queue policy; durable continuous engineering composes persistence/leases/runtime around them.
- SQLite/PostgreSQL durable engineering state, cross-process run leases, fencing, restart/idempotency, and maintenance orchestration are implemented.
- CI supports Python 3.9, 3.10, 3.11, and 3.12 plus lint, Bandit/security, Docker, CodeQL, Dependency Review, Helm, Release Gate, and SDK/TypeScript validation.
- Local/offline/no-cost operation remains a first-class path; paid-provider fallback must never be implicit.

---

## 4. Security Attack-Surface Coverage Matrix

| ID | Surface | State | Completion Evidence / Next Gate |
|---|---|---|---|
| SEC-001 | Deep Research / outbound SSRF | FIXED / MERGED | Existing SSRF protections and regressions merged |
| SEC-002 | Sandbox filesystem traversal | FIXED / MERGED | Filesystem boundary protections merged |
| SEC-003 | Sandbox direct network bypass | FIXED / MERGED | Interpreter and `/dev/tcp`/`/dev/udp` bypass regressions merged |
| SEC-OUTPUT | Sensitive provider/runtime error disclosure | FIXED / MERGED | Stable client errors + server-side logging merged |
| **SEC-004** | **CodeAgent Read/Write/Edit/Glob/Grep/LS workspace escape** | **CONFIRMED / ACTIVE** | Patch all six sinks through `safe_resolve()` + traversal/absolute/symlink regressions + hosted verification |
| SEC-005 | CodeAgent WebFetch SSRF | HYPOTHESIS / NEXT | Validate redirect/DNS/IP/source-to-sink behavior after SEC-004 merge |
| SEC-006 | MCP/tool-output trust boundary | QUEUED | Validate untrusted MCP/tool output into shell/files/network/actions |
| SEC-007 | RAG/document trust + tenant isolation | QUEUED | Validate cross-tenant retrieval and document-triggered tool paths |
| SEC-008 | Secrets/environment inheritance | QUEUED | Validate subprocess/hooks/MCP env propagation and redaction |
| SEC-009 | Authorization/approval boundaries | QUEUED | Validate permission modes, approval replay/expiry, mutating actions |
| SEC-010 | CI/dependency/supply-chain | QUEUED | Review workflow permissions, provenance, dependency pinning, release artifacts |

### 4.1 Active SEC-004 Source-to-Sink Chain

Confirmed path on the current baseline:

```text
model-controlled tool input
  -> CodeAgent._execute_tool()
  -> non-interactive askPermission auto-approval for Read/Glob/Grep/LS
  -> CodeAgent._run_tool()
  -> Path(session.cwd) / supplied path
  -> local filesystem read/enumeration/write/edit
```

Affected built-ins: `Read`, `Write`, `Edit`, `Glob`, `Grep`, `LS`.

Required remediation: use the existing `zcoder.core.security.safe_resolve(path, session.cwd)` containment primitive before every affected filesystem sink. `safe_resolve()` canonicalizes the target and rejects relative traversal, absolute escape, and symlink escape.

Required regressions:

- relative `../` escape rejected;
- absolute path outside workspace rejected;
- symlink escape rejected;
- `Read`, `Glob`, `Grep`, and `LS` cannot enumerate/read outside workspace;
- `Write` and `Edit` cannot mutate outside workspace;
- normal in-workspace behavior remains unchanged.

---

## 5. Active Bounded Execution Queue

### Slice A — SEC-004 CodeAgent Filesystem Containment — **IN PROGRESS**

**Branch:** `security-04-codeagent-filesystem-boundary-v9`  
**Base:** `main@2a8adcf817c66aa7fa032ce26c376782c705c939`

Tasks:

- [x] Revalidate current `main` and confirm no open PR blocker.
- [x] Revalidate SEC-004 source-to-sink reachability.
- [ ] Route `Read` through `safe_resolve()`.
- [ ] Route `Write` through `safe_resolve()` before mkdir/write.
- [ ] Route `Edit` through `safe_resolve()` before read/write.
- [ ] Route `Glob` base path through `safe_resolve()`.
- [ ] Route `Grep` base path through `safe_resolve()`.
- [ ] Route `LS` path through `safe_resolve()`.
- [ ] Add focused regression tests for traversal, absolute, symlink, read/enumeration, write/edit mutation.
- [ ] Run/obtain Ruff + Black + Bandit + Python 3.9–3.12 + Docker as applicable.
- [ ] Require CodeQL + Dependency Review + Release Gate + Helm + SDK/TypeScript on the exact head.
- [ ] Resolve all review blockers.
- [ ] Squash/exact-head merge only after all gates are green.

Stop rule: if hosted verification is pending or red, do not begin Slice B.

### Slice B — SEC-005 CodeAgent WebFetch SSRF

Start only after Slice A is merged. Validate the full path from model URL input through `_webfetch_retrying()`/network helper, including redirect hops, hostname/IP validation, loopback/private/link-local/metadata ranges, and DNS rebinding/repinning behavior before deciding whether a finding exists.

### Slice C — Permission & Approval Parity/Hardening

Unify deny/ask/allow precedence, non-interactive behavior, hooks, mutating-tool approval, and auditable decision records. Preserve fail-closed behavior and explicit operator authority.

### Slice D — Claude-Code-like Provider-Neutral Feature Parity

Progress in bounded PRs through:

1. terminal/headless/JSON UX;
2. sessions/resume/checkpoints/rewind;
3. CLAUDE.md + scoped rules/config compatibility;
4. skills/slash commands;
5. hooks lifecycle;
6. MCP transports/tool discovery/trust policy;
7. subagents and agent teams;
8. plugins/marketplaces;
9. complete built-in tool parity;
10. IDE/web/remote/CI workflows;
11. provider-neutral routing and local/free runtimes;
12. observability, audit, tenant isolation, quotas, deployment, upgrade/migration, disaster recovery.

Reference priority for parity research:

```text
official Claude Code documentation
  -> public anthropics/claude-code repository
  -> vetted third-party reverse-engineering/design references
  -> zcoder gap analysis
  -> one bounded implementation PR
```

Third-party references are design aids, not source-of-truth authentication/proprietary implementation sources.

### Slice E — Production Fleet Wiring

After security-critical agent boundaries are green:

- provider-backed GitHub adapter construction;
- durable SQLite/PostgreSQL multi-process/fleet runtime wiring;
- worker/service entrypoints for scheduled maintenance campaigns;
- crash-resume/fencing/lease integration tests across processes;
- explicit repository mutation approvals;
- OTel metrics/logs/traces and operational dashboards;
- deployment health/readiness, backup/restore, rollback and upgrade evidence.

---

## 6. Final Release Qualification Matrix

Final Release may be declared only when all applicable rows are green on the exact release candidate:

| Gate | Requirement |
|---|---|
| Python | 3.9 / 3.10 / 3.11 / 3.12 all green |
| Coverage | Existing repository threshold preserved or increased |
| Lint/Format | Ruff + Black green |
| Security | Bandit/security gate green; confirmed findings closed or explicitly release-blocking |
| Code scanning | CodeQL green with no unresolved introduced alert |
| Dependencies | Dependency Review green; no unaccepted critical/high release blocker |
| Containers | Docker build/version/health smoke green |
| Helm | Lint/template checks green |
| SDK | TypeScript/SDK compatibility checks green |
| Release Gate | Production release audit green |
| Architecture | Dependency direction/cycle guards green |
| AuthN/AuthZ | Provider-neutral auth, RBAC/approval ceilings, no consumer OAuth dependency |
| Tenancy | Tenant/data isolation regressions green |
| Network | SSRF/redirect/private-network boundaries verified |
| Filesystem | Workspace/sandbox containment verified |
| Observability | Structured logs, metrics, tracing, audit events verified |
| Durability | restart/idempotency/lease/fencing/crash recovery verified |
| Packaging | clean wheel/install + container artifacts + checksums/SBOM as configured |
| Operations | health/readiness, config validation, rollback/backup/restore evidence |
| Documentation | README/architecture/security/runbooks/upgrade/release evidence current |

---

## 7. Completion Evidence Ledger

For each merged slice record:

- PR number and exact verified head SHA;
- merge commit SHA;
- required workflow run IDs/results;
- test/coverage result;
- security finding closed or capability delivered;
- migration/backward-compatibility note;
- rollback note when behavior/storage/config changed;
- next highest-priority unresolved slice.

Do not mark **Final Release Complete** until every release-blocking row in Section 6 is satisfied on one exact release candidate commit.
