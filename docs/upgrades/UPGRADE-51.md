# Upgrade-51 — Architecture Boundary Regression Guard

## Goal

Advance the first bounded item in `ROADMAP-NEXT.md` Phase P2.1 by converting two architecture rules into executable regression guards:

- `domain` must not import concrete infrastructure adapters;
- `core` must not import concrete infrastructure adapters.

## Implementation

`tests/unit/test_architecture_boundaries.py` parses Python source under `src/zcoder/domain` and `src/zcoder/core` with the standard-library AST and fails if either layer imports `zcoder.infrastructure` or one of its submodules.

This is intentionally a narrow first architecture slice. It does not attempt to encode every dependency direction, circular-import check, compatibility-module deprecation rule, or service/interface boundary in one change.

## Upgrade-20/24 invariants

This slice adds no runtime execution, provider call, retry, sleep, polling loop, scheduler, daemon, recursive tool/agent behavior, automatic tool execution, or expanded iteration budget. It does not alter Ruff, Black, pytest, coverage, Bandit, CodeQL, dependency-review, release, Helm, or SDK/TypeScript gates.

## Regression contract

The guard scans the repository source directly, so future accidental imports create a deterministic unit-test failure before the architecture boundary can silently erode.

## Next boundary

After fresh hosted checks pass and this slice is merged, extend architecture validation by exactly one additional P2.1 rule, preferably service/interface direction or circular-import detection, based on the then-current `main` baseline.
