# ZCoder Usage Metering & Quotas

## 1. Immutable Usage Ledger
Usage is tracked via an append-only event stream (`usage_ledger`):
- `tokens_in` / `tokens_out`: Token consumption per LLM inference call.
- `runtime_seconds`: Execution duration across sandbox workers.
- `job_execution`: Execution count by runtime mode.

Events are deduplicated via unique idempotency keys to prevent double-charging on network retries.

## 2. Quota Enforcement & Atomic Reservations
- Soft limits trigger automated webhook notifications (default 80%).
- Hard limits block new job claims atomically using PostgreSQL row-level locks to prevent concurrency overspend races.
