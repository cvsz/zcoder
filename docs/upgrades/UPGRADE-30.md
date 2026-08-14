# UPGRADE-30: PostgreSQL Advisory Run Lease Primitive

## Goal

Add a cross-process and cross-host mutual-exclusion primitive for continuous engineering runners without incorrectly reusing the filesystem-only lease used by JSON and SQLite backends.

## Design

Upgrade-30 introduces:

- a generic `RunLease` protocol alongside the existing filesystem `UpgradeRunLease`;
- `PostgresAdvisoryRunLease`, which holds one PostgreSQL session advisory lock for the entire lease lifetime;
- deterministic signed BIGINT lock keys derived from a non-empty namespace;
- fail-closed acquisition, contention, unlock, and connection-return handling.

The PostgreSQL lease accepts a connection-scope factory. The scope must keep one database connection checked out from acquire through release. The lock and unlock statements therefore execute on the same PostgreSQL session. If that session terminates, PostgreSQL releases its advisory lock automatically.

## Safety boundary

This upgrade provides distributed exclusivity only. It is not yet a durable fencing token. A runner whose database session dies while its process continues could become a stale writer after another runner acquires the advisory lock.

For that reason Upgrade-30 does **not** expose the PostgreSQL continuous-engineering backend in the CLI. PostgreSQL backend wiring requires fence-aware durable ledger mutations in a subsequent upgrade.

Existing JSON/SQLite lease behavior, Upgrade-20 execution authority, Upgrade-24 budgets, local-only push default, and all security gates are unchanged.

## Verification

`tests/unit/test_upgrade_postgres_lease.py` covers deterministic key derivation, same-session hold/release, contention, acquire errors, lost-lock release, connection-return failures, and context-manager cleanup.

`tests/integration/test_upgrade_postgres_lease_live.py` uses hosted `DATABASE_URL` when available and verifies that two independent PostgreSQL sessions cannot hold the same advisory run lease concurrently and that the second session can acquire after release.

## Next slice

Add a monotonic fencing token at the EngineeringStore-backed upgrade ledger mutation boundary. Every PostgreSQL ledger mutation must validate the current fence so stale runners cannot persist checkpoints or terminal state after losing ownership. Only after that invariant is proven should the PostgreSQL backend be exposed to `ContinuousEngineeringPipeline` and the CLI.
