# C1 Truth & Completion Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reconcile repository planning, roadmap, release, DR, and governance documentation against the actual merged state at `main@786579a048574dbf52d4807d3bc1c7923b08a27a`, producing one evidence-backed completion ledger that later C2–C6 work can trust.

**Architecture:** C1 is documentation/evidence reconciliation only; it must not modify production Python, workflows, tests, dependencies, or repository settings. The implementation treats merged code/workflows and hosted evidence as source-of-truth, preserves historical closure documents where their original claims remain valid, and explicitly marks evidence invalidated by later code/config/dependency changes instead of pretending old RC evidence qualifies the current head.

**Tech Stack:** Markdown, Git/GitHub history, GitHub Actions evidence, existing `scripts/release-candidate.mjs`, repository workflows, existing release/DR documentation.

**Spec:** `docs/superpowers/specs/2026-08-23-completion-program-design.md`

## Global Constraints

- Baseline for this plan is exactly `main@786579a048574dbf52d4807d3bc1c7923b08a27a`.
- Preserve bounded-slice execution; C1 is docs/evidence only.
- Never weaken or relabel tests, coverage, CodeQL, Dependency Review, Bandit, pip-audit, Gitleaks, Helm, Release Gate, SDK/TypeScript, or reproducibility gates.
- Do not mark production/DR evidence complete without exact-RC evidence.
- Python support is `>=3.10`; do not restore stale Python 3.9 claims.
- Use only these final ledger states: `COMPLETE / VERIFIED`, `IMPLEMENTED / QUALIFICATION PENDING`, `INCOMPLETE / ACTIONABLE`, `HANDOFF / REQUIRES ENVIRONMENT`.
- Historical closure evidence may remain closed for the historical SHA it proves, but must not be represented as current-RC proof after later mutations.
- No broad source-file rewrites; keep each documentation edit bounded and reviewable.

---

## File Structure

**Create**
- `docs/completion/COMPLETION-LEDGER.md` — canonical current-state ledger consumed by C2–C6.

**Modify**
- `exec-planning.md` — canonical execution queue/baseline; remove stale residuals and point active work to C2–C6.
- `ROADMAP-NEXT.md` — collapse superseded historical unchecked items into verified/current status and remove Python 3.9-era instructions.
- `docs/operations/dr-rehearsal.md` — remove known-gap statements fixed by PR #93 while preserving exact-RC evidence caveat.
- `docs/operations/GITHUB-GOVERNANCE.md` — reconcile completed SBOM/signing/reproducibility controls and preserve remaining C6 governance work.
- `docs/closure/ep11-production-execution.md` — label `2ec89ce` evidence as historical qualification, remove `PASS (expected)` wording, and state that current-head qualification is pending C5.
- `docs/closure/ep11b-gpg-attestation.md` — preserve historical signature/attestation closure while distinguishing current RC qualification from historical evidence.
- `docs/closure/ep12-13-cutover-retirement.md` — preserve cutover closure but remove claims that `ROADMAP-NEXT.md` is fully synchronized if the current file still contains stale PR #6/Python 3.9-era backlog.
- `CHANGELOG.md` — reconcile any completion claim that exceeds evidence available at the current baseline; do not delete historical release notes.

**Read-only evidence inputs**
- `.github/workflows/reproducibility.yml`
- `.github/workflows/publish-container.yml`
- `.github/workflows/release.yml`
- `src/zcoder/services/backup_restore.py`
- `tests/unit/test_performance_targets.py`
- `tests/integration/test_dr_rehearsal.py`
- `tests/unit/test_admission_gate.py`
- merged PRs #88–#101 and their hosted checks

---

### Task 1: Build an Evidence-Backed State Inventory

**Files:**
- Create: `docs/completion/COMPLETION-LEDGER.md`
- Read: `exec-planning.md`, `ROADMAP-NEXT.md`, `CHANGELOG.md`, merged PRs #88–#101, workflow files listed above

**Interfaces:**
- Consumes: current merged repository state at baseline SHA and exact PR/merge evidence.
- Produces: a ledger table with columns `Domain | Capability | State | Implementation Evidence | Qualification Evidence | Residual / Next Slice`.

