# zcoder Production Readiness & Execution Planning

**Document Status:** ACTIVE // CANONICAL EXECUTION PLAN  
**Current Baseline:** `main@03010dccaacc4bfdb7e36d41ff51c677e256be84`  
**Last Updated:** 2026-08-20  
**Scope:** Drive `cvsz/zcoder` from the verified Clean Architecture baseline to enterprise-grade-ready, production-grade-ready final release while preserving Upgrade-20/24 bounded execution, provider-neutral model routing, security gates, test/coverage thresholds, exact-head hosted verification, and rollback-safe delivery.

---

## 1. Executive State

The repository has completed the Upgrade-01..25 foundation, durable engineering runtime, bounded continuous engineering loop, canonical `src/zcoder` migration, service/infrastructure architecture hardening, and the first four confirmed AI-agent security remediation slices.

The active program now has three coordinated tracks:

1. **Security closure first** — validate and remediate remaining source-to-sink attack surfaces before stacking feature work on affected runtime boundaries.
2. **Claude-Code-like provider-neutral parity** — complete terminal/agent UX, permissions, tools, hooks, skills, MCP, subagents/teams, plugins, sessions, remote/headless workflows, and provider routing without using Claude Free/Pro consumer OAuth credentials.
3. **Enterprise production qualification** — complete fleet wiring, auditability, multi-tenancy, observability, supply-chain evidence, backup/restore/rollback, deployment health, and exact-release-candidate qualification.

Implementation is not completion. A slice is complete only when its exact PR head is green across all applicable hosted gates and has no unresolved blocker. A feature being present does not make the repository production-ready until security, durability, operational, and release evidence are green on the same exact release candidate.

---

## 2. Non-Negotiable Execution Rules

1. **Upgrade-20/24 bounded execution:** one bounded vertical slice at a time; no recursive autonomous stacking on an unverified baseline.
2. **Exact-head verification:** merge only the exact head SHA that passed hosted verification.
3. **No gate weakening:** never lower coverage, skip/xfail security regressions, relax permissions, suppress CodeQL/Dependency Review findings to obtain green status, or weaken Release Gate/Helm/SDK checks.
4. **Security source-to-sink rule:** validate reachability before calling a hypothesis a finding; patch only confirmed findings.
5. **Smallest secure architectural change:** reuse centralized security/domain primitives instead of duplicating validators or introducing compatibility hacks.
6. **Provider-neutral authentication:** do not depend on Claude Free/Pro consumer OAuth tokens. Support explicit provider API keys, enterprise gateways, and local/free runtimes where available.
7. **No third-party/production attacks:** security validation stays within repository tests, controlled fixtures, localhost/private test resources, and non-production resources.
8. **Fail closed:** permission, filesystem, network, tenant, approval, and identity boundaries must deny ambiguous or unsafe operations.
9. **No unsafe broad rewrites:** if a connector mutation would rewrite a large source file beyond the bounded diff, reset rather than carry a risky replacement.
10. **Docs are evidence:** update this file and release evidence only after state is actually verified; never mark pending work complete.
11. **No hidden paid fallback:** offline/local/no-cost modes must not silently route to paid providers.
12. **Release candidate immutability:** final qualification evidence must point to one exact release-candidate SHA; any code/config/dependency change invalidates that evidence and requires re-verification.

---

## 3. Current Verified Architecture Baseline

- Canonical implementation lives under `src/zcoder/`.
- Domain/application dependency direction is guarded by architecture tests.
- Upgrade-20 remains task-level engineering authority; Upgrade-24 owns bounded queue policy; durable continuous engineering composes persistence, leases, fencing, and runtime around them.
- SQLite/PostgreSQL durable engineering state, cross-process run leases, fencing, restart/idempotency, and maintenance orchestration are implemented.
- CI supports Python 3.9, 3.10, 3.11, and 3.12 plus Ruff, Black, Bandit/security, Docker, CodeQL, Dependency Review, Helm, Release Gate, and SDK/TypeScript validation.
- Local/offline/no-cost operation remains a first-class path; paid-provider fallback must never be implicit.
- CodeAgent filesystem access now uses the centralized canonical containment primitive for `Read`, `Write`, `Edit`, `Glob`, `Grep`, and `LS`.
- API server default bind is loopback-safe (`127.0.0.1`) while preserving explicit operator override through configuration.

