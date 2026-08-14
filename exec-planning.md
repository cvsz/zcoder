# zcoder Production Readiness & Execution Planning

**Document Status:** ACTIVE // CANONICAL EXECUTION PLAN  
**Current Baseline:** `zcoder v1.40.0`  
**Last Updated:** 2026-08-14  
**Scope:** Track the repository restructuring, Clean Architecture & Domain-Driven Design (DDD) migration, durable engineering runtime validation, continuous upgrade/update/feature orchestration, test accounting, release gate compliance, and enterprise deployment roadmap.

---

## 1. Executive Summary

This execution planning document establishes the operational and architectural baseline for **zcoder v1.40.0** following the complete src-layout migration and comprehensive test suite stabilization.

### 1.1 Current Baseline & Key Metrics

- **Repository Layout:** Clean Architecture + DDD package structure under `src/zcoder/` with zero breaking import changes (compatibility shims preserved in `src/*.py`).
- **Test Suite Status:** **807 passed**, **0 skipped**, **0 failed**, **0 collection warnings** at the pre-Upgrade-24 baseline (including all webapp and interactive TUI suites).
- **Durability & Crash Consistency:** SQLite WAL-mode verified crash-consistent under hard SIGKILL subprocess termination; PostgreSQL multiprocess store verified concurrency-safe.
- **Release Gate:** Over 50 capability gates mapped across security, compliance, data residency, multi-tenancy, and no-cost local AI execution.
- **Continuous Improvement Orchestration:** Upgrade-24 adds a bounded queue-level meta-loop for upgrade, update, feature implementation, and repair work with retry budgets, deduplication, regression guards, rollback hooks, and checkpoints.

---

## 2. Architecture & Domain Structure

The repository enforces strict Clean Architecture dependency boundaries:

```text
       ┌────────────────────────────────────────────────────────┐
       │               Interfaces (CLI, TUI, SDK)               │
       │               API (REST v1 Endpoints)                  │
       └───────────────────────────┬────────────────────────────┘
                                   │
                                   ▼
       ┌────────────────────────────────────────────────────────┐
       │               Application Services                     │
       │ (Agent Runtime, Orchestrator, Upgrade Loop, Compliance)│
       └───────────────────────────┬────────────────────────────┘
                                   │
                                   ▼
       ┌────────────────────────────────────────────────────────┐
       │               Domain Models & Interfaces               │
       │     (Engineering, Tenancy, Residency, Portfolio)       │
       └───────────────────────────▲────────────────────────────┘
                                   │
       ┌───────────────────────────┴────────────────────────────┐
       │               Infrastructure Adapters                  │
       │    (SQLite / Postgres Stores, Auth OIDC, SCIM, OTel)   │
       └────────────────────────────────────────────────────────┘
```

### 2.1 Package Map (`src/zcoder/`)

| Package / Module | Layer | Purpose & Responsibilities |
| :--- | :--- | :--- |
| `zcoder.config` | Configuration | User settings, production configs, logging configuration |
| `zcoder.core` | Core Primitives | Exceptions, resilience/circuit breakers, health checks, security utilities |
| `zcoder.domain` | Domain | Entities, invariants, ports (`EngineeringTask`, `ResidencyPolicy`, `TenantPolicy`) |
| `zcoder.services` | Application Logic | `agent_runtime`, `engineering_orchestrator`, `upgrade_loop`, `compliance_evidence`, `cowork` |
| `zcoder.infrastructure` | Infrastructure | SQLite & PostgreSQL stores, OIDC/SCIM auth, OTel observability |
| `zcoder.claude` | Model & Tools | Anthropic API conformance, tool catalogs, code execution sandboxes, streaming |
| `zcoder.enterprise` | Enterprise | Local AI stack, zero-cost offline platform, portfolio execution |
| `zcoder.interfaces` | Presentation | CLI parsing, Textual TUI, streaming terminal, Python & TypeScript SDKs |
| `zcoder.worker` | Worker Process | Background worker lifecycle, job leasing, crash recovery |

---

## 3. Architecture Invariants & Standards

1. **Dependency Direction (Inward Only):**
   - `interfaces/` and `api/` depend on `services/` and `domain/`.
   - `services/` depend on `domain/`.
   - `domain/` has **zero dependencies** on infrastructure, presentation, or framework code.
   - `infrastructure/` implements repository interfaces defined in `domain/interfaces/`.

2. **Durability & Crash Consistency:**
   - SQLite connections operate with `PRAGMA journal_mode=WAL` for atomic durability.
   - Process termination (SIGKILL) during batch tasks preserves committed state without database corruption.
   - Job claims use monotonic leases with automatic release on worker shutdown or timeout.

3. **Multi-Tenancy & Data Sandboxing:**
   - Tenant isolation enforced on all store queries via tenant predicates.
   - Local object storage enforces strict path sandboxing preventing directory traversal.
   - Zero silent fallback to commercial paid APIs when configured in zero-cost / offline mode.

4. **Security & Identity:**
   - API keys stored strictly as SHA-256 hashes.
   - SSRF protection on all outbound customer webhooks (blocking metadata endpoints and loopback).
   - SCIM 2.0 provisioning and OIDC authentication with RBAC ceiling enforcement.

