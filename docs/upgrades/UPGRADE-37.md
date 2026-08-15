# Upgrade-37 — Bounded Maintenance Summary Delivery

## Objective

Extend Upgrade-36 by adding a one-message downstream delivery boundary for durable maintenance campaign summaries without introducing scheduling, polling, retry loops, or new execution authority.

## Safety invariants

- Upgrade-20 remains the mutation/execution authority.
- Upgrade-24 remains authoritative for bounded iteration, retry, regression, and no-progress policy.
- Upgrade-36 remains responsible only for one campaign plus one durable enqueue.
- Upgrade-37 processes one supplied outbox message per invocation.
- Unknown actions, unsupported schemas, malformed identity, and malformed exit codes fail closed before downstream delivery.
- The deterministic campaign idempotency key is passed explicitly to the downstream sink.
- Sink failures surface to the external worker; Upgrade-37 never retries internally.
- Existing CI, coverage, CodeQL, dependency review, and security gates are unchanged.

## Delivered slice

`zcoder.services.maintenance_campaign_delivery` provides `deliver_maintenance_campaign_summary_once()` and a typed result/error boundary. Regression tests prove exactly-one sink invocation, fail-closed validation, deterministic idempotency propagation, and no internal retry on downstream failure.

## Deliberately deferred

Generic outbox polling/batching, dead-letter policy, backoff, and durable downstream acknowledgement remain external. A subsequent slice should harden the shared outbox worker with explicit finite batch and max-attempt budgets after compatibility coverage is in place.
