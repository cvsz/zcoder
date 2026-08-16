# Upgrade-43 — PostgreSQL Outbox Concurrency Evidence

## Goal

Add live regression evidence at the production PostgreSQL store boundary before replacing the legacy `PostgresControlPlaneStore.process_outbox()` body with the Upgrade-42 compatibility adapter.

## Contract

The live integration test creates a finite 12-message outbox backlog, starts three one-shot worker processes, and verifies every message is delivered exactly once. The test uses the production store method and therefore exercises its `FOR UPDATE SKIP LOCKED` claim behavior against real PostgreSQL.

## Bounded-execution invariants

Each worker invokes `process_outbox()` exactly once. The test uses a finite backlog, a finite worker count, `max_attempts=2`, and a 10-second process join timeout. It adds no production polling, scheduling, retry loop, sleep/backoff policy, or daemon behavior. Upgrade-20 remains execution authority and Upgrade-24 remains authoritative for bounded iteration, regression, and no-progress policy.

## Regression guards

The test fails on worker errors, timeout, missing delivery, duplicate delivery, or any final status other than `DELIVERED` for the test backlog. It skips only when the repository's real PostgreSQL integration service is unavailable, matching the existing live PostgreSQL suite.

## Next boundary

After this concurrency evidence is green, replace only the body of `PostgresControlPlaneStore.process_outbox()` with one delegation to `process_postgres_store_outbox()`, preserving the existing public signature/defaults. Re-run this live regression after the delegation to prove the mechanical integration retains no-duplicate delivery.