5. **Autonomous Loop Safety:**
   - Queue-level autonomous work must be bounded by global iteration and no-progress budgets.
   - One independently verifiable vertical slice is executed per Upgrade-24 iteration.
   - Newly introduced regressions are a hard stop by default.
   - Provider, GitHub, shell, and deployment side effects remain behind injected adapters/callbacks.
   - Upgrade-20 remains the task-level engineering execution authority; Upgrade-24 owns queue-level prioritization and progression.

---

## 4. Test Accounting & Quality Matrix

The test suite is structured by execution semantics:

| Category | Path | Test Count | Scope & Validation |
| :--- | :--- | :--- | :--- |
| **Unit Tests** | `tests/unit/` | ~380 + Upgrade-24 suite | Isolated logic, mock APIs, config parsing, security regex, token counting, continuous upgrade-loop policy |
| **Integration Tests** | `tests/integration/` | ~160 | PostgreSQL concurrency, SQLite stores, OIDC auth, conformance tests |
| **E2E Tests** | `tests/e2e/` | ~50 | Durability restarts, hard crash recovery, worker fleet campaigns |
| **Upgrade Suites** | `tests/e2e/upgrade_suites/` | ~200 | Regressions & capability verification (Upgrade-11 through Upgrade-20) |
| **Pre-Upgrade-24 Baseline** | `tests/` | **807 Passed** | **100% passing before this change (0 errors, 0 warnings, 0 skipped)** |

Upgrade-24 adds focused unit coverage in `tests/unit/test_upgrade_loop.py`. The full-suite total must only be promoted to a new canonical count after hosted/local CI verifies the branch.

---

## 5. Upgrade & Capabilities Ledger

- [x] **Upgrade-01 to Upgrade-10:** Foundation APIs, streaming, thinking models, context editing, batch execution.
- [x] **Upgrade-11:** SOC 2 / ISO 27001 compliance evidence catalog and audit framework.
- [x] **Upgrade-12:** Stable `/api/v1/` public REST API, idempotency keys, rate limiting, Python & TypeScript SDKs.
- [x] **Upgrade-13:** Zero-cost offline core engine, local model routing (Ollama/vLLM), local object storage.
- [x] **Upgrade-14 to Upgrade-18:** Local AI stack, model preflight, quality engineering loops, production runtimes.
- [x] **Upgrade-19:** Project bootstrap planner, automated RAG index ingestion, readiness reports.
- [x] **Upgrade-20:** Autonomous engineering loop with baseline vs post-edit validation delta tracking.
- [x] **Upgrade-21:** Durable SQLite & PostgreSQL engineering store with atomic checkpoints and state snapshots.
- [x] **Upgrade-22:** Multi-tenant portfolio scheduler, campaign execution, and worker fleet orchestration.
- [x] **Upgrade-23:** Maintenance intelligence service, proactive issue detection, self-repair workflows.
- [x] **Upgrade-24:** Bounded continuous upgrade/update/feature/repair meta-loop with priority ordering, idempotent discovery, retries, regression guard, rollback hook, and checkpoints.
- [x] **v1.40.0 Refactoring:** Clean Architecture & DDD `src/zcoder` migration with full backward compatibility.

---

## 6. Execution Roadmap & Next Milestones

```text
 Milestone 1: Core Clean Architecture & Test Green Baseline   [ COMPLETED - 807/807 PASS ]
 Milestone 2: Durability & Subprocess Import Alignment        [ COMPLETED ]
 Milestone 3: Release Gate Path & Verification Alignment      [ COMPLETED ]
 Milestone 4: Continuous Upgrade Meta-Loop (Upgrade-24)       [ IMPLEMENTED / CI VERIFY ]
 Milestone 5: CI/CD Hosted Runner Unblocking & Gates Check    [ IN PROGRESS / PENDING HOSTED CI ]
 Milestone 6: Standalone Binary & Container Packaging Verify  [ READY FOR STAGING ]
 Milestone 7: Wire Upgrade-24 to live Upgrade-20/GitHub adapters [ NEXT ]
```

### 6.1 Action Items

1. **Continuous Validation:**
   - Execute focused Upgrade-24 tests and the full `pytest` suite before merge.
   - Maintain zero newly introduced regressions relative to the 807-test pre-change baseline.
   - Maintain `__test__ = False` on non-test classes with `Test*` naming prefix to prevent collection warnings.
2. **Subprocess Execution Invariant:**
   - Ensure all scripts or tests invoking subprocesses pass `PYTHONPATH` with both `<repo_root>/src` and `<repo_root>`.
3. **Hosted CI Execution:**
   - Monitor GitHub Actions billing and hosted runners to unblock hosted release gate verification.
4. **Upgrade-24 Runtime Wiring:**
   - Feed Upgrade-23 maintenance recommendations through `work_from_maintenance_recommendation()`.
   - Adapt one `UpgradeWorkItem` at a time into Upgrade-20 `EngineeringTask` execution.
   - Convert Upgrade-20 baseline/post-edit validation delta into Upgrade-24 `ValidationResult`.
   - Persist Upgrade-24 checkpoints through the durable engineering/portfolio store boundary.
   - Keep automatic push/PR behavior governed by the existing Upgrade-20 push policy and approval controls.