---

## 4. Security Attack-Surface Coverage Matrix

| ID | Surface | State | Completion Evidence / Next Gate |
|---|---|---|---|
| SEC-001 | Deep Research / outbound SSRF | FIXED / MERGED | Existing SSRF protections and regressions merged |
| SEC-002 | Sandbox filesystem traversal | FIXED / MERGED | Filesystem boundary protections merged |
| SEC-003 | Sandbox direct network bypass | FIXED / MERGED | Interpreter and `/dev/tcp`/`/dev/udp` bypass regressions merged |
| SEC-OUTPUT | Sensitive provider/runtime error disclosure | FIXED / MERGED | Stable client errors + server-side logging merged |
| **SEC-004** | **CodeAgent Read/Write/Edit/Glob/Grep/LS workspace escape** | **FIXED / VERIFIED / MERGED** | PR #48 exact head `14842197ddedbcffe912f42033ce962974d00e0e`; squash merge `03010dccaacc4bfdb7e36d41ff51c677e256be84` |
| **SEC-005** | **CodeAgent WebFetch SSRF** | **ACTIVE HYPOTHESIS** | Validate source→sink, redirects, hostname/IP checks, metadata/private ranges, DNS re-resolution/repinning before calling a finding |
| SEC-006 | MCP/tool-output trust boundary | QUEUED | Validate untrusted MCP/tool output into shell/files/network/actions |
| SEC-007 | RAG/document trust + tenant isolation | QUEUED | Validate cross-tenant retrieval, document-triggered actions, tenant-scoped indexes/caches |
| SEC-008 | Secrets/environment inheritance | QUEUED | Validate subprocess/hooks/MCP env propagation, secret redaction, child-process inheritance |
| SEC-009 | Authorization/approval boundaries | QUEUED | Validate deny/ask/allow precedence, approval replay/expiry, mutating actions, audit identity |
| SEC-010 | CI/dependency/supply-chain | QUEUED | Review workflow permissions, action pinning, provenance, SBOM, dependency pinning, artifact integrity |

### 4.1 SEC-004 Closure Evidence

Confirmed pre-fix path:

```text
model-controlled tool input
  -> CodeAgent._execute_tool()
  -> non-interactive askPermission auto-approval for Read/Glob/Grep/LS
  -> CodeAgent._run_tool()
  -> model-controlled filesystem path
  -> local filesystem read/enumeration/write/edit outside session.cwd
```

Merged remediation:

- `Read`, `Write`, `Edit`, `Glob`, `Grep`, and `LS` pass through `zcoder.core.security.safe_resolve()`;
- relative traversal, absolute escapes, and symlink escapes are rejected;
- Glob/Grep path-like traversal patterns are rejected before enumeration;
- mutation tests prove Write/Edit do not alter files outside the workspace;
- normal in-workspace behavior remains covered;
- non-interactive permission behavior still routes through containment.

Exact hosted verification for PR #48 head `14842197ddedbcffe912f42033ce962974d00e0e`:

- CI run `32278816677` — success;
- CodeQL run `32278816719` — success;
- Dependency Review run `32278816785` — success;
- Release Gate run `32278816690` — success;
- Helm Lint run `32278816768` — success;
- SDK & TypeScript run `32278816704` — success;
- Python 3.9 / 3.10 / 3.11 / 3.12, Ruff, Black, Bandit/security, and Docker jobs — success;
- unresolved review threads — none.

---

## 5. Active Bounded Execution Queue

### Slice A — SEC-004 CodeAgent Filesystem Containment — **COMPLETE / MERGED**

**PR:** #48  
**Verified Head:** `14842197ddedbcffe912f42033ce962974d00e0e`  
**Merge Commit:** `03010dccaacc4bfdb7e36d41ff51c677e256be84`

Tasks:

- [x] Revalidate source-to-sink reachability.
- [x] Route `Read`, `Write`, `Edit`, `Glob`, `Grep`, and `LS` through centralized containment.
- [x] Add traversal, absolute, symlink, enumeration, mutation, normal-behavior, and non-interactive permission regressions.
- [x] Ruff + Black green.
- [x] Bandit/security green.
- [x] Python 3.9–3.12 green.
- [x] Docker green.
- [x] CodeQL + Dependency Review + Release Gate + Helm + SDK/TypeScript green.
- [x] No unresolved review blocker.
- [x] Exact-head squash merge complete.

