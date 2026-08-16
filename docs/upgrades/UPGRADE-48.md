# Upgrade-48 — Bounded Messaging Output Mode

## Goal

Prepare the Upgrade-46 provider-neutral messaging boundary for migration of one existing interactive caller without regressing the caller's real-time streaming behavior.

## Contract

`run_messaging_turn_once()` and `run_claude_messaging_turn_once()` now accept an explicit `verbose` flag. The default remains `False`, preserving the quiet application-service boundary established by Upgrade-47. When an interactive caller explicitly passes `verbose=True`, that value is forwarded exactly once to the existing provider capability; the service still performs exactly one capability call and does not add output loops of its own.

## Upgrade-20/24 invariants

This slice adds no polling, retry loop, sleep, scheduler, daemon, recursive agent execution, automatic tool execution, or expanded iteration budget. It does not execute returned tool calls. It does not change security gates or validation thresholds.

## Regression guards

Focused service and Claude-adapter tests prove:

- the existing default remains `verbose=False`;
- `verbose=True` is forwarded exactly once;
- one service invocation still performs exactly one provider-capability call;
- tool calls remain returned as data only and are not executed.

## Compatibility

Existing application callers require no changes because the new argument defaults to quiet mode. `StreamCoder.stream_with_tools()` and the existing CLI entry point remain unchanged in this slice.

## Next boundary

Migrate exactly one existing interactive CLI caller to `run_claude_messaging_turn_once(..., verbose=True)` while preserving its banner, real-time text streaming, tool-call summary, model/system/tool forwarding, and returned result. Keep that caller migration isolated in its own regression-tested vertical slice.
