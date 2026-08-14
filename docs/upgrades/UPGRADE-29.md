# UPGRADE-29: SQLite EngineeringStore Backend Wiring

## Goal

Make the Upgrade-28 EngineeringStore ledger directly usable by the continuous engineering pipeline and CLI while preserving the existing JSON backend as the compatibility default.

## Changes

- `ContinuousEngineeringPipeline` now consumes the generic `UpgradeLedger` contract.
- A ledger without a local filesystem path must receive an explicit `UpgradeRunLease`; construction fails closed otherwise.
- `build_sqlite_store_pipeline()` composes the existing `SQLiteEngineeringStore`, `EngineeringStoreUpgradeLedger`, Upgrade-20 executor, and a same-host sidecar run lease.
- CLI adds `--state-backend {json,sqlite}`, `--engineering-db`, and `--ledger-namespace`.
- JSON remains the default state backend and retains its existing state-file behavior.

## Safety boundary

SQLite locking plus the sidecar run lease is a same-host deployment boundary. Upgrade-29 intentionally does not expose PostgreSQL as a fleet backend because a filesystem lease cannot provide multi-host exclusivity. PostgreSQL production fleet execution requires a distributed lease/fencing mechanism in a separate upgrade.

Push policy, Upgrade-20 execution authority, Upgrade-24 iteration/retry/regression/no-progress budgets, and Upgrade-28 metadata validation remain unchanged.

## Examples

Default JSON compatibility mode:

```bash
python -m zcoder.services.continuous_engineering --repository . --feature "Implement health endpoint"
```

SQLite EngineeringStore mode:

```bash
python -m zcoder.services.continuous_engineering \
  --repository . \
  --state-backend sqlite \
  --engineering-db .zcoder/engineering.db \
  --ledger-namespace local-fleet \
  --feature "Implement health endpoint"
```

## Verification

`tests/integration/test_continuous_engineering_sqlite_backend.py` covers:

- fail-closed construction for a pathless ledger without an explicit lease;
- SQLite builder composition and sidecar lease placement;
- restart-safe completed-work deduplication through SQLite;
- JSON compatibility as the CLI default;
- SQLite backend argument parsing;
- main CLI routing to the SQLite builder.

Hosted CI remains authoritative for Ruff, Black, Bandit, Python 3.9-3.12, Docker smoke, CodeQL, Dependency Review, Helm, SDK/TypeScript, and Release Gate.

## Next slice

Add a PostgreSQL distributed run lease with fencing semantics and live multi-process tests before allowing `PostgresEngineeringStore` to back continuous fleet execution.
