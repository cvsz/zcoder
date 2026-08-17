# Upgrade-53 — Service / Infrastructure Dependency Boundary

## Goal

Advance one bounded `ROADMAP-NEXT.md` P2.1 architecture item by making the application-service dependency direction executable: canonical `src/zcoder/services` modules must not import concrete `zcoder.infrastructure` adapters.

## Scope

- extend the existing AST-based architecture boundary guard;
- scan all Python modules under `src/zcoder/services`;
- fail deterministically when a service imports `zcoder.infrastructure` or a submodule below it;
- reuse the same guard already protecting `domain` and `core` rather than introducing a second architecture-test framework.

## Upgrade-20/24 boundedness

This slice is test/documentation only. It adds no runtime/provider execution, polling, retries, sleeps, scheduler or daemon behavior, recursive execution, automatic tool execution, concurrency-budget expansion, authentication change, authorization change, or persistence change.

It does not weaken Ruff, Black, pytest, coverage, Bandit, CodeQL, dependency review, Release Gate, Helm, or SDK/TypeScript checks. No architecture violation is allowlisted or excluded.

## Deliberately out of scope

- interface-layer dependency rules;
- compatibility-module cleanup;
- infrastructure refactors;
- runtime dependency injection changes;
- broader service/package restructuring.

## Verification contract

Merge only after the architecture guard and all fresh required hosted checks pass on the exact PR head SHA. If the guard exposes a real service-to-infrastructure dependency, repair one concrete violation only rather than weakening the guard.

## Next boundary

After this rule is green and merged, add exactly one remaining P2.1 dependency-direction invariant—preferably an interface-layer rule—without bundling a broader runtime refactor into the same slice.