- [ ] **Step 1: Create the ledger header and state contract**

Create `docs/completion/COMPLETION-LEDGER.md` with this exact opening structure:

```markdown
# zcoder Completion Ledger

**Baseline:** `main@786579a048574dbf52d4807d3bc1c7923b08a27a`  
**Date:** 2026-08-23  
**Authority:** current merged code/workflows + exact hosted evidence; historical TODO prose is non-authoritative when superseded.

## State Contract

- `COMPLETE / VERIFIED` — merged implementation plus valid evidence for the claim at the cited SHA.
- `IMPLEMENTED / QUALIFICATION PENDING` — implementation exists, but final exact-RC qualification is not yet attached.
- `INCOMPLETE / ACTIONABLE` — repository-owned implementation gap remains.
- `HANDOFF / REQUIRES ENVIRONMENT` — completion requires external runtime/credential/environment evidence.

## Current Completion Matrix

| Domain | Capability | State | Implementation Evidence | Qualification Evidence | Residual / Next Slice |
|---|---|---|---|---|---|
```

- [ ] **Step 2: Populate verified implementation rows from merged state**

Add rows for at least these capabilities, using evidence that actually exists in source/workflows/merged PRs:

```markdown
| Supply chain | uv.lock drift detection + locked install | IMPLEMENTED / QUALIFICATION PENDING | PR #88; `.github/workflows/reproducibility.yml` contains both `uv lock --check` and `uv sync --locked` | Current final-RC run not yet frozen | C5 |
| Supply chain | Keyless container signing | IMPLEMENTED / QUALIFICATION PENDING | PR #89; `publish-container.yml` runs `cosign sign --yes` on pushed digest | Verify signature on exact C5 RC | C5 |
| Supply chain | Per-architecture SBOMs | IMPLEMENTED / QUALIFICATION PENDING | `publish-container.yml` builds amd64/arm64 SBOM artifacts | Verify artifacts on exact C5 RC | C5 |
| Packaging | Helm package/checksum | IMPLEMENTED / QUALIFICATION PENDING | PR #90 + Helm workflow | Exact C5 RC artifact check pending | C5 |
| Release | SemVer release-tag gate | COMPLETE / VERIFIED | PR #91; `release.yml` validates `RELEASE_TAG` before build | Merged workflow behavior evidenced | none |
| DR | Backup/restore strictness + retention + dry-run | IMPLEMENTED / QUALIFICATION PENDING | PR #93; `backup_restore.py` fail-closes expected-ID misses, exposes dry-run, enforces weekly tier | Live exact-RC DR rehearsal still required | C5 / environment |
| Observability | `/metrics`, live/readiness probes | IMPLEMENTED / QUALIFICATION PENDING | PR #94 | Exact-RC runtime smoke pending | C5 |
| Observability | OTel bootstrap | IMPLEMENTED / QUALIFICATION PENDING | PR #95 | Collector-backed exact-RC evidence pending | C5 / environment |
| Durability | Cross-process claim/fence/crash-reclaim | IMPLEMENTED / QUALIFICATION PENDING | PR #96 + tests | Exact-RC rerun pending | C5 |
| Fleet | SQLite CAS + EngineeringWorker drain | IMPLEMENTED / QUALIFICATION PENDING | PR #97 | Exact-RC qualification pending | C5 |
| Fleet | Maintenance scheduler | IMPLEMENTED / QUALIFICATION PENDING | PR #98 | Exact-RC qualification pending | C5 |
| Fleet | Admission seam | INCOMPLETE / ACTIONABLE | PR #99 deliberately leaves `AdmissionGate` unwired | none | C3 |
| Agent UX | Skills install lifecycle | INCOMPLETE / ACTIONABLE | PR #81 advertises install but implementation is placeholder | none | C2 |
| Performance | Bounded performance targets | IMPLEMENTED / QUALIFICATION PENDING | `tests/unit/test_performance_targets.py` | Exact-RC execution pending | C5 |
| Governance | Main branch protection/rulesets | INCOMPLETE / ACTIONABLE | repository audit shows `protected:false` | none | C6 |
```

