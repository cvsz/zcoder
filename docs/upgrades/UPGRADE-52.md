# Upgrade-52 — Canonical Package Circular-Import Guard

## Goal

Advance one bounded `ROADMAP-NEXT.md` P2.1 architecture item by encoding circular-import detection as an executable regression guard for the canonical `src/zcoder` package.

## Scope

- statically parse Python modules under `src/zcoder` with `ast`;
- resolve canonical absolute imports and package-relative imports;
- build an internal module dependency graph;
- fail deterministically when that graph contains a cycle;
- report one concrete cycle path in the assertion message.

## Upgrade-20/24 boundedness

This slice is test/documentation only. It does not change runtime/provider behavior, polling, retries, sleeps, scheduler or daemon behavior, recursive execution, automatic tool execution, concurrency budgets, authentication, authorization, or persistence semantics.

It does not weaken Ruff, Black, pytest, coverage, Bandit, CodeQL, dependency review, Release Gate, Helm, or SDK/TypeScript checks.

## Deliberately out of scope

- runtime refactors to remove any cycle discovered by the guard;
- compatibility-module deprecation/removal;
- service/interface dependency-direction rules;
- import-time performance optimization;
- dynamic import analysis.

## Verification contract

Merge only after the focused architecture test and all fresh required hosted checks pass on the exact PR head SHA.

## Next boundary

After this guard is green and merged, add exactly one remaining P2.1 dependency-direction invariant—preferably the service/interface adapter direction—without bundling runtime refactors into the same slice.
