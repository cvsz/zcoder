# Upgrade-50 — Remove Temporary Repository-Hardening Scaffold

## Goal

Complete the explicit `ROADMAP-NEXT.md` P0.6 cleanup boundary by removing the one-shot repository-hardening migration machinery after the permanent hardening changes have landed on `main`.

## Removed temporary artifacts

- `.github/workflows/apply-repository-hardening.yml`
- `scripts/apply_repository_hardening.py`
- `scripts/run_repository_hardening.py`

The removed workflow targeted the historical `chore/complete-repository-hardening` branch and carried `contents: write` so it could commit deterministic migration output. The two Python scripts describe themselves as one-shot migration tooling rather than production runtime components.

## Upgrade-20/24 invariants

This slice is cleanup-only. It does not change provider behavior, runtime execution budgets, retry policy, polling, scheduling, tool execution, authentication, authorization, or security thresholds. No test, CodeQL, dependency-review, release, lint, formatting, or coverage gate is weakened.

## Regression guard

`tests/unit/test_hardening_scaffold_removed.py` asserts that all three temporary migration paths remain absent. This converts the P0.6 cleanup boundary into an executable repository invariant instead of relying only on documentation.

## Scope

The slice removes only the three explicitly documented temporary artifacts and adds the focused regression guard plus this upgrade record. It does not rewrite historical roadmap claims or remove unrelated scripts/workflows.

## Next boundary

After this slice passes fresh CI, CodeQL, dependency review, release, and SDK/Helm checks and is merged, select the next independently verifiable Upgrade-24 item from the current production-readiness gaps rather than widening this cleanup PR.
