# UPGRADE-32: Fenced PostgreSQL Upgrade Runtime Composition

## Goal

Compose the storage, exclusivity, and stale-writer safety primitives from Upgrades 28, 30, and 31 into one PostgreSQL runtime boundary before exposing PostgreSQL as a continuous-engineering backend.

## Composition

```text
PostgresFencedRunLease
  1. PostgresAdvisoryRunLease.acquire()
  2. PostgresUpgradeFence.acquire_token()
                |
                v
FencedUpgradeEngineeringStore
  save_task -> PostgresUpgradeFence.save_task(token)
                |
                v
EngineeringStoreUpgradeLedger
                |
                v
PostgresEngineeringStore
```

The advisory lease is always acquired before a fence generation is issued. If fence acquisition fails, advisory ownership is rolled back. The active token is unavailable before acquisition and immediately removed on release.

`FencedUpgradeEngineeringStore` routes the only mutation surface used by `EngineeringStoreUpgradeLedger` (`save_task`) through the fence. Attempt/checkpoint-table mutations fail closed instead of bypassing fencing. Read operations delegate to the existing PostgreSQL engineering store.

`PostgresEngineeringStore.connection_scope()` exposes the existing pooled transactional connection scope as an infrastructure boundary for advisory locking and fencing without reaching into `_get_conn()` from application services.

## Safety invariants

- distributed advisory exclusivity is acquired before fence generation advances;
- every upgrade-ledger task/control write requires the active fence token;
- stale generations are rejected by Upgrade-31 in the same transaction as the write;
- the token is inaccessible outside the composed lease lifetime;
- fence acquisition failure releases advisory ownership;
- non-fenced attempt/checkpoint-table mutation surfaces fail closed;
- no new database schema or duplicate task engine;
- PostgreSQL CLI/backend exposure remains a later slice until this composition passes hosted live tests.

## Verification

`tests/unit/test_upgrade_postgres_runtime.py` covers ordering, rollback, token lifetime, fenced save routing, fail-closed mutation surfaces, read delegation, and resource close.

`tests/integration/test_upgrade_postgres_runtime_live.py` uses hosted `DATABASE_URL` when reachable and proves end to end that:

- generation one can persist and complete an upgrade-ledger item;
- a second owner receives a newer generation;
- a stale generation cannot create a new ledger item through `EngineeringStoreUpgradeLedger`;
- the current generation can persist work;
- ledger mutation outside the active composed lease fails closed.

## Next slice

Add a production PostgreSQL pipeline builder and explicit CLI backend selection with proper store lifecycle cleanup. Only that verified builder should make `--state-backend postgres` available.
