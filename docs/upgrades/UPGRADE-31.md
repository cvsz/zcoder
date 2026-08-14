# UPGRADE-31: PostgreSQL Monotonic Fencing

## Goal

Prevent a stale continuous-engineering runner from persisting durable upgrade state after ownership has moved to a newer PostgreSQL-backed runner.

Upgrade-30 provides distributed advisory-lock exclusivity. Upgrade-31 adds the missing stale-writer boundary: a monotonic `fence_generation` stored on the existing upgrade-ledger control row in `engineering_tasks`.

## Design

`PostgresUpgradeFence` uses the existing `engineering_tasks` table and the versioned `zcoder_upgrade_ledger` control metadata envelope.

Token acquisition:

1. lock the namespace control row with `SELECT ... FOR UPDATE`;
2. create generation `1` when the control row does not exist, or increment the existing generation;
3. persist the new generation before returning `UpgradeFenceToken`.

Fenced task write:

1. lock the same control row with `SELECT ... FOR UPDATE`;
2. validate namespace, control identity, schema, and exact generation;
3. perform the task upsert in the same database transaction;
4. reject the write with `StalePostgresUpgradeFenceError` when a newer generation exists.

Control/checkpoint writes preserve the active `fence_generation` so normal ledger checkpoint metadata cannot erase ownership state.

## Safety invariants

- no new database schema or table;
- generation is monotonic per ledger control row;
- stale generations cannot persist work after a newer generation is acquired;
- validation and task mutation occur under the same row lock and transaction;
- malformed control metadata, namespace mismatch, invalid generation, or missing control state fails closed;
- ledger carrier records remain non-`CREATED` and cannot be claimed by normal Upgrade-20 workers;
- PostgreSQL CLI/backend remains disabled until the fenced primitive is composed with the Upgrade-28 ledger and Upgrade-30 lease.

## Verification

`tests/integration/test_upgrade_postgres_fence_live.py` runs against hosted `DATABASE_URL` when reachable and proves:

- generation increases from 1 to 2;
- generation 1 can write before ownership changes;
- generation 1 is rejected after generation 2 exists and its stale task is absent from PostgreSQL;
- the current generation can persist work;
- checkpoint/control writes preserve `fence_generation`;
- a token becomes invalid immediately after a newer generation is acquired.

## Next slice

Compose `EngineeringStoreUpgradeLedger` with a fenced EngineeringStore adapter and `PostgresAdvisoryRunLease`, then add end-to-end PostgreSQL restart/concurrency tests. Only after that composition is green should `--state-backend postgres` be exposed.
