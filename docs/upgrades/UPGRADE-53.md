# Upgrade-53 — Service / Infrastructure Dependency Boundary

## Goal

Advance one bounded `ROADMAP-NEXT.md` P2.1 architecture item by making the application-service dependency direction executable: canonical `src/zcoder/services` modules must not import concrete `zcoder.infrastructure` adapters.

## Scope

- extend the existing AST-based architecture boundary guard;
- scan all Python modules under `src/zcoder/services`;
- fail deterministically when a service imports `zcoder.infrastructure` or a submodule below it;
- reuse the same guard already protecting `domain` and `core` rather than introducing a second architecture-test framework.

The strict guard exposed three pre-existing violations. Upgrade-53 repairs them one dependency boundary at a time instead of allowlisting them.

### Maintenance observability repair

The first repair moves the concrete OpenTelemetry maintenance-event sink out of `services` and into `infrastructure.observability`, while retaining `MaintenanceCampaignEvent` and `MaintenanceCampaignEventSink` as service-owned contracts. The service-level CLI now accepts an injected event sink, and `interfaces.cli.maintenance_campaign` is the composition root that constructs the OTEL sink and passes it inward exactly once.

This preserves the one-shot campaign execution contract and prevents the service layer from knowing about OpenTelemetry metrics/tracer implementations.

### SQLite composition boundary preparation

The next bounded slice introduces `interfaces.cli.continuous_engineering.build_sqlite_store_pipeline()` as the outward composition root for the concrete `SQLiteEngineeringStore`. It preserves the existing same-host lease path convention, ledger namespace, Upgrade-20 executor construction, loop policy, retry-blocked flag, work sources, GitHub orchestrator, and bounded CI-repair budget. Focused unit coverage proves one store construction and exact argument forwarding, including an explicit lease path.

This slice deliberately does not yet remove the legacy SQLite construction from `services.continuous_engineering`; the strict architecture guard therefore continues to expose that dependency until the following isolated routing/removal slice. The PostgreSQL dependency is also intentionally untouched.

## Upgrade-20/24 boundedness

The architecture rule and each repair remain bounded. They add no polling, retries, sleeps, scheduler or daemon behavior, recursive execution, automatic tool execution, concurrency-budget expansion, authentication change, authorization change, or persistence semantics change.

They do not weaken Ruff, Black, pytest, coverage, Bandit, CodeQL, dependency review, Release Gate, Helm, or SDK/TypeScript checks. No architecture violation is allowlisted, dynamically hidden, skipped, or excluded.

## Remaining violations

After the maintenance-observability repair and SQLite composition-root preparation, the strict guard is expected to continue exposing the two concrete store dependencies in `services/continuous_engineering.py`:

- `zcoder.infrastructure.stores.sqlite_engineering`
- `zcoder.infrastructure.stores.postgres_engineering`

Those remain separate bounded repair slices and keep PR #47 blocked until repaired.

## Deliberately out of scope

- interface-layer dependency rules;
- compatibility-module cleanup;
- removing the legacy SQLite service import in the same preparation slice;
- repairing the PostgreSQL boundary in this slice;
- broader service/package restructuring.

## Verification contract

Merge only after the architecture guard and all fresh required hosted checks pass on the exact PR head SHA. If the guard exposes a real service-to-infrastructure dependency, repair one concrete violation only rather than weakening the guard.

## Next boundary

Route the existing SQLite continuous-engineering caller through the new interface composition root and remove the legacy `services -> infrastructure.stores.sqlite_engineering` import while preserving CLI behavior and same-host lease semantics. Keep the PostgreSQL dependency visible for the following bounded slice.
