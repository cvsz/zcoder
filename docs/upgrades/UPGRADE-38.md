# Upgrade-38 — Bounded Generic Outbox Processing

## Objective

Bound one generic outbox-processing invocation independently of backlog size while preserving the existing API and delivery semantics.

## Vertical slice

`ControlPlaneStore.process_outbox()` now accepts optional `max_messages`.

- `None` preserves the historical all-pending behavior for existing callers.
- A positive integer selects at most that many pending messages, oldest first.
- Zero and negative budgets fail closed with `ValueError`.
- The processor still performs one handler attempt per selected message.
- No polling, scheduler, retry loop, backoff, or daemon is introduced.

This follows the Upgrade-20/24 convention: orchestration cadence stays external and each bounded worker invocation has an explicit finite work budget.

## Regression guards

Tests retain the legacy unbounded-call compatibility path and add coverage proving that a three-message backlog is consumed as bounded `2 + 1` batches. Invalid non-positive budgets are rejected before any delivery work begins.

## Explicitly deferred

Poison-message policy is intentionally a separate slice. A follow-up should add a bounded `max_attempts` policy and terminal `DEAD` transition with compatibility and persistence coverage rather than combining retry semantics with this batch-budget change.
