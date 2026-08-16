# Upgrade-42 — PostgreSQL Store Integration Boundary

## Goal

Move Upgrade-41 toward the production `PostgresControlPlaneStore.process_outbox()` boundary without changing the large legacy store in the same slice. Establish and regression-test a compatibility adapter first so the final method wiring is mechanical and reviewable.

## Contract

`process_postgres_store_outbox()` preserves the existing PostgreSQL store defaults (`max_attempts=5`, `backoff_base=2.0`) and adds the Upgrade-41 finite batch default (`max_messages=50`). It delegates exactly once to `process_postgres_outbox_once()`.

`backoff_base` remains accepted for source compatibility but does not create sleeping or retry behavior. Retry cadence and backoff remain external.

## Bounded-execution invariants

This slice adds no polling, scheduling, sleep, daemon, or internal retry loop. A call delegates to exactly one bounded Upgrade-41 processor invocation. Upgrade-20 remains execution authority and Upgrade-24 remains authoritative for bounded iteration, regression, and no-progress policy.

## Regression guards

Unit tests verify legacy defaults, explicit finite budget forwarding, and that processor failures surface after exactly one delegation rather than being retried internally.

## Next boundary

After this compatibility adapter is green, wire `PostgresControlPlaneStore.process_outbox()` to this adapter with a minimal method-body change, then add live PostgreSQL concurrent-worker coverage proving `FOR UPDATE SKIP LOCKED` prevents duplicate delivery.
