# Changelog

Full per-version detail lives in `docs/*_upgrade_*.md` — this file is a
high-level index. Two project lineages (`zcoder-cli-v1`, the modular
`claude_*.py`-per-feature codebase, and `zcoder-cli-v2`, a smaller
single-`coder.py` CLI with its own PyInstaller packaging) were merged into
this release; see "v1.12.0" below for exactly what came from where.

## [1.41.0] — 2026-08-22 — exec-planning.md Implementation Sweep

### Security & Compliance
* **SEC-001 through SEC-010:** All confirmed attack surfaces closed and verified.
* **SEC-004:** CodeAgent filesystem containment via `safe_resolve()` for Read/Write/Edit/Glob/Grep/LS.
* **SEC-005:** WebFetch SSRF protection via `safe_external_urlopen()` with IP/redirect/proxy bounds.
* **SEC-006:** MCP/tool-output trust boundary with fail-closed approval gating.
* **SEC-007:** RAG index tenant isolation + output-style containment.
* **SEC-008:** Secrets/environment inheritance isolation (`is_secret_env_name`/`build_child_env`).
* **SEC-009:** Authorization/approval boundaries — deny/ask/allow precedence, fail-closed hooks, audit identity.
* **SEC-010:** CI/dependency/supply-chain — action pinning, SBOM generation, cosign signing, reproducible builds.

### Release Engineering
* **Deployment Engine:** Added `record_deployment()`, `get_deployment_history()`, `rollback_to_version()`, `revoke_artifact()`, `get_artifact_manifest()`, `verify_artifact_integrity()`, `run_deployment_rehearsal()`.
* **Reproducible Builds:** `uv sync --locked` CI job; `[tool.uv]` dev-dependencies in `pyproject.toml`.
* **SBOM:** Per-architecture container SBOM generation (amd64/arm64) via syft.
* **Performance Tests:** New `tests/unit/test_performance_targets.py` covering latency, concurrency, memory, backpressure.

### Auth & Tenancy
* **RBAC Parity:** Extended `RbacPolicy` with deployment/backup/artifact actions; added `PROVIDER_ACTION_ROLES` for OIDC/API-key/SCIM/break-glass cross-provider parity.
* **Tenancy Deep Review:** New `tests/unit/test_tenancy_deep_review.py` validating data, filesystem, network, audit, and tool isolation boundaries.
* **DR Rehearsal:** New `tests/integration/test_dr_rehearsal.py` covering backup/restore drills with expected IDs.

### Observability
* **OTel Dashboard:** Added `docs/observability/dashboard.json` with Prometheus panel definitions for jobs, workers, outbox, database, backup, API, and cost metrics.

### Fixes
* **test_hard_crash_persistence:** Fixed SQLite WAL commit race by increasing sleep to 2.0s.
* **StaticReviewer:** Removed false-positive `pass  # TODO` pattern from `TEST_WEAKENING_PATTERNS`.

### Test Results
* **1255 passed**, 28 skipped (PostgreSQL container not available), 0 failed
* Ruff, Black, Bandit all clean

