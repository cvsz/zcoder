# CHECKLIST.md

**zcoder v1.36.0 — Roadmap Execution Checklist**
Derived from `ROADMAP.md` Part 2 (Gap Audit vs. `platform.claude.com/docs`,
originally checked 2026-07-04, kept current through the v1.33.0 cycle
checked 2026-07-26). Cycles v1.34.0–v1.36.0 aren't backfilled into the
form-style sections below — see `CHANGELOG.md` and their respective
`docs/*_upgrade_*.md` writeups instead.

Every gap-audit cycle from v1.15.0 through v1.33.0 is represented below,
in order. Check off each sub-task as it lands; a priority group is only
"done" when every box under it is checked **and** the shared Definition
of Done at the bottom passes.

This file previously stopped being updated after the v1.20.0 cycle even
though the project kept shipping audit cycles through v1.33.0; the
sections below for v1.21.0 through v1.33.0 backfill that gap from
`ROADMAP.md`, `CHANGELOG.md`, and the corresponding `docs/*` writeups so
this file is a complete index again, not just current through 2026-07-08.

---

## 🔴 P0 — Server-side fallback (`fallbacks` parameter) ✅ DONE
*Est. effort: ~1 file, ~60 lines, no new deps.*

- [x] Add `fallback_chain: list[str] = None` param to `Fable5Client.__init__`
- [x] In `call()`: when `fallback_chain` is set, add `payload["fallbacks"] = fallback_chain` (replacing, not supplementing, the manual retry path)
- [x] Rework `call_with_fallback()` into a thin compatibility wrapper:
  - [x] If `fallback_chain` is set → inspect `stop_reason` + which model served the response, no manual retry
  - [x] If `fallback_chain` is unset → fall through to the existing manual retry path
- [x] Add new CLI flag: `--fable5-fallback-chain MODEL1,MODEL2` (max 3 models total, including primary)
- [x] Update `claude_fable5.py` module docstring to document both patterns and when to use each:
  - [x] Manual retry → changing prompt/system before retrying
  - [x] `fallbacks` param → let the platform handle it in one round trip
- [x] Add/update tests covering both the `fallback_chain` path and the legacy manual path (`tests/test_claude_fable5.py`, 15 tests)

---

## 🟠 P1 — Context editing ✅ DONE (scope revised — see note)
*Est. effort: ~1 new file + 1 integration point, ~200 lines total.*

> **Correction found during implementation:** `claude_tools.py` already had
> a complete `build_context_management()` — the roadmap's audit missed it.
> No new `claude_context_editing.py` module was needed; the real gap was
> narrower (the agent loop just never called the existing function).

- [x] ~~Create new module `claude_context_editing.py`~~ — not needed, reused `claude_tools.build_context_management()`
- [x] Wire into `claude_code.py`'s agent loop behind an opt-in `--agent-context-editing` flag
- [x] Add a worked example under `docs/` showing Compaction + context editing used together in one long agent run (`docs/29_upgrade_v1.15.0.md`)
- [x] Confirm this does not change default behavior (opt-in only, `context_management=None` default)

---

## 🟠 P1 — Agent Skills via the API (`skill_id`) ✅ DONE (base client)
*Est. effort: ~1 new file for the base client, ~120 lines (excel/pptx integration is a separate follow-up).*