### Slice B — SEC-005 CodeAgent WebFetch SSRF — **ACTIVE**

Do not assume a finding. First validate the complete source-to-sink chain from model-controlled URL input through every fetch helper and redirect hop.

Required analysis:

- [ ] Identify all `WebFetch`/URL-fetch source entry points and actual network sinks.
- [ ] Verify scheme restrictions and URL canonicalization.
- [ ] Verify hostname resolution and IP classification before connection.
- [ ] Block loopback, RFC1918/private, link-local, multicast, unspecified, reserved/documentation, and cloud metadata destinations where applicable.
- [ ] Revalidate every redirect hop rather than validating only the initial URL.
- [ ] Determine whether DNS resolution is pinned/revalidated sufficiently to prevent hostname-to-private-address rebinding between validation and connection.
- [ ] Verify IPv4 and IPv6 handling, including IPv4-mapped IPv6 forms.
- [ ] Bound redirect count, response size, timeout, and decompression/resource amplification.
- [ ] Confirm proxy/environment settings cannot silently bypass destination policy.
- [ ] Add regression tests only after reachability is confirmed.
- [ ] Open one bounded PR for the smallest architectural remediation if a finding is confirmed.

Stop rule: if SEC-005 PR hosted verification is pending or red, do not begin Slice C.

### Slice C — MCP / Tool-Output Trust Boundary

Validate whether untrusted MCP/tool output can cross into Bash, filesystem mutation, network actions, prompts with elevated tool authority, or structured action dispatch without an explicit trust/approval transition.

### Slice D — Permission & Approval Parity/Hardening

Unify and verify:

- deny > ask > allow precedence;
- non-interactive fail-closed semantics for mutating tools;
- hook semantics that cannot override a higher-priority deny;
- approval binding to actor/session/tool/action/resource;
- expiry/replay/idempotency protections;
- audit records for request, decision, executor, result, and denial reason.

### Slice E — Claude-Code-like Provider-Neutral Feature Parity

Progress only in bounded PRs through:

1. terminal/headless/streaming/JSON UX;
2. sessions, resume, checkpoints, rewind, branchable conversations;
3. CLAUDE.md-compatible memory plus scoped rules/config hierarchy;
4. skills and slash-command lifecycle;
5. hooks lifecycle and policy-safe event model;
6. MCP transports, discovery, resource/tool trust policy;
7. subagents and agent teams with bounded budgets/permissions;
8. plugins/marketplaces with provenance and permission manifests;
9. complete built-in tool parity with security boundaries;
10. IDE/web/remote/CI workflows;
11. provider-neutral routing, explicit API keys/gateways, local/free runtimes;
12. observability, audit, tenancy, quotas, deployment, upgrade/migration, disaster recovery.

Reference priority for parity research:

```text
official Claude Code documentation
  -> public anthropics/claude-code repository
  -> vetted third-party reverse-engineering/design references
  -> zcoder gap analysis
  -> one bounded implementation PR
```

Third-party reverse-engineering references are design aids only. Do not copy proprietary source, private protocols, authentication secrets, or consumer-subscription credential behavior.

### Slice F — Production Fleet Wiring

After security-critical agent boundaries are green:

- provider-backed GitHub adapter construction;
- durable SQLite/PostgreSQL multi-process/fleet runtime wiring;
- worker/service entrypoints for scheduled maintenance campaigns;
- crash-resume/fencing/lease integration tests across processes;
- explicit repository mutation approvals;
- OTel metrics/logs/traces and operational dashboards;
- readiness/liveness/startup health contracts;
- backup/restore, rollback, migration rehearsal, and disaster-recovery evidence;
- tenant quotas, admission control, backpressure, and bounded concurrency.

### Slice G — Supply-Chain & Release Engineering

- pin third-party GitHub Actions to immutable commits where policy requires;
- generate and retain SBOM/provenance for release artifacts;
- verify wheel/container/chart checksums and artifact signing policy;
- dependency review plus lock/pin strategy for reproducible builds;
- least-privilege workflow tokens and environment protections;
- secret-free build logs and release metadata;
- release rollback and compromised-artifact revocation procedure.

