# Upgrade-39 — Bounded Outbox Poison-Message Policy

## Goal

Establish the deterministic failure-transition contract needed to prevent poison outbox messages from remaining retryable forever, without introducing an internal retry loop or changing the existing processor in the same slice.

## Safety contract

- Upgrade-20 remains execution authority.
- Upgrade-24 remains authoritative for bounded execution and regression/no-progress guards.
- One policy call represents exactly one failed delivery attempt; it never retries, sleeps, polls, schedules, or performs I/O.
- `max_attempts` must be a positive finite integer.
- A message remains `PENDING` below the budget and becomes terminal `DEAD` exactly when the incremented attempt count reaches the budget.
- Invalid persisted attempt counts and invalid budgets fail closed.

## Compatibility

This slice deliberately does not change `ControlPlaneStore.process_outbox()`. It introduces the tested transition primitive first so the persistence integration can be a separate, reviewable vertical slice with explicit compatibility coverage.

## Regression guards

Unit coverage proves below-budget, exact-budget, already-exhausted, and invalid-input transitions. Existing CI, CodeQL, dependency review, release, formatting, security, and coverage gates remain unchanged.

## Next slice

Integrate `transition_after_failure()` into `ControlPlaneStore.process_outbox()` behind an explicit positive `max_attempts` argument while preserving the current behavior when that argument is omitted. Persist both `attempts` and `status` atomically on handler failure and add SQLite integration coverage proving a poison message reaches `DEAD` after a finite number of externally scheduled invocations.
