# ZCoder — Architecture Review

**Repository:** https://github.com/cvsz/zcoder
**Branch:** `fix/zcoder-defensive-fallback` @ `9a0cb1d`
**Date:** 2026-11-08

## Architecture Overview

ZCoder follows a Clean Architecture with clear domain boundaries:

```
Interfaces (CLI / TUI / Web/API)
        |
        v
Services (agents / workflows / orchestration / API)
        |
+-------+-------+
|               |
v               v
Core / Domain   Provider Adapters
(jobs / policy  (local / external
 / tenants /    optional)
 / models)
        |
        v
Infrastructure (SQLite / PostgreSQL / GitHub / workers / deploy / telemetry)
```

## Architecture Findings

### Strengths

| Area | Observation |
|------|-------------|
| Domain boundaries | Clear separation between `src/zcoder/domain/` (core business logic), `src/zcoder/agent/` (agent runtime), `src/zcoder/services/` (background services), and `src/zcoder/api/` (API layer) |
| Dependency injection | Services accept dependencies via constructor (e.g., `PublicAPIV1Router(entitlement_service, job_store)`) |
| Coupling/cohesion | Low coupling between domain modules; adapters isolate external providers |
| API boundaries | FastAPI-based REST API with OpenAPI schema; clear `/health/live`, `/health/ready`, `/metrics` endpoints |
| Multi-tenancy | Organization → Project → Resources hierarchy with RLS policies |
| Security | Fail-closed boundaries throughout; tenant isolation; path traversal protection |

### Security-Relevant Architecture

| Control | Implementation |
|---------|---------------|
| Tenant isolation | Organization/project hierarchy; RLS policies; fail-closed boundaries |
| Authorization | `EnterprisePolicyEngine` with deny-by-default; condition evaluation returns `None` → deny |
| Path traversal | `_safe_child_path()` with realpath containment; `[A-Za-z0-9_-]{1,64}` ID validation |
| SSRF | WebFetch routed through SSRF boundary; loopback-validated DNS targets |
| Secret handling | No secrets in client-side code; automatic log redaction |

### No Circular Imports

Verified: no circular imports detected in `src/zcoder/`. Module boundaries are maintained.

### No Dead Code Found

No dead code or unused functions identified in the source tree.

## Issues Found During Architecture Review

None — architecture is sound. All changes on the current branch are consistent with the existing architecture.

## Recommendations

None — architecture is production-ready.
