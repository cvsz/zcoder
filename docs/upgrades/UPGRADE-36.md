# UPGRADE-36: Maintenance Campaign Worker/Outbox Adapter

## Goal

Move the Upgrade-35 scheduler-friendly result contract across the repository's existing durable outbox boundary without adding an internal scheduler, daemon, retry loop, or second execution authority.

This slice connects `MaintenanceCampaignRunResult` to the existing control-plane `enqueue_outbox()` contract. It does not change campaign execution semantics.

## One-shot worker contract

`run_maintenance_campaign_worker_once()`:

1. calls `run_maintenance_campaign_once()` exactly once;
2. builds one versioned, secret-free campaign summary;
3. enqueues one `maintenance.campaign.summary` outbox message;
4. returns the original `MaintenanceCampaignRunResult` plus the outbox message ID.

Scheduling cadence remains external. The adapter has no recurrence loop and no automatic delivery retry.

## Durable summary contract

The outbox payload contains only:

- schema version;
- a campaign-scoped idempotency key;
- the Upgrade-35 exit code;
- `MaintenanceCampaignReport.to_dict()`.

It does not include maintenance recommendation evidence, provider credentials, repository snapshots, API keys, or `DATABASE_URL`.

The campaign-scoped idempotency key is exposed for downstream delivery deduplication. This slice does not change the existing outbox schema or silently introduce a second deduplication store.

## Failure semantics

If campaign execution halts under Upgrade-24 bounds, exit code `2` is preserved in the durable summary.

If outbox enqueue fails:

- the exception is surfaced to the external worker/scheduler;
- the adapter does not retry the campaign;
- the adapter does not retry the enqueue;
- Upgrade-20/24 engineering truth remains in the existing ledger/state backend;
- recurrence/recovery policy remains external.

This fail-visible behavior prevents an unbounded hidden retry loop and avoids treating telemetry/distribution failure as a new engineering execution authority.

## Verification

`tests/unit/test_maintenance_campaign_worker.py` verifies:

- versioned and secret-free summary serialization;
- deterministic campaign-scoped idempotency key;
- exactly one campaign invocation per adapter call;
- exactly one outbox enqueue per adapter call;
- preservation of bounded halted exit code;
- enqueue failure is surfaced with no internal retry.

Full hosted Ruff, Black, Bandit, Python 3.9-3.12, Docker, CodeQL, Dependency Review, Helm, SDK/TypeScript, and Release Gate workflows remain required.

## Safety invariants

- Upgrade-20 remains the only task execution authority;
- Upgrade-24 bounded iteration/retry/regression/no-progress policy remains authoritative;
- Upgrade-33 PostgreSQL advisory exclusivity/fencing remains unchanged;
- Upgrade-34/35 campaign execution remains finite and one-shot;
- no internal scheduler or daemon loop;
- no automatic outbox retry loop;
- no second persistence or observability stack;
- no secrets in durable campaign summaries;
- no test, coverage, CI, push-policy, or security gate is weakened.

## Next slice

Add a concrete external worker entrypoint that supplies the existing `ControlPlaneStore` (or PostgreSQL-equivalent durable outbox implementation), then add delivery-consumer idempotency using the exposed campaign idempotency key. Keep cadence and retry budgets owned by the external scheduler/worker policy.
