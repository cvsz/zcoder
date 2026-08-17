# Upgrade-52 — Canonical Package Circular-Import Guard

## Goal

Advance one bounded `ROADMAP-NEXT.md` P2.1 architecture item by encoding circular-import detection as an executable regression guard for the canonical `src/zcoder` package, then repair only the concrete cycle exposed by that guard.

## Scope

- statically parse Python modules under `src/zcoder` with `ast`;
- resolve canonical absolute imports and package-relative imports;
- build an internal module dependency graph;
- fail deterministically when that graph contains a cycle;
- report one concrete cycle path in the assertion message;
- repair the single discovered cycle between `zcoder.claude.capabilities.stream` and `zcoder.services.claude_messaging_adapter` by keeping `cmd_stream_tools()` on the generic bounded `run_messaging_turn_once()` service boundary instead of routing back through the Claude adapter that imports `StreamCoder`.

## Upgrade-20/24 boundedness

The repair remains one bounded caller-path change. It does not add polling, retries, sleeps, scheduler or daemon behavior, recursive execution, automatic tool execution, concurrency-budget expansion, authentication changes, authorization changes, or persistence changes.

The `--stream-tools` caller still constructs one `StreamCoder`, performs exactly one generic messaging-service call, requests `verbose=True` to preserve interactive streaming output, returns the same result shape, and never executes returned tool calls.

It does not weaken Ruff, Black, pytest, coverage, Bandit, CodeQL, dependency review, Release Gate, Helm, or SDK/TypeScript checks. The circular-import guard remains strict; no cycle is ignored, allowlisted, dynamically hidden, or excluded from analysis.

## Deliberately out of scope

- compatibility-module deprecation/removal;
- service/interface dependency-direction rules beyond the single cycle repair;
- import-time performance optimization;
- dynamic import analysis;
- broader caller or provider refactors.

## Verification contract

Merge only after the circular-import guard, the existing `--stream-tools` caller regression tests, and all fresh required hosted checks pass on the exact PR head SHA.

## Next boundary

After this guard and the single cycle repair are green and merged, add exactly one remaining P2.1 dependency-direction invariant—preferably the service/interface adapter direction—without bundling a broader runtime refactor into the same slice.
