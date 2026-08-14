# UPGRADE-25: Durable End-to-End Continuous Engineering Pipeline

## Overview

Upgrade-25 turns the Upgrade-24 callback meta-loop into an invokable, restart-safe engineering pipeline by wiring it to the existing Upgrade-20 autonomous engineering runtime and the Upgrade-23 maintenance recommendation boundary.

The implementation is intentionally an orchestration layer rather than a second task engine:

- `src/zcoder/services/upgrade_loop.py` remains the bounded queue-level policy engine from Upgrade-24.
- `src/zcoder/enterprise/local_ai_stack.py` remains the Upgrade-20 task-level engineering authority.
- `src/zcoder/services/continuous_engineering.py` adapts work items into Upgrade-20 tasks and normalizes their outcomes.
- `src/zcoder/services/upgrade_state.py` persists durable work identity, attempts, terminal state, and loop checkpoints.
- the existing `GitHubOrchestrator.execute_ci_repair_loop()` can be injected as a bounded CI repair hook.

## Architecture

```text
 Explicit feature / work JSON
             |
 Upgrade-23 maintenance recommendations
             |
             v
 +-----------------------------------+
 | ContinuousEngineeringPipeline     |
 | - restore/resume                  |
 | - persisted blockers              |
 | - work-source composition         |
 +----------------+------------------+
                  |
                  v
 +-----------------------------------+
 | ContinuousUpgradeLoop (Upgrade-24)|
 | priority / retry / regression /   |
 | no-progress / iteration budgets   |
 +----------------+------------------+
                  |
                  v
 +-----------------------------------+
 | Upgrade20EngineeringExecutor      |
 | stable task ID from fingerprint   |
 | risk + source mapping             |
 | bounded repository snapshot       |
 +----------------+------------------+
                  |
                  v
 +-----------------------------------+
 | AutonomousEngineeringLoop         |
 | Upgrade-20 task execution         |
 +----------------+------------------+
                  |
          optional REPAIR hook
                  v
 +-----------------------------------+
 | GitHubOrchestrator CI repair      |
 | existing bounded repair contract  |
 +-----------------------------------+

 Every loop checkpoint
          |
          v
 +-----------------------------------+
 | JsonUpgradeLedger                 |
 | atomic fsync + os.replace         |
 +-----------------------------------+
```

## Durable restart and idempotency

Upgrade-24 deduplicates equivalent work inside one process. Upgrade-25 extends that guarantee across process restarts.

`JsonUpgradeLedger` stores records by the same stable SHA-256 fingerprint used by `UpgradeWorkItem`. Each record contains:

- stable `item_id`;
- title and work kind;
- payload, priority, risk, and attempt budget;
- current state and consumed attempts;
- last error;
- timestamp.

Checkpoints are also persisted and bounded to the latest 100 records by default.

### Resume rules

1. `SUCCEEDED` fingerprints are never executed again.
2. `PENDING`, `RUNNING`, and other non-terminal records are resumed with their consumed attempt count.
3. `BLOCKED` records remain visible as blockers and are not silently reported as completed.
4. `--retry-blocked` explicitly resets the blocked item's attempt budget and makes it runnable again.
5. A corrupt or unsupported ledger fails closed with `UpgradeLedgerError`; the runtime never silently discards durable history and starts from an empty state.

## Repository snapshot safety

The Upgrade-20 adapter receives a bounded text snapshot rather than an unrestricted filesystem walk.

Defaults:

- maximum 400 files;
- maximum 256 KiB per file;
- maximum 4 MiB total context;
- symlinks are excluded;
- `.git`, `.zcoder`, virtual environments, build outputs, caches, `node_modules`, and `vendor` are excluded;
- `.env*`, common private-key filenames, and `.key/.pem/.p12/.pfx` files are excluded;
- non-UTF-8/binary files are skipped.

These limits make context construction deterministic and reduce accidental secret ingestion.

## Upgrade-20 adapter semantics

`Upgrade20EngineeringExecutor` creates a deterministic task ID from the work fingerprint:

```text
upgrade25-<first 20 hex chars of fingerprint>
```

The adapter pre-creates the Upgrade-20 task so risk and source policy are preserved, then calls `run_engineering_loop()` with the repository snapshot.

The default local pipeline maps:

- source to `TaskSource.WORKFLOW`;
- `low`, `medium`, `high`, `critical` to the corresponding Upgrade-20 `TaskRisk`;
- push policy to `AUTO_LOCAL_ONLY` unless `--allow-push` is explicitly supplied.