- [x] Create new module `claude_skills_api.py`
  - [x] `list_skills()` (static list of pre-built skills — no documented list endpoint for custom skills)
  - [x] `SkillRef` helper to build a `skill_id` reference for a Messages request
  - [x] CLI flag `--skills-list`
  - [x] CLI flag `--skills-info ID` (info-only, matching `claude_fable5.py`'s `cmd_fable5_info` pattern)
- [x] **Follow-up (landed this pass, ahead of schedule):** `--excel-native` / `--pptx-native` flags added to `claude_excel.py` / `claude_powerpoint.py`, routing through `claude_skills_api.py`'s `call_with_skills_turn()` while keeping the hand-rolled implementation as the fallback when Skills access isn't available

---

## 🟡 P2 — Usage and Cost API ✅ DONE
*Est. effort: ~1 file, ~100 lines. Requires an Admin API key.*

- [x] Create new module `claude_admin_api.py` (named per the roadmap's own suggested regrouping, see below)
  - [x] `get_usage_report(start, end, group_by)` wrapping the usage/cost endpoint (plus `get_cost_report`)
  - [x] CLI flag `--usage-report` that prints a table
- [x] Cross-link from `claude_cost_optimizer.py`'s docstring to the real reporting endpoint
- [x] Clearly flag in CLI help text / runtime error that this requires an **Admin API key** (not a regular key)

---

## 🟡 P2 — API key management (Admin API) ✅ DONE (list/revoke — create is N/A by design)
*Est. effort: ~80 lines, combined with the Usage API module.*

- [x] Decide module name: folded into `claude_admin_api.py` alongside the Usage API, per the roadmap's own suggested grouping
- [x] CLI flag `--admin-list-keys`
- [x] CLI flag `--admin-create-key NAME` — implemented as an explanation, not a real call: there's no documented create-key endpoint (Console-only, secret shown once), so this prints why instead of faking success
- [x] CLI flag `--admin-revoke-key ID`
- [x] Confirm Admin API auth requirements are documented alongside the Usage API ones

---

## 🟡 P2 — Compliance API ✅ DONE (v1.16.0)
*Est. effort: ~1 file, ~450 lines (client + all cmd_* wrappers). Requires a*
*Compliance Access Key for most endpoints; an Admin API key unlocks only*
*the Activity Feed.*

> **Reversal note:** v1.15.0 explicitly recommended leaving this as a
> documented gap. That recommendation's own stated exit condition — "revisit
> only if there's an actual concrete request for it" — has since been met,
> which is why this is now built. It is not a decision to build
> speculatively against a guessed shape; the endpoint family is confirmed
> against `platform.claude.com/docs/en/manage-claude/compliance-api*`
> (checked 2026-07-04).

- [x] Create new module `claude_compliance_api.py`
  - [x] `ComplianceApiClient` with the documented retry/backoff contract
        (429 + retryable 5xx back off exponentially 1s→60s; 400/401/403/
        404/409 never retry)
  - [x] Activity Feed: `list_activities()` / `iterate_activities()` with
        `since`/`until`/`activity_types`/`limit` filters and cursor-safe
        pagination (cursor only advances after a successful page)
  - [x] Chats: `list_chats()`/`iterate_chats()`, `get_chat_messages()`,
        `delete_chat()`
  - [x] Files: `download_file()` (with `Content-Disposition` filename
        parsing), `delete_file()`
  - [x] Projects: `list_projects()`, `get_project()`,
        `list_project_attachments()`, `delete_project()`
  - [x] Directory: `list_organizations()`, `list_org_users()`,
        `list_org_roles()`, `get_org_settings()`, `list_groups()`,
        `list_group_members()`
  - [x] Dry-run-by-default guard on every destructive `cmd_*`
        (`cmd_compliance_chat_delete`, `cmd_compliance_file_delete`,
        `cmd_compliance_project_delete`) — requires explicit `yes=True`
        (CLI: `--compliance-yes`), mirroring `claude_models.py`'s
        `--upgrade-all`/`--upgrade-yes` pattern
  - [x] Surfaces the documented 403 scope-mismatch message
        (`Got:`/`Needed:` scopes) with a concrete fix instead of a bare
        permission error, since Compliance Access Key vs. Admin API key
        reach differs per-endpoint
- [x] Add CLI flags (all under a new `Compliance API` argument group in
      `main.py`, dispatch mirrors the `claude_admin_api.py` block):
      `--compliance-api-key`, `--compliance-activities(-since/-until)`,
      `--compliance-activity-types`, `--compliance-activities-limit`,
      `--compliance-activities-all`, `--compliance-chats-list`,
      `--compliance-user-ids`, `--compliance-chat-messages`,
      `--compliance-chat-delete`, `--compliance-file-download`,
      `--compliance-file-delete`, `--compliance-projects-list`,
      `--compliance-project-info`, `--compliance-project-attachments`,
      `--compliance-project-delete`, `--compliance-orgs-list`,
      `--compliance-org-users`, `--compliance-org-roles`,
      `--compliance-org-settings`, `--compliance-groups-list`,
      `--compliance-group-members`, `--compliance-yes`,
      `--compliance-output`
- [x] Key fallback order: `--compliance-api-key` →
      `ANTHROPIC_COMPLIANCE_API_KEY` → `--admin-api-key` →
      `ANTHROPIC_ADMIN_API_KEY` (Admin key fallback only reaches the
      Activity Feed; every other flag 403s with a clear message)
- [x] Module docstring documents both key types and the endpoint-reach
      table, and cross-links `claude_admin_api.py` explaining how the two
      modules differ
- [x] Add tests (`tests/test_claude_compliance_api.py`, 28 tests): error
      classification/retry, exponential backoff on 429/retryable-5xx
      (never on 400/401/403/404/409), cursor-safety in `iterate_*`,
      `Content-Disposition` filename parsing, dry-run guard on every
      destructive `cmd_*`
- [x] Confirm this gap stays documented as *resolved* in `ROADMAP.md` /
      `README.md` (see `docs/30_upgrade_v1.16.0.md`)

---

## 🟠 P1 — Mid-conversation system messages ✅ DONE (v1.18.0)

> New feature, found in the v1.18.0 audit cycle (2026-07-08). Genuinely
> absent — zero matches for role:"system" message construction anywhere
> in the tree. Opus 4.8 only, no beta header.

- [x] `build_mid_system_message(text)` in `claude_cache.py`
- [x] `validate_system_message_placement(messages)` — all five documented
      placement rules, dedicated `SystemMessagePlacementError`
- [x] `MID_SYSTEM_SUPPORTED_MODELS` model gate (Opus 4.8 only)
- [x] Threaded through `generate_cached(mid_system=...)` and
      `multi_turn_cached(mid_system_updates=...)`
- [x] CLI: `--cache-multi-turn`, `--cache-mid-system`, `--cache-mid-system-after`
- [x] Add tests (`tests/test_claude_cache.py` — new file, 18 tests)

## 🟡 P2 — Cache diagnostics (beta) CLI wiring ✅ DONE (v1.18.0)

> Looked like a fresh gap on first grep (`cache_diagnostic` / `cache.diagnostic`
> matched nothing), but the feature was already fully built in
> `claude_cache.py` (`diagnose=`, the `cache-diagnosis-2026-04-07` beta
> header, `cache_miss_reason`) — just never reachable from `main.py`.

- [x] Add `--cache-diagnose` flag, wire to `cmd_cache_generate(diagnose=...)`
- [x] Add tests covering both the first-call and reference-prior-id cases
      (`tests/test_claude_cache.py`)

## 🟠 P1 — Managed Agents memory stores ✅ DONE (v1.19.0)

> New feature, found in the v1.19.0 audit cycle (2026-07-08) by checking
> the `anthropic` SDK's own changelog for drift, which surfaced the
> `agent-memory-2026-07-22` beta header. Genuinely absent — zero matches
> for `memory_store` or a `resources` param anywhere in
> `claude_agents_sdk.py`.

- [x] `ManagedAgentsClient.create_memory_store(name)` wraps
      `client.beta.memory_stores.create`
- [x] `create_session(..., memory_store_id=...)` mounts the store as a
      `resources` entry and adds the `agent-memory-2026-07-22` beta header
- [x] `cmd_agent_memory_store_create()` standalone helper
- [x] CLI: `--agent-memory-store NAME`, `--agent-memory-store-create`
- [x] Add tests (`tests/test_claude_agents_sdk.py` — new file, 10 tests,
      also covering pre-existing untested behavior per this cycle's scope)

## 🟠 P1 — Managed Agents Dreaming ✅ DONE (v1.20.0)

> New feature (research preview), found in the v1.20.0 audit cycle by
> re-checking the Managed Agents docs for what shipped alongside the
> memory-store feature. Genuinely absent — confirmed with two
> differently-worded greps (`dream`, then
> `curat|reflect.*session|memory.*consolidat`).

- [x] `ManagedAgentsClient.create_dream/.get_dream/.list_dreams/.cancel_dream`
      wrap `client.beta.dreams.*` with the `dreaming-2026-04-21` beta header
- [x] CLI: `--agent-dream`, `--agent-dream-sessions`,
      `--agent-dream-instructions`, `--agent-dream-list`, `--agent-dream-get`
- [x] Tests added (`tests/test_claude_agents_sdk.py`)

## 🟠 P1 — Managed Agents Outcomes ✅ DONE (v1.20.0)

> New feature (public beta). Genuinely absent — confirmed with two
> differently-worded greps (`define_outcome`, then
> `outcome_evaluation|rubric`).

- [x] `ManagedAgentsClient.define_outcome/.wait_for_outcome` send the
      `user.define_outcome` event and stream to a terminal
      `span.outcome_evaluation_end`
- [x] `cmd_managed_agent_run()` gains opt-in outcome params, falling
      through to the existing `run_task()` path when unset
- [x] CLI: `--agent-outcome`, `--agent-outcome-rubric`,
      `--agent-outcome-max-iter`
- [x] Tests added (`tests/test_claude_agents_sdk.py`)

## 🟡 P2 — Managed Agents Webhooks ✅ DONE (v1.20.0)

> New feature (public beta). Genuinely absent — grep for `webhook`
> matched only an unrelated docstring comment.

- [x] `ManagedAgentsClient.register_webhook()` wraps `client.beta.webhooks.create`
- [x] CLI: `--agent-webhook-register`, `--agent-webhook-events`
- [x] Tests added (`tests/test_claude_agents_sdk.py`)

## 🟡 P2 — Managed Agents native Multiagent orchestration ⏸ DEFERRED (v1.20.0)

> Confirmed real and absent (distinct from the pre-existing client-side
> `--agent-orchestrate`, which makes separate Messages API calls per
> subagent rather than sharing one Managed Agents session/sandbox).
> Deliberately not built this cycle — larger surface than the other
> three items, no concrete use case yet. See `ROADMAP.md`'s Priority
> Summary section for the full reasoning and exit condition. Matches how
> the Compliance API gap was handled between v1.15.0 and v1.16.0.

## 🟡 P2 — Managed Agents native Multiagent orchestration ✅ DONE (v1.21.0)

> Closes the item deferred at v1.20.0. `build_multiagent_config()` +
> `--agent-review-multiagent` in `claude_agents_sdk.py`.

- [x] Vaults & credentials: `--agent-vault-create`, `-add-credential`, `-list`, `--agent-vault`
- [x] Scheduled deployments: `--agent-schedule-create`, `-list`, `-cancel`
- [x] Native Multiagent orchestration: `build_multiagent_config`, `--agent-review-multiagent`
- [x] Outcomes file-based rubric: `--agent-outcome-rubric-upload`, `-file`
- [x] Tests added (`tests/test_claude_agents_sdk.py`)

## 🟡 P2 — Managed Agents session overrides, vault injection location, event deltas ✅ DONE (v1.22.0)

- [x] `--agent-override-json`, `--agent-override-model`, `--agent-override-system`
- [x] `--agent-vault-injection-location`
- [x] `--agent-stream-deltas`
- [x] `code_execution` tool version bump to `code_execution_20260120` (`--code-exec-version`)
- [x] Tests added

## 🔴 P0 — Workload Identity Federation (WIF) ✅ DONE (v1.23.0)

> Genuinely absent — confirmed with two differently-worded greps
> (`workload identity|OIDC|oidc|federation`, then
> `short-lived|token_exchange|id_token`).

- [x] `claude_wif.py` (new): `WIFClient` auto-detects config from
      `ANTHROPIC_FEDERATION_RULE_ID`/`ANTHROPIC_ORGANIZATION_ID`/
      `ANTHROPIC_SERVICE_ACCOUNT_ID`/`ANTHROPIC_WORKSPACE_ID`/
      `ANTHROPIC_IDENTITY_TOKEN_FILE`(or `_TOKEN`)
- [x] JWT-bearer exchange against `POST /v1/oauth/token`, auto-refresh before expiry
- [x] CLI: `--wif-info`, `--wif-token`
- [x] Tests added (`tests/test_claude_wif.py`)

## 🟠 P1 — Server tool version drift: code_execution, web_search, web_fetch ✅ DONE (v1.24.0)

- [x] `claude_tools.SERVER_TOOLS` bumped: `code_execution_20260521`, `web_search_20260318`, `web_fetch_20260318`
- [x] `claude_search.py`'s separate `WEB_SEARCH_TOOL`/`WEB_FETCH_TOOL` constants brought in sync (had never been bumped)
- [x] `response_inclusion` parameter wired as opt-in
- [x] Confirmed non-gap: Claude Enterprise Analytics API real but deliberately unbuilt

## 🟠 P1 — Extended thinking `display: "omitted"` ✅ DONE (v1.25.0)

- [x] `claude_thinking.py` config builders accept `display="omitted"`
- [x] `--thinking-display omitted`
- [x] Confirmed CMEK `external_keys` Admin API surface; read-only `--admin-cmek-list` added

## 🟠 P1 — Managed Agents self-hosted sandboxes ✅ DONE (v1.26.0)

- [x] `client.beta.environments.create(config={"type": "self_hosted"})` wrapper
- [x] `EnvironmentWorker` polling pattern
- [x] CLI: `--agent-env-self-hosted`, `--agent-worker-poll`
- [x] Tests added

## 🔴 P0 bug fix + 🟠 P1 — Memory store beta-header regression, memory/memory-store CRUD ✅ DONE (v1.27.0)

- [x] Fixed: `create_memory_store()`/`list_memories()` no longer send both
      `managed-agents-2026-04-01` and `agent-memory-2026-07-22` (400 on combination)
- [x] Memory store management: `retrieve`/`update`/`list`/`archive`/`delete`
- [x] Memory CRUD: `retrieve`/`create`/`update`/`delete`
- [x] Deliberately deferred: memory *versions* (`list`/`retrieve`/`redact`) — no concrete use case yet

## 🔴 P0 — Files API: wrong content-block type for code execution ✅ DONE (v1.28.0)

- [x] `claude_code_exec.py` now attaches `file_ids` with `container_upload`, not `document`
- [x] New `webapp/` (FastAPI backend + frontend) for browser-based access

## Feature deep-dive — Textual TUI + web console upgrade ✅ DONE (v1.29.0)

- [x] `tui.py` (new): Textual-based terminal UI, `--tui`
- [x] Web console gained streaming, session persistence, theme support
- [x] Not a gap-audit cycle — no new Anthropic API surface

## 🔴 P0 — Extended/adaptive thinking routing broken on 6 of 9 catalog models ✅ DONE (v1.30.0)

- [x] `claude_thinking.py` routes each model to the request shape it accepts
      (adaptive vs. extended) instead of sending `enabled`+`budget_tokens` unconditionally
- [x] Fixed models: Opus 4.8, Opus 4.7, Sonnet 5, Fable 5, Mythos 5, Mythos Preview

## 🟠 P1 — CLI-to-API wiring audit: GitHub, Router, Prompt Optimizer, Metrics ✅ DONE (v1.31.0)

- [x] Found and wired 4 fully-built, fully-tested modules with zero `main.py` reachability
- [x] Added `tests/test_cli_wiring.py` as a standing regression check

## 🔴 P0 bug fix + 🟡 P2 — Claude Opus 5, fast-mode enforcement, fallbacks "default" ✅ DONE (v1.32.0)

- [x] `claude-opus-5` added to `MODEL_CATALOG`
- [x] `validate_fast_mode()` wired into `Coder.generate()` (previously defined but never called)
- [x] `fallbacks` `"default"` string mode added alongside existing list mode
- [x] Tests added (`tests/test_coder.py`, `tests/test_claude_fable5.py`)

## 🟡 P2 — Deep per-model modules: Claude Opus 5, Sonnet 5, Haiku 4.5 ✅ DONE (v1.33.0)

> Every current-tier model previously lived only as a `MODEL_CATALOG`
> row; `claude_fable5.py`/`claude_mythos5.py` were the only per-model
> modules. See `docs/45_upgrade_v1.33.0_current_tier_deep_modules.md`.

- [x] `claude_opus5.py` (new): `validate_effort_thinking()` client-side
      guard, `OPUS5_EFFORT_BUDGETS` with the `xhigh` rung,
      unconfirmed-data-residency flag for `--opus5-geo`
- [x] `claude_sonnet5.py` (new): `current_pricing()` date-based promo
      calculator, service-tier-unsupported / inference-geo-supported flags
- [x] `claude_haiku45.py` (new): `build_thinking_param()` always builds
      the extended (not adaptive) shape; dateless alias resolution
- [x] All three wired into `main.py`; 30 new tests
      (`tests/test_claude_opus5.py`, `tests/test_claude_sonnet5.py`, `tests/test_claude_haiku45.py`)
- [x] Deliberately out of scope: `claude_models.EFFORT_BUDGETS` not patched
      with `xhigh` (wider blast radius); `--upgrade-all` not extended to
      target Sonnet 5/Haiku 4.5 (product decision, not implied by the ask)

## 🟠 P1 / 🟡 P2 — Re-validation cycle: Opus, Sonnet, Haiku, Fable, Mythos ✅ DONE (v1.34.0)

> Targeted re-audit requested for the five per-model modules against a
> fresh release-notes fetch (2026-07-26). See
> `docs/46_upgrade_v1.34.0_model_revalidation.md`.

- [x] Re-confirmed `MODEL_CATALOG`, fast-mode sets, and existing
      Opus 5/Haiku 4.5/Fable 5/Mythos 5 validators all still correct
- [x] Finding 1: mid-conversation tool changes beta
      (`mid-conversation-tool-changes-2026-07-01`; Fable 5, Mythos 5,
      Opus 4.8, Opus 5 only) was entirely missing — added
      `MID_CONVERSATION_TOOL_CHANGES_SUPPORTED`,
      `validate_mid_conversation_tool_change()`,
      `with_mid_conversation_tool_changes()` to `claude_tools.py`;
      `--mid-conv-tool-check MODEL_ID` wired into `main.py`
- [x] Finding 2: Sonnet 5's strict non-default sampling-parameter
      rejection (temperature/top_p/top_k) was unguarded — added
      `validate_sampling_params()`; `Sonnet5Client.call()` now
      rejects these client-side before building a request
- [x] Deliberately out of scope: Dreaming's July 10 Fable 5/Sonnet 5
      expansion (Managed Agents concern, not a per-model-module
      concern); Fable 5/Mythos 5 prefill/manual-thinking guards (no
      live code path exposes either parameter yet)
- [x] 10 new tests (`tests/test_claude_tools.py` +5,
      `tests/test_claude_sonnet5.py` +5); full suite (506) passes

---

## Definition of Done (applies to every P0/P1/P2 item above)

- [x] New/changed code has a CLI flag consistent with existing house style (`--flag-name`) — verified: `--fable5-fallback-chain`, `--agent-context-editing`, `--skills-list`/`--skills-info`, `--usage-report`/`--cost-report`(+`-start`/`-end`/`-group-by`), `--admin-list-keys`/`--admin-revoke-key`/`--admin-create-key`, `--excel-native`/`--pptx-native`, the full `--compliance-*` group (23 flags), `--cache-diagnose`/`--cache-multi-turn`/`--cache-mid-system`/`--cache-mid-system-after`, `--agent-memory-store`/`--agent-memory-store-create`, and the new `--agent-dream*`/`--agent-outcome*`/`--agent-webhook-*` groups all wired in `main.py`
- [x] Module docstring updated to explain the feature and, where relevant, how it relates to an existing similar feature — confirmed in `claude_fable5.py`, `claude_code.py`, `claude_skills_api.py`, `claude_admin_api.py`, `claude_compliance_api.py`, `claude_cache.py`, `claude_agents_sdk.py`
- [x] Tests added or updated for the new code path — `tests/test_claude_fable5.py` (15), `tests/test_claude_code_context_editing.py` (6), `tests/test_claude_skills_api.py` (17), `tests/test_claude_admin_api.py` (10), `tests/test_claude_compliance_api.py` (28), `tests/test_claude_cache.py` (18), `tests/test_claude_agents_sdk.py` (26, up from 10 in v1.19.0); all 176 pass
- [x] `README.md` per-flag reference updated — "New in v1.15.0" section, "New in v1.16.0" section for the Compliance API, "New in v1.18.0" section, "New in v1.19.0" section, and a new "New in v1.20.0" section
- [x] `CHANGELOG.md` entry added — see "v1.15.0 — Roadmap gap-audit implementation", "v1.16.0 — Compliance API", "v1.18.0 — Mid-conversation system messages + Cache diagnostics CLI wiring", "v1.19.0 — Managed Agents memory stores", and "v1.20.0 — Dreaming, Outcomes, Webhooks"
- [x] No regression to existing default behavior — every new capability is opt-in (`context_management=None` default, `fallback_chain` unset falls through to the existing manual-retry path, Admin/Compliance API calls only fire when their flags are passed, every Compliance destructive op is dry-run unless `--compliance-yes` is also passed, `mid_system`/`mid_system_updates` default to `None`/`{}`, `diagnose` defaults to `False`, `memory_store_id` defaults to `None`, and `outcome_description`/`outcome_rubric` default to `None` so existing callers are unaffected)
- [x] `ROADMAP.md` Part 1 coverage table updated to move the item from Part 2 (gap) into Part 1 (implemented) — confirmed present for all twelve implemented items (native Multiagent orchestration intentionally stays in the gap/defer section, not Part 1)

---

## Priority Summary (for quick reference)

| Priority | Item | Status |
|---|---|---|
| 🔴 P0 | Server-side `fallbacks` param | ✅ Done (`claude_fable5.py`) |
| 🟠 P1 | Context editing | ✅ Done — wired existing `claude_tools.build_context_management()` into `claude_code.py` |
| 🟠 P1 | Agent Skills API (`skill_id`) | ✅ Done (`claude_skills_api.py`) — base client + `--excel-native`/`--pptx-native` follow-up both landed |
| 🟡 P2 | Usage and Cost API | ✅ Done (`claude_admin_api.py`) |
| 🟡 P2 | API key management | ✅ Done — list/revoke (`claude_admin_api.py`); create is N/A by design |
| 🟡 P2 | Compliance API | ✅ Done (`claude_compliance_api.py`, v1.16.0) — built once the recommendation's own "concrete request" condition was met |
| 🟠 P1 | Mid-conversation system messages | ✅ Done (`claude_cache.py`, v1.18.0) |
| 🟡 P2 | Cache diagnostics CLI wiring | ✅ Done (`claude_cache.py`/`main.py`, v1.18.0) |
| 🟠 P1 | Managed Agents memory stores | ✅ Done (`claude_agents_sdk.py`, v1.19.0) |
| 🟠 P1 | Managed Agents Dreaming | ✅ Done (`claude_agents_sdk.py`, v1.20.0) |
| 🟠 P1 | Managed Agents Outcomes | ✅ Done (`claude_agents_sdk.py`, v1.20.0) |
| 🟡 P2 | Managed Agents Webhooks | ✅ Done (`claude_agents_sdk.py`, v1.20.0) |
| 🟡 P2 | Managed Agents native Multiagent orchestration | ✅ Done (v1.21.0) — closes the v1.20.0 deferral |
| 🟡 P2 | Managed Agents Vaults & credentials, Scheduled deployments, Outcomes file rubric | ✅ Done (v1.21.0) |
| 🟡 P2 | Managed Agents session overrides, vault injection location, event deltas | ✅ Done (v1.22.0) |
| 🔴 P0 | Workload Identity Federation (WIF) | ✅ Done (`claude_wif.py`, v1.23.0) |
| 🟠 P1 | Server tool version drift (code_execution/web_search/web_fetch) | ✅ Done (v1.24.0) |
| 🟠 P1 | Extended thinking `display: "omitted"`, CMEK `external_keys` | ✅ Done (v1.25.0) |
| 🟠 P1 | Managed Agents self-hosted sandboxes | ✅ Done (v1.26.0) |
| 🔴 P0 | Memory store beta-header regression + memory/memory-store CRUD | ✅ Done (v1.27.0) — memory *versions* deferred |
| 🔴 P0 | Files API `container_upload` fix + web console | ✅ Done (v1.28.0) |
| — | Textual TUI + web console streaming/sessions/theme (feature deep-dive) | ✅ Done (v1.29.0) |
| 🔴 P0 | Extended/adaptive thinking routing broken on 6 of 9 models | ✅ Done (v1.30.0) |
| 🟠 P1 | CLI-to-API wiring audit (GitHub, Router, Prompt Optimizer, Metrics) | ✅ Done (v1.31.0) |
| 🔴 P0 | Claude Opus 5 model-catalog gap + fast-mode enforcement bug + fallbacks "default" | ✅ Done (v1.32.0) |
| 🟡 P2 | Deep per-model modules: Opus 5, Sonnet 5, Haiku 4.5 | ✅ Done (v1.33.0) |
| 🟠 P1 / 🟡 P2 | Re-validation: Opus, Sonnet, Haiku, Fable, Mythos (mid-conv tool changes, Sonnet 5 sampling guard) | ✅ Done (v1.34.0) |
