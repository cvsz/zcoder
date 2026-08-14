# UPGRADE-33: Production PostgreSQL Continuous Backend

## Goal

Expose the fenced PostgreSQL runtime from Upgrades 28, 30, 31, and 32 as a production continuous-engineering state backend with explicit CLI selection and deterministic resource cleanup.

## Runtime composition

`build_postgres_store_pipeline()` creates:

1. `PostgresEngineeringStore` and initializes the existing engineering schema;
2. `EngineeringStoreUpgradeLedger` probe for the deterministic namespace control ID;
3. `PostgresUpgradeFence` on the store's public connection scope;
4. `PostgresAdvisoryRunLease` for cross-host exclusivity;
5. `PostgresFencedRunLease` so advisory ownership exists before a fence generation is issued;
6. `FencedUpgradeEngineeringStore` so ledger writes require the active fence token;
7. the final `EngineeringStoreUpgradeLedger` and existing Upgrade-20 executor;
8. `ContinuousEngineeringPipeline` with the composed lease and store cleanup callback.

No new database table or task engine is introduced.

## CLI

The state backend choices are now:

- `json` — compatibility/default local JSON ledger;
- `sqlite` — same-host EngineeringStore backend with filesystem run lease;
- `postgres` — multi-host EngineeringStore backend with PostgreSQL advisory exclusivity and monotonic fencing.

PostgreSQL mode reads the database credential from `DATABASE_URL`. The URL is not added to the structured run report or printed by the CLI. PostgreSQL selection fails closed when `DATABASE_URL` is absent.

Example:

```bash
DATABASE_URL='postgresql://...' \
python -m zcoder.services.continuous_engineering \
  --repository . \
  --state-backend postgres \
  --ledger-namespace production-fleet \
  --feature 'Implement provider health endpoint'
```

JSON remains the default, and automatic push remains local-only unless explicitly opted in.

## Resource lifecycle

`ContinuousEngineeringPipeline` now supports idempotent `close()` and context-manager usage. A closed pipeline cannot be run again. The PostgreSQL builder installs the store pool close operation as its cleanup callback and also closes the pool if builder construction fails after the store was opened.

The CLI runs every backend inside the pipeline context manager so cleanup executes on success and exception paths.

## Verification

`tests/unit/test_continuous_engineering_postgres_backend.py` covers:

- JSON remains the default while PostgreSQL is explicitly selectable;
- PostgreSQL mode requires `DATABASE_URL`;
- the secret reaches the builder but is not printed in CLI output;
- CLI uses the pipeline resource context;
- close is idempotent and closed pipelines reject new runs;
- empty database URLs fail before store construction.

`tests/integration/test_continuous_engineering_postgres_backend_live.py` uses hosted `DATABASE_URL` when reachable and proves:

- a PostgreSQL-backed pipeline persists a successful work fingerprint;
- a fresh pipeline instance with the same namespace skips the completed fingerprint after restart;
- two pipeline instances using the same namespace cannot run concurrently;
- resource pools are closed explicitly after each live test.

## Safety invariants

- advisory ownership is acquired before the fence generation;
- every upgrade-ledger write uses the current fence token;
- stale writers remain rejected by Upgrade-31;
- no filesystem lock is used for PostgreSQL fleet exclusivity;
- database credentials are not included in run reports;
- JSON compatibility and SQLite same-host behavior remain intact;
- Upgrade-20 remains the task execution authority and Upgrade-24 remains the bounded queue policy;
- existing coverage, security, Docker, CodeQL, dependency, Helm, SDK, and release gates are unchanged.

## Next slice

Add a worker/service campaign entrypoint that invokes this PostgreSQL backend for scheduled Upgrade-23 maintenance recommendations, with structured metrics and bounded run summaries suitable for fleet operations.
