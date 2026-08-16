# Upgrade-47 — Quiet Messaging Capability Boundary

## Goal

Repair the Upgrade-46 provider-neutral messaging seam before migrating a real caller. `run_messaging_turn_once()` deliberately invokes `StreamCoder.stream_with_tools(..., verbose=False)`, so that capability must not emit text or formatting to stdout/stderr when used as an application service dependency.

## Contract

`StreamCoder.stream_with_tools(..., verbose=False)` returns the same text, tool-call, stop-reason, and stop-details data as before but emits no text-delta or final-newline output. `verbose=True` preserves the existing CLI streaming behavior.

## Upgrade-20/24 invariants

This slice adds no polling, retry loop, sleep, scheduler, daemon, recursive agent execution, automatic tool execution, or expanded iteration budget. It only makes the existing verbosity flag authoritative at the provider capability boundary.

## Regression guards

Focused unit coverage proves that quiet mode returns the complete messaging result with empty stdout/stderr and that verbose mode still emits the legacy text stream plus final newline.

## Compatibility

`StreamCoder.stream()` is unchanged. `cmd_stream_tools()` continues to use the default `verbose=True`, so existing interactive CLI output remains unchanged. The provider-neutral Upgrade-46 adapter continues to pass `verbose=False` and now has a side-effect-free output boundary.

## Next boundary

After this repair is green, migrate exactly one existing CLI or web caller to `run_claude_messaging_turn_once()` while preserving that caller's externally visible behavior. Keep provider-specific options on their existing path until the adapter explicitly supports them.
