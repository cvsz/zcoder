# zcoder Production Readiness & Execution Planning

**Document Status:** ACTIVE // CANONICAL EXECUTION PLAN  
**Current Baseline:** `zcoder v1.40.0`  
**Last Updated:** 2026-08-14  
**Scope:** Track repository restructuring, Clean Architecture & Domain-Driven Design (DDD) migration, durable engineering runtime validation, continuous upgrade/update/feature orchestration, test accounting, release gate compliance, and enterprise deployment readiness.

---

## 1. Executive Summary

This document establishes the operational and architectural baseline for **zcoder v1.40.0** and records the continuous engineering upgrades layered on top of that release baseline.

### 1.1 Current Baseline & Key Metrics

- **Repository Layout:** Clean Architecture + DDD package structure under `src/zcoder/` with compatibility shims preserved in `src/*.py`.
- **Canonical Pre-Upgrade Baseline:** **807 passed**, **0 skipped**, **0 failed**, **0 collection warnings** in the previously verified local full-suite environment.
- **Durability & Crash Consistency:** SQLite WAL-mode and PostgreSQL engineering-store paths remain the durable task-store baseline.
- **Release Gate:** Capability gates cover security, compliance, data residency, multi-tenancy, and no-cost local AI execution.
- **Upgrade-24:** bounded queue-level orchestration for upgrade, update, feature implementation, and repair work.
- **Upgrade-25:** wires Upgrade-24 to the existing Upgrade-20 engineering runtime, adds cross-process durable work identity/resume, Upgrade-23 discovery, secret-aware bounded repository snapshots, optional existing GitHub CI repair integration, and a directly invokable module CLI.

Hosted CI counts may differ from the canonical local baseline because optional services/dependencies can be skipped. Do not replace the canonical local baseline with a hosted count unless the execution environment and skip semantics are equivalent.

---

## 2. Architecture & Domain Structure

```text
       ┌────────────────────────────────────────────────────────┐
       │               Interfaces (CLI, TUI, SDK)               │
       │               API (REST v1 Endpoints)                  │
       └───────────────────────────┬────────────────────────────┘
                                   │
                                   ▼
       ┌────────────────────────────────────────────────────────┐
       │               Application Services                     │
       │ Agent Runtime / Upgrade Loop / Continuous Engineering  │
       └───────────────────────────┬────────────────────────────┘
                                   │
                                   ▼
       ┌────────────────────────────────────────────────────────┐
       │               Domain Models & Interfaces               │
       │     Engineering / Tenancy / Residency / Portfolio      │
       └───────────────────────────▲────────────────────────────┘
                                   │
       ┌───────────────────────────┴────────────────────────────┐
       │               Infrastructure Adapters                  │
       │ SQLite / Postgres / Auth / SCIM / OTel / GitHub        │
       └────────────────────────────────────────────────────────┘
```

### 2.1 Package Map (`src/zcoder/`)

| Package / Module | Layer | Purpose & Responsibilities |
| :--- | :--- | :--- |
| `zcoder.config` | Configuration | User settings, production configs, logging configuration |
| `zcoder.core` | Core Primitives | Exceptions, resilience/circuit breakers, health checks, security utilities |
| `zcoder.domain` | Domain | Entities, invariants, ports (`EngineeringTask`, `ResidencyPolicy`, `TenantPolicy`) |
| `zcoder.services.upgrade_loop` | Application Logic | Upgrade-24 bounded queue-level policy, retry/no-progress budgets, regression guard |
| `zcoder.services.continuous_engineering` | Application Logic | Upgrade-25 Upgrade-20 adapter, work-source composition, GitHub CI repair hook, CLI |
| `zcoder.services.upgrade_state` | Application/Local Adapter | Atomic durable upgrade ledger and bounded repository snapshotter |
| `zcoder.infrastructure` | Infrastructure | SQLite & PostgreSQL stores, OIDC/SCIM auth, OTel observability |
| `zcoder.claude` | Model & Tools | Anthropic API conformance, tool catalogs, code execution sandboxes, streaming |
| `zcoder.enterprise` | Enterprise | Local AI stack, Upgrade-20 autonomous engineering loop, portfolio execution |
| `zcoder.interfaces` | Presentation | CLI parsing, Textual TUI, streaming terminal, Python & TypeScript SDKs |
| `zcoder.worker` | Worker Process | Background worker lifecycle, job leasing, crash recovery |

---

## 3. Architecture Invariants & Standards

1. **Dependency Direction:** domain code must not depend on presentation/provider infrastructure. Provider-specific side effects remain behind application adapters.
2. **Durability:** committed task/store state must remain crash-consistent; Upgrade-25 local loop state uses atomic temporary-file write, flush/fsync, and `os.replace`.
3. **Multi-Tenancy & Data Sandboxing:** tenant isolation and object-store path sandboxing remain mandatory; zero-cost/offline mode must never silently fall back to paid APIs.
4. **Security & Identity:** secrets are not persisted in plaintext application configuration, outbound network boundaries retain SSRF protections, and identity/RBAC ceilings remain enforced.
5. **Autonomous Loop Safety:** queue-level work is bounded by global iterations, per-item attempts, and no-progress budgets; newly introduced regressions remain a hard-stop signal by default.
6. **Execution Authority:** Upgrade-20 remains the task-level engineering authority. Upgrade-24 owns queue-level policy. Upgrade-25 is the composition and persistence layer and must not become a duplicate task engine.
7. **Restart Idempotency:** a durable `SUCCEEDED` fingerprint cannot execute again after process restart. A durable blocker cannot disappear into a false `COMPLETED` report.
8. **Push Safety:** automatic repository push is local-only by default and requires explicit operator opt-in.
9. **Context Safety:** Upgrade-25 repository snapshots are bounded and exclude `.env*`, common private-key material, symlinks, `.git`, generated caches/build outputs, virtual environments, and dependency vendor trees.
10. **GitHub Repair Reuse:** CI repair must reuse the existing bounded `GitHubOrchestrator.execute_ci_repair_loop()` contract instead of introducing a second unbounded repair engine.

