# Upgrade-46 — Claude Messaging Caller Adapter

## Goal

Advance the Upgrade-44 next boundary by adapting the existing Claude streaming capability to the provider-neutral messaging service through one deliberately small caller adapter while retaining the legacy `StreamCoder.stream_with_tools()` entry point.

## Contract

`run_claude_messaging_turn_once()` constructs one `StreamCoder` capability and delegates exactly once to `run_messaging_turn_once()`. The adapter forwards the caller's model, token budget, tools, and system prompt and returns the provider-neutral `MessagingTurnResult` unchanged.

Tool calls remain data only. This adapter never executes them.

## Upgrade-20/24 invariants

This slice adds no polling, provider retry loop, sleep, scheduler, daemon, recursive agent loop, automatic tool execution, or expanded retry cadence. One invocation constructs one capability and performs one service-boundary delegation. Upgrade-20 remains execution authority and Upgrade-24 remains authoritative for bounded iteration, retry, regression, and no-progress policy.

## Regression guards

Unit coverage proves exactly-one capability construction, exactly-one provider-capability call through the service seam, exact forwarding of model/token/tool/system inputs, and non-execution of returned tool calls.

## Compatibility

The existing `StreamCoder.stream_with_tools()` API is unchanged. This slice introduces an opt-in caller seam only; no legacy caller is removed or redirected yet.

## Next boundary

After this adapter is green, migrate one existing CLI or web caller to `run_claude_messaging_turn_once()` while preserving its current externally visible behavior, then rerun the same bounded/non-execution guards plus that caller's regression suite.