- [ ] **Step 3: Record historical-only evidence explicitly**

Add a section:

```markdown
## Historical Evidence That Does Not Qualify the Final RC

Evidence tied to `2ec89ce` (including EP11/EP11b/EP12-13) remains valid for the historical claims it proves. Because later code/config/dependency changes produced `main@786579a...`, those records do **not** qualify the final completion release candidate. C5 must re-run final-RC qualification against one immutable SHA.
```

- [ ] **Step 4: Run a contradiction scan**

Run:

```bash
rg -n "3\.9|PARTIAL|remain|remaining|TODO|placeholder|PASS \(expected\)|known gaps|not complete yet|protected: false" \
  exec-planning.md ROADMAP-NEXT.md CHANGELOG.md docs/closure docs/operations docs/completion
```

Expected: command may return matches; every returned match must be classified as either intentional historical text or a C1 edit target. Do not bulk-delete historical references.

- [ ] **Step 5: Commit the ledger skeleton and inventory**

```bash
git add docs/completion/COMPLETION-LEDGER.md
git commit -m "docs: add evidence-backed completion ledger"
```

---

### Task 2: Reconcile `exec-planning.md` With Merged Reality

**Files:**
- Modify: `exec-planning.md`
- Read: `docs/completion/COMPLETION-LEDGER.md`

**Interfaces:**
- Consumes: Task 1 ledger.
- Produces: one canonical active queue whose residuals match C2–C6 exactly.

- [ ] **Step 1: Update header baseline and date**

Replace the stale baseline header with:

```markdown
**Current Baseline:** `main@786579a048574dbf52d4807d3bc1c7923b08a27a` (post-CI alignment; completion-program baseline)  
**Last Updated:** 2026-08-23
```

- [ ] **Step 2: Reconcile SEC-010 status**

Replace the SEC-010 matrix claim that cosign and uv.lock wiring remain with a state that distinguishes implementation from final qualification:

```markdown
| **SEC-010** | **CI/dependency/supply-chain** | **IMPLEMENTED / FINAL-RC QUALIFICATION PENDING** | Immutable action pinning, least privilege, release/container SBOMs, per-arch SBOMs, `uv lock --check`, `uv sync --locked`, keyless cosign signing, Helm packaging/checksums, and release-tag gate are merged. Final artifact/signature/reproducibility verification is C5. |
```

- [ ] **Step 3: Replace obsolete Slice-F residual language**

Where the file says fleet runtime wiring, OTel, backup_restore remediation, reproducibility wiring, or per-arch SBOM remain, replace those statements with references to the merged work and the real residuals:

```markdown
Current repository-owned residuals:
1. C2 — remove advertised skills-install placeholder.
2. C3 — compose the deliberately unwired AdmissionGate into reachable submission paths.
3. C4 — audit/close supported child-agent lifecycle gaps.
4. C5 — freeze and qualify one exact release-candidate SHA, including environment-backed DR/observability evidence.
5. C6 — enforce repository governance/rulesets after final check names are verified.
```

- [ ] **Step 4: Normalize final-release matrix states**

For every final-release row, use only the four ledger states. In particular:
- implementation-present rows without current-RC evidence become `IMPLEMENTED / QUALIFICATION PENDING`;
- governance becomes `INCOMPLETE / ACTIONABLE`;
- environment-only evidence becomes `HANDOFF / REQUIRES ENVIRONMENT` until C5 runs it.

- [ ] **Step 5: Verify no stale active residual remains**

Run:

```bash
rg -n "cosign signing .*remain|uv\.lock .*remain|per-arch .*remain|backup_restore\.py gap remediation|fleet runtime wiring, OTel|Python 3\.9 / 3\.10" exec-planning.md
```

Expected: no active-current-state matches. Historical evidence sections may still mention Python 3.9 when describing old verified PRs; do not rewrite those histories.

- [ ] **Step 6: Commit**

```bash
git add exec-planning.md
git commit -m "docs: reconcile canonical execution plan with merged state"
```

