# Upgrade-41 — PostgreSQL Bounded Outbox Parity

## Goal

Close the production outbox gap after Upgrade-38/39/40 by adding a one-shot PostgreSQL processor with explicit finite batch and failure budgets while preserving Upgrade-20/24 bounded execution conventions.

## Contract

`process_postgres_outbox_once()`:

- requires positive `max_messages` and `max_attempts` budgets;
- claims at most `max_messages` oldest eligible `PENDING` rows;
- uses `FOR UPDATE SKIP LOCKED` so concurrent workers can partition work without blocking on claimed rows;
- invokes the downstream handler at most once per selected message per invocation;
- reuses Upgrade-39 `transition_after_failure()` for deterministic `PENDING -> DEAD` exhaustion;
- marks successful messages `DELIVERED` in the same transaction boundary;
- rejects invalid budgets before database work.

## Bounded-execution invariants

This slice adds no polling, scheduling, sleep, backoff, daemon, or internal retry loop. External worker orchestration remains responsible for cadence and retry timing. Upgrade-20 remains execution authority and Upgrade-24 remains authoritative for bounded iteration, regression, and no-progress policy.

## Regression guards

Unit tests verify finite oldest-first selection, SQL `FOR UPDATE SKIP LOCKED`, exactly one handler call for a failing message, terminal exhaustion through the shared policy, JSON payload compatibility, and validation before I/O.

## Deliberate next boundary

After this adapter is green, integrate it into `PostgresControlPlaneStore.process_outbox()` while preserving the existing public signature/defaults. A separate live PostgreSQL slice should then prove concurrent workers do not double-deliver selected rows.
