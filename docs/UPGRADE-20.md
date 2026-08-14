# UPGRADE-20: Autonomous Software Engineering Loop

## 1. Overview
Upgrade-20 integrates all prior platform capabilities (Upgrades 14–19) into a complete, durable, isolated, zero-cost autonomous software engineering loop: Issue/Task → Baseline → Isolated Worktree → Versioned Plan → Bounded Edit/Repair → Static Review → Security Hard Gate → Commit → [Push/PR].

## 2. New Components

### Task Domain (§5–§9)
- **`EngineeringTask`**: Durable task record with 18-state lifecycle (`CREATED` → `SUCCEEDED`/`FAILED`/`CANCELLED`). Source content from GitHub issues/PR comments is explicitly marked `source_content_trusted=False` and cannot override security, cost, or tenant policy.
- **`ExecutionAttempt`**: Separate from `EngineeringTask` so retry preserves full history. Each attempt records `base_commit`, `worktree_path`, `model_profile`, `plan_revision`, `result`.
- **`TaskSource`**: `CLI | API | GITHUB_ISSUE | WORKFLOW | MANUAL`
- **`TaskRisk`**: `LOW | MEDIUM | HIGH | CRITICAL`

### Execution Plan (§19–§23)
- **`EngineeringPlan`**: Versioned plan with `revision` counter. Repair/replan creates a new revision without losing history. Plan cannot authorize tools — the policy engine remains authoritative.

### Validation (§43–§49)
- **`ValidationState`**: Semantically correct — `DISCOVERED` ≠ `EXECUTED_PASS`/`FAIL`/`ERROR`/`TIMEOUT`.
- **`ValidationCommand`**: Starts `DISCOVERED`, transitions to `EXECUTED_*` after actual execution.
- **`ValidationProfile`**: Project-specific pipeline derived from bootstrap.
- **`ValidationFailure`**: Structured failure with `validator`, `file`, `message`, `category`, `attempt_id`.
- **`ValidationDelta`**: Tracks `fixed`, `new_regressions`, `unchanged_failures` between baseline and post-edit runs.

### Worktree (§12–§18)
- **`WorktreeManager`**: Path-escape guard (`..` detection, `os.path.realpath` validation), safe branch name sanitization, ownership tracking (`ZCODER_MANAGED`), idempotent resume (no duplicate worktree on restart).

### Context Builder (§25–§27)
- **`EngineeringContextBuilder`**: Bounded context assembly with hard token-budget truncation. Priority: task → policy → project instructions → relevant source → baseline failures → RAG → tool results.

### No-Progress Detector (§53)
- **`NoProgressDetector`**: Detects repeated same-failure fingerprint and A→B→A patch oscillation. Stops repair loop immediately when stuck.

### Static Review (§63–§65)
- **`StaticReviewer`**: Deterministic diff analysis for secrets (18 patterns), test weakening (skip/xfail/noqa), out-of-scope modifications.
- **`StaticReviewFinding`**: Structured findings with `severity`, `category`, `file`, `line`, `blocking`.

### Security Gate (§70–§71)
- **`SecurityGate`**: Hard-failure gate — cannot be averaged with quality scores. Blocking findings result in `FAILED_SECRET`, `FAILED_TEST_WEAKENING`, or `FAILED_POLICY` status. Task cannot finalize.

### Commit/Push (§75–§83)
- **`CommitPreconditions`**: All four preconditions must be `True`: `final_validators_passed`, `security_gate_passed`, `required_approvals_satisfied`, `worktree_clean`.
- **`PushPolicy`**: `AUTO_LOCAL_ONLY` (safe default), `APPROVAL_BEFORE_PUSH`, `AUTO_PUSH_ALLOWED`. No remote mutation without explicit policy.

### Checkpoint/Recovery (§55–§60)
- **`Checkpoint`**: Durable checkpoints after BASELINE, PLAN, VALIDATION, COMMIT phases.
- **`CheckpointStore`**: Save/load/latest-for-task. `resume_task()` returns latest checkpoint for idempotent restart without duplicate worktree/commit/PR.

## 3. Verification
- `pytest tests/test_upgrade20_engineering_loop_suite.py`: **69 passed, 0 failed**
- Full regression suite: **807 passed, 2 optional skipped, 0 failed**

## 4. Key Invariants
- Zero paid API calls during autonomous local engineering (verified by `TransportCallMonitor`)
- No remote push by default — `AUTO_LOCAL_ONLY` is the safe default
- Security hard failures block the loop immediately — not softened by quality metrics
- Task source text (GitHub issues, PR comments) is explicitly `untrusted` — cannot override policy
- Worktree path traversal is blocked at creation time