---

### Task 3: Repair `ROADMAP-NEXT.md` Without Rewriting History

**Files:**
- Modify: `ROADMAP-NEXT.md`

**Interfaces:**
- Consumes: completion ledger + reconciled execution plan.
- Produces: forward-looking roadmap that delegates current authority to `exec-planning.md` and no longer presents 2026-08-14 backlog as current truth.

- [ ] **Step 1: Replace the stale current-baseline block**

Use:

```markdown
## 2. Current Baseline

`ROADMAP-NEXT.md` is a historical-to-forward roadmap. Current execution state is authoritative in `exec-planning.md` and `docs/completion/COMPLETION-LEDGER.md` at `main@786579a048574dbf52d4807d3bc1c7923b08a27a`.
```

- [ ] **Step 2: Remove stale Python 3.9 current-support requirements**

Change current/future instructions from `Python 3.9–3.12` to `Python 3.10–3.12`. Preserve any clearly labeled historical account of old CI runs.

- [ ] **Step 3: Collapse superseded P0–P4 checklists**

Do not individually flip dozens of old boxes. Add a short status note above legacy phases:

```markdown
> **Status note (2026-08-23):** The detailed P0–P4 checklists below are retained as historical planning context. Many items were subsequently implemented through PRs #48–#101 and are reconciled in `docs/completion/COMPLETION-LEDGER.md`. Do not use unchecked boxes below as current work authorization; current residuals are C2–C6 in `exec-planning.md`.
```