A returned Upgrade-20 `SUCCEEDED` task maps to a passing Upgrade-24 `ValidationResult`. Any other terminal status maps to validation failure and consumes the existing Upgrade-24 retry budget.

## Upgrade-23 integration

`maintenance_work_source(service)` converts each recommendation returned by Upgrade-23 through the existing `work_from_maintenance_recommendation()` adapter.

Examples:

- `PATCH_DEPENDENCY` -> `UPDATE`;
- `REPAIR_CI` -> `REPAIR`.

Because discovery runs every Upgrade-24 iteration, newly generated recommendations can enter the queue without duplicating already completed fingerprints.

## GitHub CI repair integration

`github_ci_repair_hook()` adapts the existing `GitHubOrchestrator.execute_ci_repair_loop()` contract.

For a `REPAIR` work item, the hook is activated when the payload contains:

```json
{
  "github_job_id": "job-123",
  "github_repo": "cvsz/zcoder",
  "github_pr": 42
}
```

`repository` may be used instead of `github_repo`.

The repair count is bounded by `max_ci_repairs` (default `3`). If the existing GitHub repair loop exhausts its budget, Upgrade-25 returns validation failure and lets the Upgrade-24 item budget decide whether to retry or block.

## CLI

The pipeline is directly invokable without changing the existing main CLI surface:

```bash
python -m zcoder.services.continuous_engineering \
  --repository . \
  --feature "Implement provider health endpoint" \
  --description "Expose health and routing status" \
  --risk medium
```

Safe default: local-only push policy.

Explicit push opt-in:

```bash
python -m zcoder.services.continuous_engineering \
  --repository . \
  --feature "Repair release workflow" \
  --allow-push
```

Resume pending durable work:

```bash
python -m zcoder.services.continuous_engineering --repository .
```

Retry previously blocked durable work:

```bash
python -m zcoder.services.continuous_engineering --repository . --retry-blocked
```

## Work-file input

`--work-file` accepts a JSON array so automation can seed multiple independently verifiable items while the meta-loop still executes one slice per iteration.

```json
[
  {
    "title": "Update dependency X",
    "kind": "UPDATE",
    "priority": 80,
    "risk": "low",
    "max_attempts": 2,
    "payload": {"package": "X"}
  },
  {
    "title": "Implement dashboard status panel",
    "kind": "IMPLEMENT_FEATURE",
    "description": "Show current provider health",
    "priority": 60,
    "risk": "medium"
  }
]
```

Supported kinds remain `UPGRADE`, `UPDATE`, `IMPLEMENT_FEATURE`, and `REPAIR`.

## Verification

`tests/unit/test_continuous_engineering.py` covers:

- feature execution through the Upgrade-20 contract;
- risk/source propagation;
- durable success persistence;
- restart deduplication;
- retry then blocked behavior;
- persisted blocker visibility;
- explicit retry of blocked work;
- pending crash/restart resume;
- Upgrade-23 recommendation discovery;
- existing GitHub CI repair contract adaptation;
- CI repair budget failure propagation;
- secret-aware bounded repository snapshots;
- corrupt-ledger fail-closed behavior;
- JSON work-file parsing for all work kinds.

## Safety invariants

1. Upgrade-24 global iteration and no-progress budgets remain authoritative.
2. Upgrade-20 remains the task-level execution authority; Upgrade-25 does not duplicate worktree/review/security policy.
3. Push is local-only by default and requires explicit opt-in.
4. Terminal success is persisted by fingerprint and is idempotent across restarts.
5. Persisted blockers cannot disappear into a false `COMPLETED` result.
6. Corrupt durable state fails closed.
7. Repository context is bounded and secret-aware.
8. GitHub CI repair reuses the existing bounded orchestrator rather than introducing an unbounded repair loop.

## Definition of done

- [x] Upgrade-24 wired to Upgrade-20 through a dedicated executor adapter.
- [x] Stable Upgrade-20 task IDs derived from work fingerprints.
- [x] Upgrade-20 task source and risk propagated.
- [x] Upgrade-23 maintenance recommendation work source implemented.
- [x] Durable JSON ledger and atomic checkpoint persistence implemented.
- [x] Cross-process completed-work deduplication implemented.
- [x] Pending-work restart/resume implemented.
- [x] Persisted blocker visibility and explicit blocked retry implemented.
- [x] Secret-aware bounded repository snapshot implemented.
- [x] Existing GitHub CI repair loop adapter implemented.
- [x] Safe local-only default and explicit push opt-in implemented.
- [x] Invokable module CLI and JSON work-file input implemented.
- [x] Focused unit test suite added.
- [ ] Hosted CI verification and merge.
