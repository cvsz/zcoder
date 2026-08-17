# Upgrade-49 — Bounded `--stream-tools` Caller Migration

## Goal

Complete the Upgrade-48 next boundary by migrating exactly one existing interactive CLI entry point, `cmd_stream_tools()`, through the provider-neutral messaging service without changing the CLI dispatch or user-visible streaming contract.

## Contract

`cmd_stream_tools()` now delegates exactly once to `run_claude_messaging_turn_once(..., verbose=True)` instead of constructing `StreamCoder` and invoking `stream_with_tools()` directly.

The CLI continues to preserve:

- the existing streaming banner;
- real-time provider text/tool-input output via `verbose=True`;
- prompt, model, system, and tool-definition forwarding;
- the existing tool-call summary;
- the legacy dict-shaped return value with `text`, `tool_calls`, `stop_reason`, and `stop_details`.

Returned tool calls remain data only. The CLI entry point does not execute them.

## Upgrade-20/24 invariants

This slice migrates one caller only. It adds no polling, retry loop, sleep, scheduler, daemon, recursive agent execution, automatic tool execution, or expanded iteration budget. No validation threshold, test gate, security gate, or release gate is weakened.

## Regression guards

Focused tests prove:

- one `cmd_stream_tools()` invocation performs exactly one service-adapter delegation;
- API key, prompt, model, system, tools, and `verbose=True` are forwarded exactly;
- the existing banner and tool-call summary remain present;
- the legacy result shape is preserved;
- returned tool-call data is never executed by this caller.

## Compatibility

`main.py` remains unchanged and continues importing `cmd_stream_tools` through the existing `claude_stream` compatibility surface. `StreamCoder.stream_with_tools()` remains available for other callers.

## Next boundary

After this slice is merged and the new `main` baseline is verified, inventory remaining direct application/CLI callers of `StreamCoder.stream_with_tools()` and migrate at most one additional caller in a separate vertical slice. If no application caller remains, prefer a different independently verifiable Upgrade-24 work item rather than widening this migration.
