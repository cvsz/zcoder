# Upgrade-44 — Bounded Core Messaging Service Boundary

## Goal

Start Phase B / Core Messaging from the v1.45 execution plan against the current repository architecture without restoring obsolete snapshot code.

## Contract

`run_messaging_turn_once()` performs exactly one call to an injected messaging capability and returns provider-neutral turn data. Tool calls are returned as data only; the service does not execute them.

Malformed or truncated fine-grained tool input remains preserved by the provider capability (`input_raw` with `input=None`) so downstream policy/tool boundaries can validate it fail-closed.

## Upgrade-20/24 invariants

This slice adds no polling, provider retry loop, sleep, scheduler, daemon, recursive agent loop, or automatic tool execution. One invocation performs one provider-capability call. Upgrade-20 remains execution authority and Upgrade-24 remains authoritative for bounded iteration, retry, regression, and no-progress policy.

## Regression guards

Unit coverage proves exactly-one delegation, result preservation including `max_tokens`/raw malformed tool input, and that returned tool calls are not executed by the messaging service.

## Next boundary

After this slice is green, adapt the existing Claude streaming capability to the service boundary at one caller while retaining the legacy entry point. Separately, complete the already-evidenced PostgreSQL store delegation from Upgrade-43 when the production store body can be changed mechanically without widening the slice.
