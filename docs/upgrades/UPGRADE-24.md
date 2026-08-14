# UPGRADE-24: Continuous Upgrade / Update / Feature Implementation Loop

## Overview

Upgrade-24 adds a bounded meta-orchestrator above zcoder's existing autonomous engineering and maintenance capabilities. The loop continuously discovers, prioritizes, implements, validates, and checkpoints independently verifiable work items across four classes:

- `UPGRADE` — architectural, capability, platform, or runtime upgrades.
- `UPDATE` — dependency, configuration, API, model, toolchain, or compatibility updates.
- `IMPLEMENT_FEATURE` — new product or engineering feature vertical slices.
- `REPAIR` — CI, regression, security, or maintenance repair work.

The implementation lives in `src/zcoder/services/upgrade_loop.py`.

## Why this layer exists

Upgrade-20 provides the engineering execution loop for a task. Upgrade-23 provides maintenance signals, recommendations, and self-repair intelligence. Upgrade-24 composes those capabilities into a higher-level queue that can repeatedly select the next useful change while enforcing bounded execution and regression safety.

```text
Discovery / Requests / Upgrade-23 Recommendations
                    |
                    v
        +-------------------------+
        | ContinuousUpgradeLoop   |
        +-------------------------+
          | prioritize + dedupe
          v
   one vertical slice / iteration
          |
          v
   implementation callback
          |
          v
   validation callback
      /           \
   pass           fail
    |              |
checkpoint     rollback/retry
    |              |
 next item   regression guard / halt
```

## Core guarantees

1. **Bounded execution**
   - Global `max_iterations` prevents unbounded autonomous work.
   - `max_no_progress_iterations` prevents retry loops that do not converge.
   - Each work item has its own `max_attempts` budget.

2. **Regression guard**
   - Validation returns structured `regressions`.
   - When `stop_on_regression=True`, any newly introduced regression blocks the item and halts the loop.
   - An injected rollback callback can restore the pre-change state before halt/retry.

3. **One verifiable slice at a time**
   - The loop executes one work item, validates it, and checkpoints before selecting the next item.
   - This matches the repository's PR/vertical-slice operating model and avoids batching unrelated risky changes.

4. **Idempotent discovery**
   - Work items use a stable SHA-256 content fingerprint across kind/title/payload.
   - Re-discovering the same dependency update, repair, or requested feature does not duplicate execution.

5. **Provider-neutral orchestration**
   - Discovery, implementation, validation, rollback, and checkpoint storage are injected callbacks.
   - The loop can run over the local autonomous engineering runtime, GitHub orchestration, CI repair adapters, or offline tests without introducing provider coupling into the application service.

6. **Upgrade-23 bridge**
   - `work_from_maintenance_recommendation()` maps `PATCH_DEPENDENCY` to `UPDATE` and `REPAIR_CI` to `REPAIR`.
   - Unknown future maintenance recommendation types safely map to `UPGRADE` until a more specific adapter is added.

## API surface

```python
from zcoder.services.upgrade_loop import (
    ContinuousUpgradeLoop,
    LoopPolicy,
    ValidationResult,
    feature_work,
)

loop = ContinuousUpgradeLoop(
    discover=discover_work,
    implement=implement_vertical_slice,
    validate=validate_vertical_slice,
    rollback=rollback_vertical_slice,
    checkpoint=save_checkpoint,
    policy=LoopPolicy(
        max_iterations=12,
        max_no_progress_iterations=3,
        stop_on_regression=True,
    ),
)

report = loop.run(
    [feature_work("Add provider health dashboard", "Expose provider health and routing status")]
)
```

## Suggested integration with Upgrade-20

The `implement` callback should adapt one `UpgradeWorkItem` into an Upgrade-20 `EngineeringTask` and invoke `AutonomousEngineeringLoop` using the isolated worktree / checkpoint / review / security / commit pipeline already present in zcoder.

The `validate` callback should consume Upgrade-20's validation delta and return:

```python
ValidationResult(
    passed=not delta.new_regressions,
    summary="engineering validators completed",
    regressions=tuple(delta.new_regressions),
)
```

This keeps Upgrade-24 responsible for portfolio-level iteration policy while Upgrade-20 remains responsible for task-level code execution semantics.

## Verification

Unit coverage is provided by `tests/unit/test_upgrade_loop.py` and verifies:

- mixed upgrade/update/feature execution;
- priority ordering;
- deduplicated rediscovery;
- bounded retries;
- regression halt and rollback;
- no-progress halt;
- checkpoint emission;
- Upgrade-23 recommendation adaptation;
- feature request validation.

## Definition of done

- [x] Continuous meta-loop application service implemented.
- [x] Upgrade / update / feature / repair work kinds implemented.
- [x] Stable discovery deduplication implemented.
- [x] Per-item retries and global iteration budget implemented.
- [x] No-progress detector implemented.
- [x] Regression guard and rollback hook implemented.
- [x] Checkpoint callback implemented.
- [x] Upgrade-23 maintenance recommendation bridge implemented.
- [x] Unit test suite added.
- [x] Upgrade documentation and execution-plan ledger updated.