---

## 4. Test Accounting & Quality Matrix

| Category | Path | Scope |
| :--- | :--- | :--- |
| Unit Tests | `tests/unit/` | Isolated service/domain behavior including Upgrade-24 and Upgrade-25 policy/persistence |
| Integration Tests | `tests/integration/` | PostgreSQL, SQLite, OIDC, provider/conformance boundaries |
| E2E Tests | `tests/e2e/` | Durability restart, worker/campaign and runtime flows |
| Upgrade Suites | `tests/e2e/upgrade_suites/` | Capability regression suites for major upgrades |
| Canonical Local Baseline | `tests/` | **807 passed / 0 skipped / 0 failed** before Upgrade-24/25 additions |

Upgrade-24 adds `tests/unit/test_upgrade_loop.py`.

Upgrade-25 adds `tests/unit/test_continuous_engineering.py` for restart deduplication, pending resume, persisted blockers, explicit blocked retry, Upgrade-20 result adaptation, Upgrade-23 discovery, GitHub CI repair contract reuse, bounded secret-aware snapshots, fail-closed ledger parsing, and JSON work-file inputs.

Promote a new canonical full-suite count only after an equivalent local full environment completes with its intended optional dependencies/services available.

---

## 5. Upgrade & Capabilities Ledger

- [x] **Upgrade-01 to Upgrade-10:** Foundation APIs, streaming, thinking models, context editing, batch execution.
- [x] **Upgrade-11:** SOC 2 / ISO 27001 compliance evidence catalog and audit framework.
- [x] **Upgrade-12:** Stable `/api/v1/` public REST API, idempotency keys, rate limiting, Python & TypeScript SDKs.
- [x] **Upgrade-13:** Zero-cost offline core engine, local model routing, local object storage.
- [x] **Upgrade-14 to Upgrade-18:** Local AI stack, model preflight, quality engineering loops, production runtimes.
- [x] **Upgrade-19:** Project bootstrap planner, automated RAG ingestion, readiness reports.
- [x] **Upgrade-20:** Autonomous engineering loop with baseline/post-edit validation delta and task-level safety gates.
- [x] **Upgrade-21:** Durable SQLite & PostgreSQL engineering store with checkpoints/state snapshots.
- [x] **Upgrade-22:** Multi-tenant portfolio scheduler, campaign execution, worker fleet orchestration.
- [x] **Upgrade-23:** Maintenance intelligence, proactive issue detection, self-repair recommendations.
- [x] **Upgrade-24:** Bounded continuous upgrade/update/feature/repair meta-loop.
- [ ] **Upgrade-25:** Durable end-to-end continuous engineering pipeline — implementation complete on feature branch; hosted CI/merge pending.
- [x] **v1.40.0 Refactoring:** Clean Architecture & DDD `src/zcoder` migration with backward compatibility.

---

## 6. Execution Roadmap & Next Milestones

```text
 Milestone 1: Core Clean Architecture & Test Green Baseline      [ COMPLETED ]
 Milestone 2: Durability & Subprocess Import Alignment           [ COMPLETED ]
 Milestone 3: Release Gate Path & Verification Alignment         [ COMPLETED ]
 Milestone 4: Upgrade-24 Continuous Queue Meta-Loop              [ COMPLETED ]
 Milestone 5: Hosted CI/CD Gates                                 [ CONTINUOUS ]
 Milestone 6: Standalone Binary & Container Packaging Verify     [ READY FOR STAGING ]
 Milestone 7: Upgrade-25 Durable Runtime Wiring                  [ IMPLEMENTED / CI VERIFY ]
 Milestone 8: Production Provider Hardening & Live Fleet Wiring  [ NEXT ]
```

### 6.1 Upgrade-25 Verification Checklist

1. Run Ruff and Black against the new application/state modules and tests.
2. Run Bandit/security checks without exclusions added for the new code.
3. Run the focused Upgrade-24 and Upgrade-25 unit suites.
4. Run the full Python matrix and preserve the existing coverage threshold.
5. Run Docker image build/version smoke test.
6. Run CodeQL, Dependency Review, Helm Lint, SDK/TypeScript, and Release Gate workflows.
7. Fix implementation defects rather than weakening CI/test/security policy.
8. Mark Upgrade-25 complete only after all required hosted gates are green and the PR is merged.

### 6.2 Next Engineering Slice After Upgrade-25

The next high-value slice should move from composition to production fleet wiring:

- connect durable Upgrade-25 state to the existing SQLite/PostgreSQL engineering-store boundary where multi-process/fleet operation is required;
- add provider-backed live GitHub adapter construction rather than only dependency injection;
- expose worker/service entrypoints for scheduled maintenance campaigns;
- add integration/E2E crash-resume tests across process boundaries and durable database stores;
- preserve local-only/offline execution as the default and keep repository mutation behind explicit approval/policy.
