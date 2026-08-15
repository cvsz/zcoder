# Upgrade-40 — Durable Bounded Outbox Exhaustion

## Goal

Integrate Upgrade-39's deterministic poison-message transition into the shared SQLite `ControlPlaneStore` outbox while preserving Upgrade-20/24 bounded-execution conventions and existing callers.

## Contract

`ControlPlaneStore.process_outbox()` accepts an optional positive `max_attempts` budget in addition to Upgrade-38's `max_messages` budget.

- `max_attempts=None` preserves historical failure behavior: one failed handler call increments `attempts` and leaves the message `PENDING`.
- An explicit positive `max_attempts` applies `transition_after_failure()` after exactly one failed handler invocation.
- A message remains `PENDING` below the budget and becomes terminal `DEAD` when the budget is exhausted.
- `DEAD` messages are excluded from subsequent invocations because processing selects only `PENDING` rows.
- Zero or negative attempt budgets fail closed before delivery work.

## Bounded-execution invariants

This upgrade does not add polling, scheduling, sleep, backoff, or an internal retry loop. One selected message receives at most one handler invocation during one `process_outbox()` call. External workers remain responsible for cadence and retry timing. Upgrade-20 remains execution authority and Upgrade-24 remains authoritative for bounded iteration/regression/no-progress policy.

## Regression guards

SQLite tests verify durable `PENDING -> DEAD` exhaustion across separate externally initiated processor invocations, terminal messages are not redelivered, legacy behavior remains unchanged when `max_attempts` is omitted, and invalid budgets are rejected.

## Deliberate next boundary

PostgreSQL parity and multi-worker atomic claiming are not changed in this slice. They require a separate transaction/locking review so this bounded persistence change remains independently verifiable.