---

## 6. Enterprise Final Release Qualification Matrix

Final Release may be declared only when every applicable release-blocking row is green on one exact release-candidate SHA.

| Gate | Requirement | Current Program State |
|---|---|---|
| Python | 3.9 / 3.10 / 3.11 / 3.12 all green | Continuous per PR; must be green on final RC |
| Coverage | Existing threshold preserved or increased | Enforced; final RC evidence required |
| Lint/Format | Ruff + Black green | Enforced |
| Security | Bandit/security green; confirmed findings closed | SEC-005..010 remain to review |
| Code scanning | CodeQL green with no unresolved introduced alert | Enforced |
| Dependencies | Dependency Review green; no unaccepted high/critical release blocker | Enforced; reproducibility review pending |
| Containers | Docker build/version/health smoke green | Enforced; runtime hardening evidence pending |
| Helm | Lint/template checks green | Enforced; deployment rehearsal pending |
| SDK | TypeScript/SDK compatibility checks green | Enforced; parity completion pending |
| Release Gate | Production release audit green | Enforced |
| Architecture | Dependency direction/cycle guards green | Enforced |
| AuthN/AuthZ | Provider-neutral auth, RBAC/approval ceilings, no consumer OAuth dependency | Hardening review pending |
| Tenancy | Tenant/data isolation regressions green | Deep review pending |
| Network | SSRF/redirect/private-network/DNS-rebinding boundaries verified | SEC-005 active |
| Filesystem | Workspace/sandbox containment verified | SEC-002 + SEC-004 merged; final RC recheck required |
| MCP/Tools | Untrusted output cannot silently gain elevated side effects | Review pending |
| Secrets | Redaction + environment/process inheritance policy verified | Review pending |
| Observability | Structured logs, metrics, tracing, security/audit events verified | Production evidence pending |
| Durability | restart/idempotency/lease/fencing/crash recovery verified | Implemented baseline; fleet E2E evidence pending |
| Performance | bounded latency/memory/concurrency/backpressure targets documented and tested | Qualification pending |
| Packaging | clean wheel/install + container/chart artifacts + checksums/SBOM/provenance | Supply-chain slice pending |
| Operations | health/readiness, config validation, backup/restore, rollback, DR rehearsal | Qualification pending |
| Documentation | README/architecture/security/runbooks/upgrade/release evidence current | Continuous; final RC evidence required |

### 6.1 Final Release Hard Stops

Do not declare **Enterprise Final Release Complete** while any of these remain true:

- a confirmed high/critical security finding is unremediated;
- SEC-005 network trust boundary has not been reviewed;
- approval/authorization replay and mutation semantics are not verified;
- cross-tenant data/tool paths are not verified;
- MCP/tool-output trust transition is not verified;
- final release candidate lacks one complete hosted verification set;
- artifacts lack required integrity/provenance/SBOM evidence;
- backup/restore/rollback/DR procedures are untested;
- production observability and audit trails are not demonstrated;
- release documentation points to a different SHA than the qualified artifacts.

---

## 7. Completion Evidence Ledger

### SEC-004 — CodeAgent Filesystem Workspace Containment

- PR: #48
- verified head: `14842197ddedbcffe912f42033ce962974d00e0e`
- merge commit: `03010dccaacc4bfdb7e36d41ff51c677e256be84`
- CI: `32278816677` — success
- CodeQL: `32278816719` — success
- Dependency Review: `32278816785` — success
- Release Gate: `32278816690` — success
- Helm Lint: `32278816768` — success
- SDK & TypeScript: `32278816704` — success
- review threads: none unresolved
- security result: relative traversal, absolute escape, symlink escape, read/enumeration escape, and Write/Edit outside-workspace mutation closed for CodeAgent filesystem tools
- next security hypothesis: SEC-005 CodeAgent WebFetch SSRF

For every future merged slice record the PR number, exact verified head SHA, merge SHA, required workflow run IDs/results, test/coverage result, security/capability result, compatibility/migration note, rollback note, and next highest-priority unresolved slice.

Do not mark **Final Release Complete** until every release-blocking row in Section 6 is satisfied on one exact release candidate commit.