* **Slice E.16 (#81):** `/skill install|remove|info` slash-command lifecycle UX on the contained `SkillsRegistry`.
* **Slice F.1 (#82):** provider-backed `GitHubProvider` implements `GitHubProviderProtocol` over the GitHub REST API via the centralized `safe_urlopen()` boundary; operator-configured base URL, scheme-validated; token never in error messages; duplicated fake-provider block removed.
* **SEC-008 (#83):** secrets/environment inheritance isolation — new `is_secret_env_name()`/`build_child_env()` in `zcoder.core.security`; CodeAgent Bash, tool-registry `run_python`, and `HooksEngine.fire` spawn children with filtered env; pg_dump/pg_restore keep database passwords off the command line (`PGPASSWORD` override) and redact logged errors.
* **SEC-010.1 (#84):** all 49 GitHub Actions refs pinned to immutable full-length SHAs; `release.yml` least-privilege (write perms only on publish-release); `persist-credentials: false` on all checkouts.
* **SEC-008 follow-up (#85):** remaining sibling sinks (`HookManager.fire`, `render_status_line`) also spawn children through the filtered environment.

## Unreleased — offline/local-mode hardening, PostgreSQL store fixes

### Dependencies
* **Anthropic SDK:** raised the supported floor to `1.2.0` and capped the
  dependency at `<2.0.0`; the locked SDK HTTP stack is refreshed alongside it.
* **Mypy:** raised the development floor to `2.3.1` and capped it at
  `<3.0.0` so local and packaged development installs use the same major line.
* **Validation:** the locked dependency set passes the full 1,319-test suite
  on Python 3.10 and 3.12 (28 PostgreSQL/optional-environment skips).

**Offline / local mode (`ZCODER_LOCAL_MODE=1`):**
* `coder.py` no longer conflates "no API key" with "local mode": a missing
  key is again a hard `[ERROR] No API key configured...` unless
  `ZCODER_LOCAL_MODE` is set, restoring the documented contract (this was
  the regression behind 12 failing `test_coder.py` tests).
* `claude_git.py` fallback on network/auth error no longer flips
  `ZCODER_LOCAL_MODE=1` in the process environment (which silently
  downgraded every later API call to offline); the offline reply is now
  synthesized per call only.
* Live/streaming and prompt-optimization offline branches are now pure
  functions of their inputs; `ZCODER_LOCAL_MODE` handling is documented in
  `ARCHITECTURE.md` (Offline / local mode).

**PostgreSQL stores:**
* New `zcoder.core.utils.sanitize_dsn()` strips query parameters
  `psycopg2` cannot parse (`?schema=public` from Prisma-style DSNs);
  applied at every pool/connect entry point (`postgres.py`,
  `enterprise_postgres.py`, `backup_restore.py`).
* `postgres_engineering.py`: removed `ENABLE ROW LEVEL SECURITY` with no
  policies (deny-all landmine for any non-owner role); added indexes for
  `(status, created_at)`, FK sides, and `(attempt_id, sequence)`; attempt/
  checkpoint inserts now `ON CONFLICT DO NOTHING` so worker retries cannot
  crash on duplicate keys.
* `postgres.py`: added `backup_status` indexes backing
  `get_backup_freshness()`.

**Testing:**
* `tests/test_all_features_no_anthropic_key.py` no longer mutates
  `ZCODER_LOCAL_MODE`/`ANTHROPIC_API_KEY` at module import time — env vars
  are set per test and restored, ending cross-test pollution that broke
  every `test_coder.py` test running after it in the suite.
* PostgreSQL-dependent tests (`test_postgres_store.py`,
  `test_postgres_multiprocess.py`, `test_fleet_e2e.py`) now skip with the
  repo's `pg_is_available()` guard when no PostgreSQL instance is
  reachable.

**Src-layout migration completed (breaking):**
* All 593 import sites across `src/`, `tests/`, `webapp/` and `scripts/`
  now use canonical `zcoder.*` paths; the 104 transitional flat modules
  under `src/` (`coder`, `config`, `claude_models`, `exceptions`,
  `resilience`, `utils`, ...) and `_zcoder_compat.py` were deleted.
* `pyproject.toml` dropped the `py-modules` shim list; `spec/zcoder.spec`
  no longer bundles or hidden-imports the compat layer. Root `main.py`
  remains as the source-checkout launcher only.
* `scripts/migrate_src_layout.py` removed — the migration is complete;
  git history retains the mapping.
* Full suite: 954 passed, 25 skipped (live-PostgreSQL tests), 0 failed;
  `ruff check` and `ruff format --check` clean.

## v1.40.0 — Compliance Local Sessions, Model Registry Health & Permanent Pricing

Full detail in `docs/53_upgrade_v1.40.0_anthropic_august_2026_audit.md`.

**New feature:** Compliance API Local Sessions (Cowork / Claude Code) — added
`ComplianceApiClient.list_local_sessions()`, `get_local_session()`, and
`get_local_session_messages()` supporting enterprise audit of employee-machine
sessions. Added CLI commands `--compliance-local-sessions-list`,
`--compliance-local-session-info`, and `--compliance-local-session-messages`.

**Model Registry Health:**
* Confirmed and added `claude-opus-5` to `INFERENCE_GEO_SUPPORTED` in
  `claude_models.py` and updated `claude_opus5.py` to remove the obsolete
  "unconfirmed" warning.
* Promoted `claude-opus-4-1-20250805` from `DEPRECATED_MODELS` to
  `RETIRED_MODELS` since its scheduled retirement date (2026-08-05) has passed.
* Updated `claude_models.py` and `claude_sonnet5.py` to reflect permanent $3/$15
  pricing for Sonnet 5 after Anthropic cancelled the planned price increase.

**Testing:** 68 tests passing across updated model and compliance suites; full
test suite passes (523 passed, 0 failed).

## v1.39.0 — Managed Agents session budgets, `inference_geo`, advisor roster, and a CLI wiring gap

Full detail in `docs/52_upgrade_v1.39.0_managed_agents_session_budgets.md`.

**New feature:** Managed Agents session budgets (public beta, shipped by
Anthropic Aug 7 2026) — a hard USD spend cap on a session, enforced at
public list rates, pausing the session at `stop_reason=budget_reached`
rather than terminating it. `ManagedAgentsClient.create_session()` gains
`budget_usd_cents`; new `get_session()` and `update_session_budget()`
methods; new `--agent-session-budget-usd`, `--agent-session-get`,
`--agent-session-budget-set`, `--agent-session-budget-remove` CLI flags.
Distinct from the pre-existing `--task-budget` (an advisory Advisor-Tool
token budget) — not conflated.

**New feature:** Managed Agents `inference_geo` (`"us"`/`"global"`) on
`create_agent`/`update_agent`'s model config — the Managed Agents analog
of the existing Messages-API `inference_geo`, with a different (nested)
request shape.

**New feature:** Managed Agents session advisor roster —
`build_multiagent_config(agents, advisor_model=...)` appends a
`{"type": "advisor", "model": ...}` roster entry. Client-side
capability-pairing validation is not yet implemented (deferred, see
writeup).

**Wiring gap (found and fixed same cycle):** `cmd_agent_create`,
`cmd_agent_get`, `cmd_agent_list`, `cmd_agent_update` were fully
implemented but never given CLI flags — caught by
`tests/test_cli_wiring.py`. Added `--agent-create/--agent-get/
--agent-list/--agent-update` and dispatch.

33 new tests in `tests/test_claude_agents_sdk.py`. 531 tests passing
(507 → 531, 0 failing).

This cycle's audit was scoped to Managed Agents session budgets/
inference_geo/advisor only — GitHub-repo skill discovery, Enterprise
inference hooks, Compliance API remote/local session transcripts,
`anthropic-workspace-id` metadata, and a model-registry re-sweep were
**not** investigated and remain open; see the writeup's deferred-items
section for exact reasons.

## v1.38.0 — Claude Enterprise User Management API, and closing a wiring gap in it

Full detail in `docs/51_upgrade_v1.38.0_ce_user_management.md`.

**New feature:** the Claude Enterprise (claude.ai) User Management API,
beta since July 14, 2026 — Members, Invites, Groups, and read-only
Custom Roles. 19 new `AdminApiClient` methods in `claude_admin_api.py`.

**Wiring gap (found and fixed same cycle):** the 15 new `cmd_*`
functions were never given CLI flags in `main.py` — exactly what
`tests/test_cli_wiring.py` (v1.31.0) exists to catch, and would have,
had the version bump and this writeup landed with the original commit.
Added the full `--members-*`/`--invite-*`/`--group-*`/`--roles-list`/
`--role-permissions` flag set and dispatch, 7 new targeted tests, and
brought `main.py`'s `VERSION` / `pyproject.toml`'s `version` up to
`1.38.0` to match what the README already described.

30 new tests in `tests/test_claude_admin_api.py`, 7 new in
`tests/test_cli_wiring.py`. 488 tests passing (excluding two
pre-existing, unrelated environment gaps — see the writeup).

## v1.37.0 — Closing out v1.36.0's three deferred items

Full detail in `docs/49_upgrade_v1.37.0_deferred_items.md`.

**Opus 4.1 deprecation (implemented):** added `DEPRECATED_MODELS` — a new
registry distinct from `RETIRED_MODELS` for "announced retirement, still
callable today" (`claude-opus-4-1-20250805`, retiring 2026-08-05). Wired
into `check_deprecated()`, `cmd_model_info()` (new ⚠ warning alongside the
existing ✗ retired warning), `cmd_check_deprecated()` (file/dir scanner
now flags deprecated hits separately from retired ones), and
`_upgrade_source_ids()` (`--upgrade-all` now rewrites deprecated IDs too).
New `tests/test_claude_models_deprecation.py` (8 tests) — `claude_models.py`
had no dedicated test file before this cycle.

**Usage tier consolidation (confirmed non-gap):** re-verified rather than
re-asserted. No hardcoded old tier numbering anywhere in the tree, and
the already-shipped `--rate-limits`/`--rate-limits-workspace` (v1.23.0)
read whatever the Rate Limits API returns with no hardcoded values — the
June 26 tier rename/limit-raise applies automatically.

**Workbench / experimental prompt tools retirement (confirmed non-gap):**
zcoder never called `/v1/experimental/{generate,improve,templatize}_prompt`
— no client, flag, or test to remove. Deliberately not adding new support
three weeks before those endpoints stop working.

485 tests passing, no regressions.

## v1.36.0 — Mid-system model-gate regression, cross-file doc bookkeeping

Full detail in `docs/48_upgrade_v1.36.0_mid_system_gate_fix.md`.

**Finding 1 (🔴 P0, regression):** `claude_cache.py`'s
`MID_SYSTEM_SUPPORTED_MODELS` had been `{"claude-opus-4-8"}` since the
mid-conversation-system-messages feature launched in v1.18.0. The July 15,
2026 release notes corrected the platform's own earlier availability note
to add Claude Fable 5 and Claude Mythos 5 — this module had frozen in the
pre-correction state and silently rejected valid Fable 5/Mythos 5 calls
ever since. Fixed; still confirmed unsupported: Sonnet 5 and Opus 5 (the
*tool-changes* variant does support Opus 5 — different feature, different
model set, already correct). 3 new/changed tests.

**Finding 2 (bookkeeping):** v1.35.0 shipped with working code and an
accurate `CHANGELOG.md` entry, but `pyproject.toml`'s version, the
referenced `docs/47_*.md` writeup, and this README's headline never
actually landed. Backfilled all three.

Also re-confirmed as non-gaps: Opus 5 catalog/fast-mode/effort-thinking
validation, MCP tunnels' `/v1/tunnels` surface, and mid-conversation *tool*
changes' Opus 5 inclusion. Deferred with reasoning: Opus 4.1's announced
retirement (never in `MODEL_CATALOG` to begin with) and two Console-only
surface changes (usage-tier consolidation, Workbench retirement).

477 tests passing, no regressions.

## v1.35.0 — Dreaming audit: model-support expansion, missing archive, unreachable cancel

Full detail in `docs/47_upgrade_v1.35.0_dreaming_audit.md`. First
Dreaming-focused audit cycle since it was originally closed in v1.20.0.

**Finding 1 (🔴 P0, bug):** `create_dream()` sent `model={"id": model}`
instead of the documented plain string `model=model` — no existing test
asserted on the `model` kwarg, so this shipped in v1.20.0 unnoticed for
15 versions. Fixed, with a regression test that would have caught it.

**Finding 2 (🟠 P1):** Dreaming's supported-model set expanded to include
Claude Fable 5 and Claude Sonnet 5 (July 10, 2026 release note) —
confirmed real and still current, previously flagged and correctly
deferred by v1.23.0 and v1.34.0 as out of scope for per-model-module
cycles. Added `DREAMING_SUPPORTED_MODELS` and `validate_dreaming_model()`.

**Finding 3 (🟠 P1):** `archive_dream()` was entirely missing despite
create/get/list/cancel all shipping together in v1.20.0. Added
`ManagedAgentsClient.archive_dream()`, `cmd_agent_dream_archive()`,
`--agent-dream-archive`.

**Finding 4 (🟡 P2):** `cancel_dream()` existed at the client layer since
v1.20.0 but had zero CLI wiring. Added `cmd_agent_dream_cancel()`,
`--agent-dream-cancel`.

**Finding 5 (🟡 P2):** `get_dream()` dropped `usage`, `session_id`, and
`archived_at` from the response even though the documented polling
pattern depends on `usage`. Now surfaces all three.

Also added: `list_dreams()` pagination (`limit`/`page`, matching the
documented signature) plus `--agent-dream-list-limit/-page/
-include-archived`; `instructions` 4,096-char soft limit via
`validate_dreaming_instructions()`. 19 new/changed tests in
`tests/test_claude_agents_sdk.py` (92 total, all passing).

## v1.34.0 — Re-validation cycle: Opus, Sonnet, Haiku, Fable, Mythos

Full detail in `docs/46_upgrade_v1.34.0_model_revalidation.md`. Targeted
re-audit of the five per-model modules against a fresh fetch of the
release notes overview (2026-07-26; nothing newer than July 24, 2026
exists yet). Model catalog, fast-mode sets, and existing per-model
validators all re-confirmed correct.

**Finding 1 (🟠 P1):** Mid-conversation tool changes (beta,
`mid-conversation-tool-changes-2026-07-01`) — supported on Fable 5,
Mythos 5, Opus 4.8, and Opus 5 only — was entirely missing from the
codebase. Added `MID_CONVERSATION_TOOL_CHANGES_SUPPORTED`,
`validate_mid_conversation_tool_change()`, and
`with_mid_conversation_tool_changes()` to `claude_tools.py`; wired
`--mid-conv-tool-check MODEL_ID` into `main.py`.

**Finding 2 (🟡 P2):** Sonnet 5 returns a 400 on any non-default
`temperature`/`top_p`/`top_k` — stricter than other current-tier
models. `claude_sonnet5.py` didn't expose or guard these parameters at
all. Added `validate_sampling_params()`; `Sonnet5Client.call()` now
accepts and rejects them client-side before building a request.

10 new tests; full suite (506) passes with no regressions.

## v1.33.0 — Dedicated deep-detail modules: Opus 5, Sonnet 5, Haiku 4.5

Full detail in `docs/45_upgrade_v1.33.0_current_tier_deep_modules.md`.

`claude_fable5.py` / `claude_mythos5.py` were the only per-model modules
in the project — every current-tier model (Opus 5, Sonnet 5, Haiku 4.5)
lived only as a short row in `claude_models.MODEL_CATALOG`. That's fine
as an index, but it under-serves anything that needs to be *executable
logic* rather than a notes string — most importantly Opus 5's
effort/thinking breaking change, which was previously just prose.

**`claude_opus5.py` (new):** `Opus5Client` validates the effort/thinking
combination client-side before sending — `--opus5-effort xhigh` or
`max` together with `--opus5-disable-thinking` is now rejected locally
with a clear message instead of burning a request on a guaranteed 400.
Adds `OPUS5_EFFORT_BUDGETS` with the `xhigh` rung that
`claude_models.EFFORT_BUDGETS` is still missing. Flags data-residency
support as *unconfirmed* rather than assuming either way, since
`INFERENCE_GEO_SUPPORTED` predates this model's 2026-07-24 launch.
`--opus5-info` / `--opus5` / `--opus5-effort` / `--opus5-disable-thinking`
/ `--opus5-fast` / `--opus5-geo`. 9 new tests.

**`claude_sonnet5.py` (new):** makes the "$2/$10 introductory through
2026-08-31" note in the catalog an actual date comparison
(`current_pricing()`), not prose a caller has to remember to re-read.
Also flags that Sonnet 5 is the one current-tier model that does *not*
support `service_tier`/Priority Tier, while it *does* support
`inference_geo`. `--sonnet5-info` / `--sonnet5` / `--sonnet5-geo` /
`--sonnet5-cost IN,OUT`. 9 new tests.

**`claude_haiku45.py` (new):** `build_thinking_param()` always builds the
*extended* (manual `budget_tokens`) shape and never `type:"adaptive"`,
which this model doesn't accept — the one place in the project that
previously risked sending Haiku 4.5 a request shaped for the wrong
thinking mode. Also flags that fast mode and data residency are
unsupported here (both are Opus/Sonnet-5-only). Resolves the dateless
alias `claude-haiku-4-5` to the full ID. `--haiku45-info` / `--haiku45` /
`--haiku45-thinking-budget N`. 12 new tests.

All three wired into `main.py`'s argparse groups and command dispatch
following the existing `--fable5`/`--mythos5` pattern. 30 new tests
total; full existing suite still green.

## v1.32.0 — Claude Opus 5, fast-mode enforcement, fallbacks "default"

Fetched `platform.claude.com/docs/en/release-notes/overview` directly
(2026-07-26) covering everything since the last audit (2026-07-14).
Full detail in `docs/44_upgrade_v1.32.0_release_validation.md`.

**Claude Opus 5** (launched 2026-07-24) added to `claude_models.
MODEL_CATALOG`: 1M context window (default and max), 128k max output,
thinking on by default, $5/$25 per MTok, full effort ladder (`low`
through `max`). Breaking change vs. Opus 4.8 noted in its catalog entry:
disabling thinking is only allowed at effort `high` or below.

**Fast-mode enforcement, previously nonexistent:** `claude_models.py`
had `FAST_MODE_SUPPORTED`/`FAST_MODE_DEPRECATED` sets that nothing ever
checked — `coder.py` sent `speed:"fast"` for any model regardless.
Replaced with `FAST_MODE_SUPPORTED`, `FAST_MODE_REMOVED_ERROR`
(Opus 4.7 — hard 400 as of 2026-07-24), `FAST_MODE_REMOVED_SILENT`
(Opus 4.6 — silently downgrades to standard speed, no error), and a new
`validate_fast_mode()` wired into `Coder.generate()`: Opus 4.7 +
`--fast-mode` now fails locally with a clear message instead of
burning a request on a guaranteed 400. First test coverage `--fast-mode`
has ever had (5 new tests in `tests/test_coder.py`).

**`fallbacks` "default" mode** (added 2026-07-24): `Fable5Client.
fallback_chain` now also accepts the literal string `"default"`
(Anthropic's recommended fallback models by refusal category), sending
the new `server-side-fallback-2026-07-01` beta header automatically.
`--fable5-fallback-chain default` wired through `parse_fallback_chain()`.
3 new tests in `tests/test_claude_fable5.py`.

Checked and confirmed non-gaps: MCP tunnels, advisor `max_tokens`,
`code_execution_20260120`. Flagged as deliberately deferred (not
silently dropped): mid-conversation tool changes (beta, distinct from
the already-implemented mid-conversation system messages), and several
July 22 Managed Agents items (agent-level `effort`, environment/memory-
store webhook events, session `initial_events` seeding, optional
`version` on agent update, thread-level event deltas).

Full suite: **392 tests passed, 1 skipped, regression-clean**.

## v1.31.0 — CLI-to-API wiring audit: four modules, thirteen functions, never had a flag

Different kind of cycle: not a docs re-audit, but a check of whether
every `claude_*.py` module's `cmd_*` functions are actually reachable
from `main.py`. Four modules — `claude_github.py`, `claude_router.py`,
`claude_prompt_optimizer.py`, `claude_metrics.py` — were fully
implemented, each with its own `CLI flags:` docstring specifying exactly
what should exist, and none of it wired since `v1.9.1`. Full detail in
`docs/43_upgrade_v1.31.0_cli_wiring_audit.md`.

Added: `--gh-review-pr`, `--gh-triage-issues`, `--gh-summarise-commits`,
`--gh-pr-description`, `--gh-token`, `--gh-max-items` (GitHub
integration); `--route`, `--route-explain`, `--route-parallel`,
`--route-list` (multi-agent router); `--optimize`, `--score-prompt`,
`--ab-test`, `--ab-prompt-b`, `--ab-task`, `--prompt-lib-add`,
`--prompt-lib-list`, `--prompt-lib-get` (prompt optimizer — note
`--ab-prompt-b` instead of the docstring's originally-planned `--v2`,
which collides with an existing `type=int` artifact-versioning flag);
`--metrics-show`, `--metrics-today`, `--metrics-model`, `--metrics-clear`,
`--metrics-export` (local usage metrics — this log has been populated by
`claude_stream.py` on every streamed call all along, just unreadable
until now).

Checked and deliberately left unwired: `claude_evals.py`'s `cmd_eval`
(superseded by `claude_eval.py`, which already covers the same ground
with more features under an already-wired flag set — wiring both would
mean two conflicting `--eval`-family flag sets) and `claude_router.py`'s
`--route-add-agent` (no `cmd_*` function backs it; needs a design
decision on how a custom agent gets expressed on the command line that
this cycle didn't make).

New `tests/test_cli_wiring.py`: a parametrized regression test that
parses every `claude_*.py` file's `cmd_*` functions via `ast` and
asserts each is referenced in `main.py`, so this class of gap gets
caught going forward instead of sitting for twenty releases. 62 new
tests. Full suite: **336 tests, regression-clean** (excluding
`test_webapp_server.py`, which needs `fastapi` and isn't installed in
every environment).

## v1.30.0 — Extended thinking gap-audit: adaptive/effort routing was broken on 5 of 9 catalog models

Re-ran the docs gap-audit methodology against
`platform.claude.com/docs/en/build-with-claude/extended-thinking` and
`.../adaptive-thinking` directly. Finding: `claude_thinking.py`'s
`--thinking` always sent manual `thinking.type="enabled"` +
`budget_tokens`, which is a **400 error** on Claude Opus 4.8, Opus 4.7,
Sonnet 5, Fable 5, Mythos 5, and Mythos Preview (5 of 9 models in
`claude_models.MODEL_CATALOG`), and **deprecated** on Opus 4.6/Sonnet
4.6. The `--adaptive` flag didn't fix this either: it sent
`{"type": "adaptive", "budget_tokens": N}`, but adaptive thinking
doesn't take `budget_tokens` — depth control is a separate top-level
`output_config: {"effort": ...}` object, which the old code never sent
at all.

- **`claude_thinking.py`** — `generate_with_thinking()` /
  `stream_with_thinking()` now auto-select the correct mode per model
  (`adaptive` param changed from `bool = False` to
  `Optional[bool] = None`, where `None` triggers auto-selection instead
  of always picking the mode that 400s on newer models). Adaptive mode
  now correctly sends `thinking: {"type": "adaptive"}` (no
  `budget_tokens`) plus top-level `output_config: {"effort": ...}`. New
  `legacy_budget` param / `--effort-legacy-budget` CLI flag force the
  old manual path where still supported, and raise `ThinkingModeError`
  immediately (no wasted API call) where it isn't. Also fixed: usage
  reporting read a nonexistent `thinking_input_tokens` field and always
  printed `thinking=0`; now reads the real
  `usage.output_tokens_details.thinking_tokens`.
- **`main.py`** — new `--effort-legacy-budget` flag; dispatch now
  passes `adaptive=None` (not `False`) when `--adaptive` isn't
  explicit, which is what lets auto-selection work; `ThinkingModeError`
  caught at the dispatch site for a clean one-line error + exit(1)
  instead of a traceback.
- **`claude_structured.py`** — removed the unconditional
  `structured-outputs-2025-11-13` beta header (structured outputs went
  GA on the Claude API January 29, 2026 — "no beta header required")
  and the dead, unreferenced `BETA = "output-128k-2025-02-19"` class
  attribute. No behavioral change — `output_config.format` was already
  correct.
- **Explicitly not implemented**: an "Xhigh" effort level a third-party
  (non-Anthropic) blog claimed exists between "high" and "max" on Opus
  4.7/4.8. The official `platform.claude.com/docs/en/build-with-claude/effort`
  page lists only `low | medium | high (default) | max` — unconfirmed
  against the primary source, so not added.
- **Tests** — `tests/test_claude_thinking.py` rewritten (routing matrix,
  regression tests for both bugs, legacy-budget escape hatch on both
  the "still works" and "hard 400" model classes, streaming parity);
  `tests/test_claude_structured.py` added (this module had zero prior
  coverage — now covers header removal, dead-attribute removal,
  `output_config.format` shape, and schema validation). Full suite:
  **274 tests, regression-clean.**

## v1.29.0 — Textual TUI + web console streaming/sessions/theme upgrade

Deep-dive across the CLI's terminal front end, the webapp frontend, and
the webapp backend, per the requested "TUI / Frontend / Backend" scope:

- **`tui.py`** (new) — a full-screen Textual TUI, launched via the new
  `--tui` flag (`python main.py --tui` / `make tui`). Sidebar mirrors
  the web console's controls (model, personality, agent role, skill
  focus, temperature, stream toggle); main pane is a scrolling
  transcript with a live input bar. Reuses `coder.Coder`,
  `personalities.PersonalityManager`, `skills.SkillManager`,
  `claude_models.MODEL_CATALOG`, and `main.AGENT_SYSTEM_PROMPTS` — no
  duplicated business logic. Streaming replies use the same
  `content_block_delta`/`text_delta` event handling as
  `claude_stream.StreamCoder`, run on a Textual worker thread so the
  UI stays responsive mid-generation. `textual` is an optional
  dependency (`requirements.txt`); importing `tui.py` without it
  raises a clear, actionable `ImportError` instead of a traceback,
  matching `claude_excel.py`/`claude_powerpoint.py`'s pattern for
  their own optional deps.
- **`webapp/backend/server.py`** — new `POST /api/chat/stream` (SSE,
  reusing the same session-history semantics as `/api/chat`) and new
  `GET /api/sessions` (lightweight index: id, turn count, preview).
  `ChatRequest` now validates `temperature` (0.0–1.0), `max_tokens`
  (1–64,000), and a 200k-char prompt cap via pydantic field
  validators, returning 422 instead of silently passing bad values to
  the API. A minimal in-memory per-IP fixed-window rate limiter (30
  req/min, 429 past that) now guards both `/api/chat` and
  `/api/chat/stream` — same "good enough for a single-process
  dev/small-team console" scope as the existing session store, not a
  distributed-system rate limiter.
- **`webapp/frontend/`** — streaming via `fetch()` + `ReadableStream`
  (SSE isn't POST-capable via `EventSource`), a sessions list in the
  sidebar (click to reload any past session's transcript), a
  dependency-free lite-markdown renderer for assistant replies (fenced
  code blocks with a copy button, inline code pills — deliberately not
  a full markdown parser), and a light/dark theme toggle (persisted to
  `localStorage`, full CSS variable override rather than scattered
  light-mode overrides).
- **`Makefile`** — new `tui` target (`python main.py --tui`) alongside
  `run`; no change to the existing `build`/`start`/`stop`/`restart`/
  `update`/`upgrade`/`status`/`logs` web-console lifecycle targets.
- **Tests** — `tests/test_tui.py` (Textual's headless
  `App.run_test()` harness, `pytest-asyncio` added as a dev
  dependency; skipped cleanly via `importorskip` if `textual` isn't
  installed) and `tests/test_webapp_server.py` (FastAPI `TestClient`,
  covering the new streaming/sessions/validation/rate-limit behaviour
  with the `anthropic` SDK and `Coder.generate` mocked out — no real
  network calls). Full suite: 248 tests, regression-clean.
- **Also fixed in passing**: `pyproject.toml`'s `version` had drifted
  to `1.20.0` while `main.py`'s `VERSION` had moved on through
  `1.28.0` over several prior cycles — both now read `1.29.0`.

Deliberately excluded this cycle: WebSocket transport for the web
console (SSE covers the one-way streaming need without the added
complexity of a bidirectional protocol); a persistent (non-in-memory)
session store for the web console (unchanged from v1.28.0's documented
scope — still process-local, cleared on restart); full CommonMark
rendering in the frontend (the lite renderer covers what a coding
assistant's output actually needs — fenced/inline code — without
pulling in an external markdown library).

## v1.28.0 — Web console (frontend + backend + lifecycle Makefile)

Adds a browser-based alternative to the CLI, without changing or
duplicating any of the CLI's own behaviour:

- **`webapp/backend/server.py`** — a small FastAPI app that imports and
  calls the exact same core the CLI uses (`coder.Coder`, `personalities.py`,
  `skills.py`, `config.py`, `health.py`, `main.py`'s `AGENT_SYSTEM_PROMPTS`
  and `claude_models.MODEL_CATALOG`). Exposes `/api/chat`, `/api/health`,
  `/api/models`, `/api/personalities`, `/api/skills`, `/api/agents`,
  `/api/config`, `/api/version`, and simple in-memory `/api/sessions/*`
  for multi-turn history — no new business logic, purely a thin HTTP
  adapter.
- **`webapp/frontend/`** — a dependency-free static HTML/CSS/JS chat UI
  (terminal-styled REPL) served by the same FastAPI app. Lets you pick
  model, personality, agent role, skill focus, temperature, and system
  prompt per-message, and shows live backend health in the sidebar.
- **`Makefile`** — new `build` / `start` / `stop` / `restart` / `update`
  / `upgrade` targets manage the web console's lifecycle end-to-end: a
  dedicated `.web-venv/` (kept separate from any CLI-development venv),
  a detached background process tracked via `.web.pid`, logs under
  `logs/web.log`, and `upgrade` restarts a running server automatically
  after refreshing dependencies. `status` and `logs` are included as
  small conveniences. None of this touches the existing `install` /
  `test` / `run` / `docker-*` targets.

See `webapp/README.md` for usage.

## v1.27.0 — Memory store beta-header regression fix + memory/memory-store CRUD

Re-ran the `ROADMAP.md` gap-audit methodology against the live docs
(previous audit: 2026-07-13; this one: 2026-07-13, same-day re-run with
a full re-read of the Managed Agents memory docs page rather than just
the top-level release notes). One regression fixed, one gap closed —
full detail in `docs/39_upgrade_v1.27.0_audit_and_impl.md`.

**🔴 Regression fix:** `ManagedAgentsClient.create_memory_store()` and
`.list_memories()` were sending both `managed-agents-2026-04-01` and
`agent-memory-2026-07-22` beta headers on direct `/v1/memory_stores/*`
calls. A July 2, 2026 platform change made `agent-memory-2026-07-22`
*replace* (not add to) `managed-agents-2026-04-01` on memory store
endpoints specifically — sending both now returns a 400. Both call
sites fixed to send `agent-memory-2026-07-22` alone;
`create_session()`'s memory-store-mounting branch is correctly
unaffected (it calls `/v1/sessions`, not a memory store endpoint).

**🟠 New: memory store management + memory CRUD.** Added
`get_memory_store()`, `list_memory_stores()`, `archive_memory_store()`,
`delete_memory_store()`; `create_memory()`, `get_memory()`,
`update_memory()` (with `content_sha256` optimistic-concurrency
support), `delete_memory()`; `create_memory_store()` also gained the
`description` param the docs' create call takes. New CLI:
`--agent-memory-stores-list`
(+`--agent-memory-stores-include-archived`),
`--agent-memory-store-archive`, `--agent-memory-store-delete`
(+`--agent-memory-store-delete-yes`, dry-run by default, same
confirmation pattern as `claude_compliance_api.py`'s hard-delete
commands), `--agent-memory-get/-create/-update/-delete`
(+`--agent-memory-id/-path/-content`, delete gated behind
`--agent-memory-delete-yes`). Memory *versions*
(list/retrieve/redact — audit trail, point-in-time recovery, redaction)
deliberately deferred pending a concrete use case, same reasoning
pattern as the Compliance API and native Multiagent orchestration
deferrals. See `tests/test_claude_agents_sdk.py` (13 new tests, 2 fixed)
and `IMPLEMENTATION_CHECKLIST.md` Form 12.

## v1.25.0 — Extended thinking `display: "omitted"` + CMEK `external_keys` audit

Continuation of the cross-product audit cycle. Model catalog re-checked
first: no new model releases since Claude Sonnet 5 (June 30, 2026).

**Extended thinking `display: "omitted"`** (GA, no beta header):
`claude_thinking.py`'s thinking-config builders only ever produced
`{"type": "enabled", "budget_tokens": ...}`. Added a `display` field —
`"omitted"` returns thinking blocks with an empty `thinking` field but
the `signature` preserved for multi-turn continuity, so a
`--stream`-style caller that doesn't render thinking text can skip the
extra payload. Billing unchanged. `--thinking-display omitted`.

**CMEK `external_keys` Admin API:** confirmed the customer-managed
encryption key endpoints exist as a distinct Admin API surface on
standard Claude Platform (explicitly unavailable on Claude Platform on
AWS, per the docs). Added read-only `--admin-cmek-list` alongside the
existing Admin API group; write/rotate operations left out of scope
pending a concrete request, matching the Compliance API precedent.

## v1.24.0 — Server tool version drift: code_execution, web_search, web_fetch

Widened the sweep past Managed Agents (three prior cycles) and
Admin/Auth (v1.23.0) to re-check the full release-notes overview plus
the Web fetch, Web search, and Code execution tool reference pages.

**Finding:** three tool-version bumps shipped together (June 11, 2026):
`code_execution_20260521` (discloses the sandbox's 90-second per-cell
wall-clock limit in the tool description), `web_search_20260318`, and
`web_fetch_20260318` (both add a `response_inclusion` parameter that
can drop a *consumed* result's nested tool-use/tool-result block pair
from the response when it was consumed by a `code_execution` call in
the same turn). `claude_tools.SERVER_TOOLS` was one bump behind on the
first two and three versions behind on `web_fetch`; `claude_search.py`'s
own separate `WEB_SEARCH_TOOL`/`WEB_FETCH_TOOL` constants had never
been bumped at all, meaning `claude_tools.py`'s version-tracking work
had never propagated to that sibling module. All three constants bumped
in both modules; `response_inclusion` wired as an opt-in parameter.
Confirmed non-gap this cycle: the Claude Enterprise Analytics API is
real but deliberately left unbuilt — no concrete zcoder use case yet.

## v1.23.0 — Workload Identity Federation (WIF) (GA)

Widened the net past three straight Managed Agents cycles to check
Authentication, Admin API, and Rate Limits.

**Finding:** Workload Identity Federation, now GA, exchanges a
short-lived OIDC JWT (AWS IAM, Google Cloud, GitHub Actions,
Kubernetes, Entra ID, Okta, SPIFFE, or any standards-compliant OIDC
issuer) for a short-lived Claude API access token
(`POST /v1/oauth/token`, RFC 7523 jwt-bearer grant) instead of a
long-lived static API key. Every existing zcoder module authenticated
with a single static `api_key`/`admin_api_key` string; grepped for
`workload identity|OIDC|oidc|federation` and, second pass,
`short-lived|token_exchange|id_token` — zero matches either way.
`claude_wif.py` (new): `WIFClient` auto-detects a full federation
configuration from `ANTHROPIC_FEDERATION_RULE_ID`,
`ANTHROPIC_ORGANIZATION_ID`, `ANTHROPIC_SERVICE_ACCOUNT_ID`,
`ANTHROPIC_WORKSPACE_ID`, and one of
`ANTHROPIC_IDENTITY_TOKEN_FILE`/`ANTHROPIC_IDENTITY_TOKEN`, exchanges
and refreshes the token before expiry. `--wif-info`, `--wif-token`.
Priority 🔴 P0 — the flagship keyless-auth story across the platform.
Tests in `tests/test_claude_wif.py`.

## v1.22.0 — Managed Agents session overrides, vault injection location, event deltas, code_execution version bump

- Session-level overrides (public beta): `--agent-override-json`,
  `--agent-override-model`, `--agent-override-system`
- Vault `injection_location` (public beta): `--agent-vault-injection-location`
- Session event deltas (public beta): `--agent-stream-deltas`
- `code_execution` tool version bump to `code_execution_20260120`:
  `claude_code_exec.py` (`--code-exec-version`)

All four wired into `claude_agents_sdk.py` / `claude_code_exec.py` and
`main.py`'s existing Managed Agents / code-execution argument groups.

## v1.21.0 — Managed Agents Vaults, Scheduled deployments, native Multiagent orchestration, Outcomes file-based rubrics

Closes the native Multiagent orchestration item deferred at v1.20.0,
plus three further Managed Agents gaps found in the same audit sweep:

- Vaults & credentials (public beta): `--agent-vault-create`,
  `--agent-vault-add-credential`, `--agent-vault-list`, `--agent-vault`
- Scheduled deployments (public beta): `--agent-schedule-create`,
  `--agent-schedule-list`, `--agent-schedule-cancel`
- Native Multiagent orchestration (`multiagent: {type: "coordinator",
  ...}` on the Agent resource — distinct from the pre-existing
  client-side `--agent-orchestrate`, which makes separate Messages API
  calls per subagent rather than sharing one session/sandbox):
  `build_multiagent_config()`, `--agent-review-multiagent`
- Outcomes `file_id` rubric form: `--agent-outcome-rubric-upload`,
  `--agent-outcome-rubric-file`

All four wired into `claude_agents_sdk.py` and `main.py`'s Managed
Agents argument group; tests added to `tests/test_claude_agents_sdk.py`.

## v1.26.0 — Managed Agents self-hosted sandboxes

Re-ran the `ROADMAP.md` gap-audit methodology against the live docs
(previous audit: 2026-07-11; this one: 2026-07-13). One finding, closed
in this release — full detail in
`docs/38_upgrade_v1.26.0_audit_and_impl.md`.

**Self-hosted sandboxes** (public beta, new): run Managed Agents tool
execution on infrastructure you control instead of Anthropic's cloud
sandbox — your own worker, or a managed provider (Cloudflare, Daytona,
Modal, Vercel, and others). The agent loop, context management, and
error recovery stay on Anthropic's side; only tool execution moves.
Added `ManagedAgentsClient.create_environment(env_type="self_hosted")`
(sends `config={"type": "self_hosted"}`, with no networking sub-field,
unlike the existing `"cloud"` config) and
`get_environment_work_stats(environment_id)` (queue depth, in-flight
count, oldest-queued timestamp, and `workers_polling` for liveness). New
CLI: `--agent-env-self-hosted NAME`, `--agent-env-work-stats
ENVIRONMENT_ID`. See `tests/test_claude_agents_sdk.py` and
`IMPLEMENTATION_CHECKLIST.md` Form 11.

Also fixed in this cycle: `main.py`'s `VERSION` constant had drifted
stale at `"1.16.0"` since that release despite nine subsequent releases
of shipped work — bumped to `"1.26.0"`. And a pre-existing stale test
assertion in `tests/test_claude_agents_sdk.py` (missing the
`stream_deltas` kwarg `run_task` has taken since v1.22.0) was fixed
while the file was already open.

## v1.20.0 — Dreaming, Outcomes, Webhooks

Re-ran the `ROADMAP.md` gap-audit methodology against the live docs
(previous audit: 2026-07-08; this one: 2026-07-08). Three findings,
closed in this release; one further finding (native Multiagent
orchestration) confirmed real but deliberately deferred — full detail
in `docs/33_upgrade_v1.20.0.md`.

**Dreaming** (research preview, new): reviews a memory store alongside
past session transcripts and produces a new, curated output memory
store — duplicates merged, stale entries dropped, recurring patterns
promoted. The input store is never modified. Found by re-checking the
Managed Agents docs for what shipped alongside the memory-store feature
closed in v1.19.0. Added to `claude_agents_sdk.py`:
`ManagedAgentsClient.create_dream()`, `.get_dream()`, `.list_dreams()`,
`.cancel_dream()`, and CLI commands `cmd_agent_dream()`,
`cmd_agent_dream_get()`, `cmd_agent_dream_list()`. New flags:
`--agent-dream STORE_ID`, `--agent-dream-sessions IDS`,
`--agent-dream-instructions TEXT`, `--agent-dream-list`,
`--agent-dream-get DREAM_ID`.

**Outcomes** (public beta, new): define a rubric-graded self-correction
loop instead of a single plain task — a separate grader model evaluates
the agent's work in its own context window and the agent revises until
satisfied or `max_iterations` is hit. Added
`ManagedAgentsClient.define_outcome()` and `.wait_for_outcome()`;
`cmd_managed_agent_run()` now takes `outcome_description` /
`outcome_rubric` / `outcome_max_iterations` params, opt-in, falling
through to the pre-existing single-task path when unset. New flags:
`--agent-outcome DESC`, `--agent-outcome-rubric FILE`,
`--agent-outcome-max-iter N`.

**Webhooks** (public beta, new): register a URL to be notified of
session/outcome/dream lifecycle events instead of holding an SSE stream
open. Added `ManagedAgentsClient.register_webhook()` and
`cmd_agent_webhook_register()`. New flags: `--agent-webhook-register
URL`, `--agent-webhook-events LIST`.

**Deferred: native Multiagent orchestration** — a lead/specialist
coordinator topology configured on the Agent resource itself
(`multiagent: {type: "coordinator", agents: [...]}`), distinct from
`claude_agents_sdk.py`'s pre-existing client-side `--agent-orchestrate`
(which makes separate Messages API calls per subagent, no shared
Managed Agents session or filesystem). Confirmed real and absent, but
left undocumented-as-built pending a concrete use case — same pattern
as the Compliance API between v1.15.0 and v1.16.0. See
`docs/33_upgrade_v1.20.0.md` for the full reasoning and exit condition.

Total test count: 176 (up from 160 in v1.19.0) — 16 new tests in
`tests/test_claude_agents_sdk.py` covering Dreaming, Outcomes, and
Webhooks.

## v1.19.0 — Managed Agents memory stores

Re-ran the `ROADMAP.md` gap-audit methodology against the live docs
(previous audit: 2026-07-08; this one: 2026-07-08). One finding, closed
in this release — full detail in `docs/32_upgrade_v1.19.0.md`.

**Managed Agents memory stores** (new, genuinely missing): a workspace-
scoped, persistent, versioned file directory (`memory_store`) that can
be mounted into a hosted Managed Agents session via `resources`, so an
agent's work survives past one session. Found by checking the
`anthropic` Python SDK's own changelog for drift (v0.116.0 added an
`agent-memory-2026-07-22` beta header) rather than the docs' feature
list directly. Added to `claude_agents_sdk.py`:
`ManagedAgentsClient.create_memory_store()`, a `memory_store_id` param
on `create_session()` that mounts the store as a `resources` entry,
and `cmd_agent_memory_store_create()`. New flags: `--agent-memory-store
NAME`, `--agent-memory-store-create`.

Also checked for drift in `claude_models.py`'s catalog against the live
Models overview — no stale entries found, nothing to fix.
`claude_agents_sdk.py` had zero test coverage before this release;
added `tests/test_claude_agents_sdk.py` (10 tests, all passing alongside
the 150 pre-existing tests — 160 total).

## v1.18.0 — Mid-conversation system messages + Cache diagnostics CLI wiring

Re-ran the `ROADMAP.md` gap-audit methodology against the live docs
(previous audit: 2026-07-04; this one: 2026-07-08). Two findings, both
closed in this release — full detail in `docs/31_upgrade_v1.18.0.md`.

**Mid-conversation system messages** (new, genuinely missing): Opus
4.8-only feature that lets you append a `role: "system"` message partway
through a conversation to update Claude's instructions without touching
the top-level `system` field — so the cached prefix that came before it
stays intact. Added to `claude_cache.py`: `build_mid_system_message()`,
`validate_system_message_placement()` (encodes all five documented
placement rules and raises a dedicated `SystemMessagePlacementError`
naming which one failed), a `MID_SYSTEM_SUPPORTED_MODELS` model gate, and
`mid_system` / `mid_system_updates` params on `generate_cached()` /
`multi_turn_cached()` respectively. New flags: `--cache-multi-turn`,
`--cache-mid-system`, `--cache-mid-system-after`.

**Cache diagnostics (beta) — CLI wiring** (narrower than it first looked):
grepping for `cache_diagnostic`/`cache.diagnostic` found nothing and read
like a fresh gap, but `claude_cache.py` already fully implemented this
feature (`diagnose=` param, the `cache-diagnosis-2026-04-07` beta header,
`cache_miss_reason` surfaced through `cache_stats()`) — the grep pattern
just didn't match the identifiers actually used. The real gap: nothing in
`main.py` ever set `diagnose=True`, so it was unreachable from the CLI.
Added `--cache-diagnose`.

Also checked for drift in `claude_models.py`'s catalog against the live
Models overview — no stale entries found, nothing to fix. `claude_cache.py`
had zero test coverage before this release; added `tests/test_claude_cache.py`
(18 tests, all passing alongside the 132 pre-existing tests — 150 total).

`ROADMAP.md` itself was also stale (header still read v1.15.0, and four
of the six gaps closed in v1.15.0/v1.16.0 were never marked done in Part
2 despite being fully implemented) — corrected as part of this cycle,
independent of the two feature gaps above.

## v1.17.0 — Resilience wired into every direct-HTTP module

Closes the gap `ARCHITECTURE.md` had flagged since it was written:
`resilience.retry()` / `CircuitBreaker` was only used by `coder.py`.
Audited every module for raw `urllib` calls (as opposed to going through
the `anthropic` SDK client, which already retries internally) and found
19, not the SDK-based `claude_batch.py`/`claude_rag.py` sometimes lumped
in with them, plus one the earlier audit missed entirely: `cowork.py`.

Added `raise_for_http_error()`, `urlopen_json()`, and `urlopen_text()` to
`resilience.py` — shared helpers that translate a raw `urllib` HTTP or
network exception into the `ZCoderError` hierarchy `retry()` already
knows how to read, so each module no longer hand-rolls its own
`except HTTPError` translation. Every module now retries transient
failures (429/5xx/network) with exponential backoff and fails fast via a
`CircuitBreaker` once a downstream is clearly down, without changing any
external contract — callers that expected a `{"error": ...}` dict back,
or a `RuntimeError`, or a `[API ERROR N]` string, still get exactly that
shape; only what happens underneath changed.

Two deliberate exceptions to a shared per-module breaker: `claude_github.py`
gets one breaker (all its call sites hit the GitHub API), while call sites
that fetch an arbitrary caller-supplied URL — `claude_chrome.py`'s page
fetch, `claude_research.py`'s source fetch, `claude_code.py`'s `WebFetch`
tool, `claude_plugins.py`'s marketplace fetch — retry transient failures
but skip the breaker, since a breaker tracking "this one dependency is
down" doesn't mean anything when every call targets a different host.

All 132 pre-existing tests still pass; verified end-to-end with a mocked
503 that retries twice then succeeds on the 3rd attempt.

## v1.16.0 — Compliance API

Closes the one gap v1.15.0 deliberately left open. New module
`claude_compliance_api.py` wraps `/v1/compliance/*`: the org-wide
Activity Feed, plus (with a Compliance Access Key) read/hard-delete
access to the chats, files, and projects those activities reference,
plus directory (orgs/users/roles/settings/groups) endpoints. Every
destructive op is dry-run by default and requires `--compliance-yes`.
Retry/backoff and pagination-cursor handling follow the documented
compliance-errors contract exactly (see `docs/30_upgrade_v1.16.0.md`).
28 new tests in `tests/test_claude_compliance_api.py`, all passing.

## v1.15.0 — Roadmap gap-audit implementation

Implements the five buildable items from `ROADMAP.md`'s gap audit against
platform.claude.com/docs (checked 2026-07-04); the sixth (Compliance API)
stays a documented gap per the roadmap's own recommendation. See
`docs/29_upgrade_v1.15.0.md` for the full write-up and `CHECKLIST.md` for
the itemized task list this release closes out.

- **P0 — Server-side `fallbacks` param** (`claude_fable5.py`): new
  `--fable5-fallback-chain MODEL1,MODEL2` lets the platform itself retry a
  refused Fable 5 call against up to 3 models in one round trip, instead
  of the existing client-side manual retry (`--fallback-model`, still
  supported, now the fallback path only when a chain isn't given).
- **P1 — Context editing** (new `claude_context_editing.py` is not
  needed — `claude_tools.py` already had a complete
  `build_context_management()`; the actual gap was that
  `claude_code.py`'s `--code-agent` loop never called it). New
  `--agent-context-editing` flag wires `clear_tool_uses` into the agent
  loop, complementary to the existing Compaction support. See
  `docs/29_upgrade_v1.15.0.md` for a worked example combining both.
- **P1 — Agent Skills API** (new `claude_skills_api.py`): `skill_id`-based
  platform Skills, distinct from `claude_code.py`'s local
  `.claude/skills/*/SKILL.md` loader. New `--skills-list` / `--skills-info
  ID` flags. Routing `claude_excel.py`/`claude_powerpoint.py` through this
  instead of their existing hand-rolled implementation is an intentional
  follow-up, not part of this release.
- **P2 — Usage and Cost API + API key management** (new
  `claude_admin_api.py`, combined per the roadmap's own suggested
  grouping): new `--usage-report` and `--admin-list-keys` /
  `--admin-revoke-key` flags. Both require an Admin API key
  (`--admin-api-key` or `ANTHROPIC_ADMIN_API_KEY`), not a regular one.
  `--admin-create-key` intentionally explains why key creation isn't
  exposed via the API rather than faking it — Anthropic doesn't document a
  create-key endpoint (Console-only, secret shown once).
- **P2 — Compliance API**: left as a documented gap, not built, per the
  roadmap's recommendation (enterprise-only surface, no concrete use case
  yet).

## v1.14.0 — Chat & Excel

Two new user-facing features, both additive: `-i`/`--interactive` (a bare,
dead argparse flag since v1.7.0) now runs a real persistent chat REPL, and
a new `--excel` conversational spreadsheet assistant builds financial
models, cleans messy data, and creates tables/charts against a live
`.xlsx` workbook. No existing flags changed. See
`docs/28_upgrade_v1.14.0.md`.

## v1.13.0 — Enterprise hardening

Structured logging with secret redaction, retry + circuit breaking around
the core API call, path/URL/input security controls, a `--health-check`
for orchestrators, and a full test/CI/Docker setup. No CLI flags removed
or renamed. See `docs/27_upgrade_v1.13.0.md`.

## v1.12.1 — 2026-07-03

Deep-dive bug pass against v1.12.0, plus a new bulk model-upgrade feature.
See `docs/26_upgrade_v1.12.1.md` for full detail.

- Fixed `coder.py`'s `Coder.generate()` silently mishandling responses from
  thinking-capable models (Sonnet 5, Opus 4.8, Fable 5/Mythos 5) and any
  multi-text-block response — was reading only `content[0]["text"]`.
- Wired three previously dead-on-arrival CLI flags: `--skill`, `--agent`
  (accepted, never read anywhere), and `--cache-stats` (accepted, but
  `--cache` always showed stats regardless of it).
- Added `--personality` / `--list-personalities`, exposing `personalities.py`'s
  `PersonalityManager`, which was fully implemented and already wired into
  `Coder.__init__` but unreachable from the CLI.
- **New:** `--upgrade-all PATH [--upgrade-target fable5|opus] [--upgrade-yes]
  [--upgrade-no-backup]` — bulk-rewrites every known Claude model ID under a
  file or directory to Claude Fable 5 or Claude Opus 4.8. Dry-run by
  default; writes `.bak` backups on apply. Distinct from the existing
  `--check-deprecated` (report-only, retired IDs only).

## v1.12.0 "Release" — 2026-07-03

Packaging-only release. No API/functional changes from v1.11.1.


- Merged in `zcoder-cli-v2`'s standalone-executable packaging: `build.sh`
  / `build.bat` (PyInstaller, produces a single `dist/zcoder` binary with
  no local Python required), `setup.sh` / `setup.bat` (venv + `.env` setup
  for running from source), `zcoder.spec`, `LICENSE` (MIT).
- Added `.env.example` (referenced by `setup.sh`/`setup.bat` but missing
  from both source projects) documenting `ANTHROPIC_API_KEY` (required),
  `VOYAGE_API_KEY` (optional, `claude_embeddings.py`), `GITHUB_TOKEN`
  (optional, `claude_github.py`).
- `requirements.txt`: bumped minimum `anthropic` SDK to `>=0.75.0`,
  required for `client.beta.agents/.environments/.sessions`
  (`--agent-managed-run`, see `claude_agents_sdk.ManagedAgentsClient`).
- Everything else in `zcoder-cli-v2` (`coder.py`, `config.py`, `utils.py`,
  `skills.py`, `agents.py`, `multi_agent_core.py`, `workflow_examples.py`,
  `batches.py`, its own `managed_agents.py`) was **not** merged — v1 already
  has a mature, independently-audited implementation of the same ground
  (`coder.py`/`config.py`/`utils.py`/`skills.py` under the same names but a
  different, already-integrated implementation; `claude_agents_sdk.py`'s
  `ManagedAgentsClient` already wraps the real Managed Agents API that
  v2's `managed_agents.py` also wrapped). Merging both would have meant two
  competing implementations behind the same CLI flags and import names —
  picked the one already wired into 900+ lines of `main.py` and this
  project's own audit history rather than replacing it. See
  `docs/25_merge_v2_into_release.md` for the full reasoning.

## v1.11.1 and earlier

See `docs/*_upgrade_*.md` for the full per-release history, starting from
`docs/17_projects_and_artifacts.md`. Highlights:

- **v1.11.1**: MCP tunnels (`claude_agents_sdk.McpTunnel`), retired
  tool-version tracking (`claude_tools.RETIRED_TOOL_VERSIONS`), refusal
  billing exemption in the cost optimizer, a Sonnet-5 sampling-parameter
  fix.
- **v1.11.0**: Advisor tool (`claude_advisor.py`), Programmatic Tool
  Calling (real implementation), Tool Use Examples, task budgets,
  compaction, embeddings (`claude_embeddings.py`, via Voyage AI),
  fine-grained tool streaming, `stop_details` on refusals.
- **v1.10.x**: native memory tool, context editing, tool search tool,
  full model catalog + retired-model registry, verified pricing.
- **v1.9.x – v1.0**: Claude Code / Agent SDK, Cowork, plugins, output
  styles, sandbox, RAG, evals, batch API, prompt caching, vision, and the
  rest of the modular `claude_*.py` feature set.
