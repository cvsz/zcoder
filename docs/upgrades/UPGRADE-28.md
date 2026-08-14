# UPGRADE-28: EngineeringStore-Backed Upgrade Ledger

## Goal

Persist continuous upgrade state through the existing Upgrade-21 `EngineeringStore` boundary instead of adding another database schema.

## Design

`EngineeringStoreUpgradeLedger` stores Upgrade-24/25 records as namespaced `EngineeringTask.metadata`. It works with the existing EngineeringStore interface, including SQLite and PostgreSQL implementations.

Non-terminal ledger records use `TaskStatus.PAUSED`; successful records use `TaskStatus.SUCCEEDED`. Upgrade work state in versioned metadata remains authoritative.

## Guarantees

- deterministic record IDs from namespace plus work fingerprint;
- restart deduplication for completed work;
- blocked work remains blocked unless retry is explicit;
- namespaces can share one EngineeringStore without collisions;
- checkpoint history is bounded;
- malformed or unsupported namespaced records raise `UpgradeLedgerError`;
- Upgrade-20 remains the execution authority;
- Upgrade-24 retry, regression, and no-progress budgets are unchanged.

## Verification

`tests/integration/test_upgrade_store_ledger_sqlite.py` covers SQLite restart persistence, completed-work deduplication, explicit blocked retry, namespace isolation, bounded checkpoint history, non-`CREATED` carrier status, and fail-closed corrupt metadata handling.

Hosted CI remains the verification source for Ruff, Black, Bandit, Python 3.9-3.12, Docker smoke, CodeQL, Dependency Review, Helm, SDK/TypeScript, and Release Gate.

## Next slice

Wire `ContinuousEngineeringPipeline` to the generic ledger contract and expose explicit EngineeringStore-backed pipeline construction while retaining JSON as the compatibility default.