Then correct only statements that are dangerously misleading as active policy (Python 3.9 support, PR #6 as active, merge-through-protection claims when branch protection is not actually enabled).

- [ ] **Step 4: Verify historical-vs-current labeling**

Run:

```bash
rg -n "PR #6|3\.9|Not complete yet|merge through branch protection" ROADMAP-NEXT.md
```

Expected: every remaining match is explicitly historical, not current instruction.

- [ ] **Step 5: Commit**

```bash
git add ROADMAP-NEXT.md
git commit -m "docs: mark legacy roadmap backlog as historical"
```

---

### Task 4: Reconcile DR Runbook With PR #93

**Files:**
- Modify: `docs/operations/dr-rehearsal.md`
- Read: `src/zcoder/services/backup_restore.py`, PR #93

**Interfaces:**
- Consumes: current BackupManager behavior.
- Produces: operational procedure whose safety guidance matches implementation while retaining external-evidence requirements.

- [ ] **Step 1: Update restore-drill semantics**

Replace text saying expected-ID misses only warn with:

```markdown
`run_restore_drill()` now fails closed when requested job/repository IDs are missing and fails on verification exceptions. Operator verification queries remain required as independent evidence, but they are no longer compensating for a known false-success implementation gap.
```

- [ ] **Step 2: Update dry-run and retention semantics**

Replace text saying there is no dry-run or weekly retention with:

```markdown
Use `run_pg_dump_backup(dry_run=True)` to validate backup planning without invoking pg_dump or writing a manifest. Use `enforce_retention(dry_run=True)` to preview deletions. The two-window retention policy preserves the daily window and enforces the configured weekly retention horizon.
```

- [ ] **Step 3: Replace Known gaps with current residuals only**

Remove fixed items 1–4 and 6 from the old Known gaps list. Keep only real current constraints such as:
- custom-format dump naming still uses `.sql.gz` if unchanged;
- scheduling remains external (cron/Kubernetes CronJob);
- PITR still requires real WAL archive configuration/recovery proof in the target environment.

- [ ] **Step 4: Preserve exact-RC caveat**

Do not change the existing rule that a DR rehearsal only qualifies C5 when run against the exact immutable release-candidate SHA and an isolated non-production restore target.

- [ ] **Step 5: Commit**

```bash
git add docs/operations/dr-rehearsal.md
git commit -m "docs: sync DR rehearsal with restored fail-closed behavior"
```

---

### Task 5: Reconcile Supply-Chain and Governance Documentation

**Files:**
- Modify: `docs/operations/GITHUB-GOVERNANCE.md`
- Read: `.github/workflows/reproducibility.yml`, `.github/workflows/publish-container.yml`, `.github/workflows/release.yml`

**Interfaces:**
- Consumes: actual workflow controls.
- Produces: a future-hardening queue containing only real residuals.

- [ ] **Step 1: Update supported Python matrix**

Change workflow principle 4 from Python 3.9–3.12 to Python 3.10–3.12.

- [ ] **Step 2: Mark already-implemented supply-chain controls done**

Future hardening should explicitly mark:
- SBOM generation — DONE;
- per-architecture container SBOMs — DONE in implementation;
- keyless cosign signing — DONE in implementation;
- `uv lock --check` + `uv sync --locked` reproducibility wiring — DONE in implementation;
- artifact verification on the final RC — still C5 qualification work.

- [ ] **Step 3: Keep true governance residuals**

Future hardening must retain:
- branch/ruleset required checks;
- CODEOWNERS/security-sensitive review enforcement if chosen;
- protected tags/release environment approvals if required by release policy;
- operator recovery procedure;
- verifying normal Dependabot/release operation after rules apply.

- [ ] **Step 4: Commit**

```bash
git add docs/operations/GITHUB-GOVERNANCE.md
git commit -m "docs: reconcile governance hardening queue"
```

---

### Task 6: Correct Closure/Evidence Semantics

**Files:**
- Modify: `docs/closure/ep11-production-execution.md`
- Modify: `docs/closure/ep11b-gpg-attestation.md`
- Modify: `docs/closure/ep12-13-cutover-retirement.md`
- Read: `docs/migration/evidence/README.md`, `docs/migration/evidence/003-uv-lock-reproducibility.md`

**Interfaces:**
- Consumes: historical evidence tied to `2ec89ce`.
- Produces: honest historical closure documents that do not masquerade as final current-head qualification.

- [ ] **Step 1: Remove non-evidence wording in EP11**

Change the Python matrix row from `PASS (expected)` to a historically accurate statement backed by actual run IDs, or to `historical evidence incomplete` if no exact run ID can be substantiated. Never use expectation as PASS evidence.

- [ ] **Step 2: Add invalidation banner to EP11**

Add directly below metadata:

```markdown
> **Historical qualification notice:** This document closes production execution for `2ec89ce` only. Later code/config/dependency changes invalidate it as final-release evidence for current `main`; C5 must qualify a new immutable RC SHA.
```

- [ ] **Step 3: Add the same distinction to EP11b and EP12-13**

Preserve their historical closure statements, but explicitly separate historical signing/cutover proof from final C5 artifact/runtime qualification.

- [ ] **Step 4: Correct synchronization claims**

If EP12-13 says `ROADMAP-NEXT.md` was synchronized and that statement is false relative to the present file, rephrase it as a historical action at `2ec89ce`, not a claim about current documentation state.

- [ ] **Step 5: Commit**

```bash
git add docs/closure/ep11-production-execution.md docs/closure/ep11b-gpg-attestation.md docs/closure/ep12-13-cutover-retirement.md
git commit -m "docs: distinguish historical closure from final RC evidence"
```

---

### Task 7: Reconcile Changelog Claims Against Source Truth

**Files:**
- Modify: `CHANGELOG.md`
- Read: workflows/tests/source evidence listed in this plan

**Interfaces:**
- Consumes: Task 1 ledger.
- Produces: release notes that distinguish shipped implementation from final production qualification.

- [ ] **Step 1: Preserve shipped feature claims that are source-verifiable**

Keep claims for:
- SEC-010 workflow controls that are present;
- `uv sync --locked` if present in reproducibility workflow;
- per-arch SBOM if present in container workflow;
- performance tests if file exists;
- DR integration tests if file exists.

- [ ] **Step 2: Remove or qualify over-broad completion wording**

Replace statements such as `All confirmed attack surfaces closed and verified` only if the ledger cannot support the global claim at the release SHA. Prefer bounded wording such as:

```markdown
* Security remediation slices SEC-001–SEC-010 were implemented as documented; final exact-RC requalification remains governed by `exec-planning.md` and the completion ledger.
```

Do not rewrite old version history beyond what is needed to avoid a current false completion claim.

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: align changelog completion claims with evidence model"
```

---

### Task 8: Run C1 Documentation Verification and Open the Bounded PR

**Files:**
- Verify all modified C1 docs only.

**Interfaces:**
- Consumes: Tasks 1–7.
- Produces: one bounded docs-only PR ready for hosted checks and later merge.

- [ ] **Step 1: Run contradiction and placeholder scans**

```bash
rg -n "PASS \(expected\)|Python 3\.9–3\.12|Python 3\.9 / 3\.10|cosign signing .*remain|uv\.lock .*remain|per-arch .*remain|backup_restore\.py gap remediation|fleet runtime wiring, OTel" \
  exec-planning.md ROADMAP-NEXT.md CHANGELOG.md docs/completion docs/closure docs/operations
```

Expected: zero current-state contradictions. Historical matches must be explicitly labeled historical.

- [ ] **Step 2: Validate all ledger residuals map to C2–C6**

Manually verify every `INCOMPLETE / ACTIONABLE` row has exactly one next slice (`C2`, `C3`, `C4`, or `C6`) and every qualification/environment row points to `C5` where appropriate.

- [ ] **Step 3: Validate Markdown links where repository tooling supports it**

Run the repo's existing docs/link validation command from CI. If no dedicated command exists, at minimum run:

```bash
python - <<'PY'
from pathlib import Path
required = [
    Path('exec-planning.md'),
    Path('ROADMAP-NEXT.md'),
    Path('docs/completion/COMPLETION-LEDGER.md'),
    Path('docs/operations/dr-rehearsal.md'),
    Path('docs/operations/GITHUB-GOVERNANCE.md'),
]
for p in required:
    assert p.exists() and p.read_text(encoding='utf-8').strip(), p
print('C1 required docs present')
PY
```

Expected: `C1 required docs present`.

- [ ] **Step 4: Confirm production code/workflows are untouched**

```bash
git diff --name-only main...HEAD
```

Expected: only documentation files listed in this plan plus the approved design/plan docs; no `src/`, `tests/`, `.github/workflows/`, dependency, or deployment manifest changes.

- [ ] **Step 5: Push branch and open PR**

```bash
git push -u origin docs/completion-program-design

gh pr create \
  --base main \
  --head docs/completion-program-design \
  --title "docs: reconcile completion truth before final closure" \
  --body "C1 of the approved completion program. Docs/evidence only: reconciles stale roadmap/exec-plan/DR/governance claims against merged PRs #88-#101 and creates the four-state completion ledger. No production code, workflow, dependency, test, coverage, or security-gate changes."
```

- [ ] **Step 6: Hosted stop condition**

Do not merge until the exact PR head is green on all applicable docs/repository checks and has no unresolved blocking review thread. If hosted verification exposes a factual documentation error, repair only that bounded claim and rerun exact-head verification.

---

## C1 Definition of Done

C1 is complete only when all of the following are true:

1. `docs/completion/COMPLETION-LEDGER.md` exists and uses only the four approved states.
2. `exec-planning.md` current baseline is `786579a048574dbf52d4807d3bc1c7923b08a27a` or a newer exact head produced by the C1 branch, with no stale active residuals for already-merged PR #88–#101 work.
3. `ROADMAP-NEXT.md` no longer authorizes stale PR #6/Python-3.9-era work as current execution.
4. DR documentation matches the fail-closed/dry-run/retention behavior merged in PR #93.
5. Supply-chain docs match actual `uv sync --locked`, cosign, SBOM, per-arch SBOM, release-tag, and Helm-package implementation.
6. Historical EP11/EP11b/EP12-13 evidence is explicitly historical and is not used as current final-RC proof.
7. Remaining repository-owned implementation gaps map cleanly to C2/C3/C4/C6; final qualification/environment gaps map to C5.
8. No production source, workflow, test, dependency, or security gate changes are included in the C1 PR.
9. Exact-head hosted verification for the C1 PR is green before merge.
