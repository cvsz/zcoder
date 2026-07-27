# IMPLEMENTATION CHECKLIST (Form) — zcoder v1.16.0

Source: `ROADMAP.md` Part 2 — Gap Audit vs. `platform.claude.com/docs` (checked 2026-07-04)
One form per gap. All six gaps are now done — Forms 1–5 shipped in
v1.15.0, Form 6 (Compliance API) shipped in v1.16.0 once its own stated
exit condition ("revisit only if there's an actual concrete request for
it") was met. See `CHANGELOG.md`, `CHECKLIST.md`, and
`docs/29_upgrade_v1.15.0.md` / `docs/30_upgrade_v1.16.0.md` for the
narrative writeups this form-style tracker summarizes.

---

## Form 1 — 🔴 P0: Server-side fallback (`fallbacks` parameter)

| Field | Value |
|---|---|
| Priority | 🔴 P0 |
| Module(s) affected | `claude_fable5.py` |
| Est. effort | ~1 file, ~60 lines, no new deps |
| Owner | zcoder maintainers |
| Target date | v1.15.0 |
| Status | ☐ Not started ☐ In progress ☐ In review ☑ Done |

**Task list**
- [x] Add `fallback_chain: list[str] = None` param to `Fable5Client.__init__`
- [x] `call()`: set `payload["fallbacks"] = fallback_chain` when provided (replaces manual path, not additive)
- [x] `call_with_fallback()` reworked into compatibility wrapper (fallback_chain path vs. legacy manual path)
- [x] New CLI flag `--fable5-fallback-chain MODEL1,MODEL2` (max 3 incl. primary)
- [x] Docstring updated: explain manual retry vs. `fallbacks` param, and when to use each
- [x] Tests added/updated for both code paths (`tests/test_claude_fable5.py`, 15 tests)

**Sign-off**
- Reviewed by: zcoder maintainers  Date: v1.15.0 release
- Notes: Shipped as planned, no scope changes.

---

## Form 2 — 🟠 P1: Context editing

| Field | Value |
|---|---|
| Priority | 🟠 P1 |
| Module(s) affected | ~~New: `claude_context_editing.py`~~; integration: `claude_code.py` (see notes — no new module was needed) |
| Est. effort | ~1 new file + 1 integration point, ~200 lines (revised: 0 new files, ~1 integration point) |
| Owner | zcoder maintainers |
| Target date | v1.15.0 |
| Status | ☐ Not started ☐ In progress ☐ In review ☑ Done |

**Task list**
- [x] ~~New module `claude_context_editing.py` mirroring `claude_cache.py` structure~~ — not needed
- [x] ~~`ContextEditingConfig` dataclass...`~~ — not needed
- [x] Function to build `context_management` payload block — already existed as `claude_tools.build_context_management()`
- [x] Wire into `claude_code.py` agent loop behind `--agent-context-editing` (opt-in)
- [x] Worked example added to `docs/` showing Compaction + context editing together (`docs/29_upgrade_v1.15.0.md`)
- [x] Confirm default behavior unchanged (opt-in only, `context_management=None` default)

**Sign-off**
- Reviewed by: zcoder maintainers  Date: v1.15.0 release
- Notes: The original gap-audit was wrong about this one — `claude_tools.py`
  already had a complete `build_context_management()`, so no new module
  was created. The real gap was narrower: `claude_code.py`'s agent loop
  never called it. Module(s) affected / Est. effort above are struck
  through rather than deleted, to keep an honest record of what the audit
  originally assumed vs. what was actually true.

---

## Form 3 — 🟠 P1: Agent Skills via the API (`skill_id`)

| Field | Value |
|---|---|
| Priority | 🟠 P1 |
| Module(s) affected | New: `claude_skills_api.py`; follow-up: `claude_excel.py`, `claude_powerpoint.py` |
| Est. effort | ~1 new file, ~120 lines (excel/pptx integration is a separate follow-up) |
| Owner | zcoder maintainers |
| Target date | v1.15.0 |
| Status | ☐ Not started ☐ In progress ☐ In review ☑ Done |

**Task list**
- [x] New module `claude_skills_api.py`
- [x] `list_skills()` wrapper
- [x] `SkillRef` helper for `skill_id` in Messages requests
- [x] CLI flag `--skills-list`
- [x] CLI flag `--skills-info ID` (info-only, matches `cmd_fable5_info` pattern)
- [x] **Follow-up PR (separate, not this one):** `--excel-native` / `--pptx-native` flags on `claude_excel.py` / `claude_powerpoint.py`, existing hand-rolled logic kept as fallback — landed in the same v1.15.0 pass, ahead of the original schedule

**Sign-off**
- Reviewed by: zcoder maintainers  Date: v1.15.0 release
- Notes: Follow-up item landed early rather than as a separate PR; no
  regression to the fallback path when Skills access isn't available.

---

## Form 4 — 🟡 P2: Usage and Cost API

| Field | Value |
|---|---|
| Priority | 🟡 P2 |
| Module(s) affected | New: `claude_admin_api.py` (renamed from planned `claude_usage_api.py`, folded with Form 5); cross-link: `claude_cost_optimizer.py` |
| Est. effort | ~1 file, ~100 lines. Requires Admin API key |
| Owner | zcoder maintainers |
| Target date | v1.15.0 |
| Status | ☐ Not started ☐ In progress ☐ In review ☑ Done |

**Task list**
- [x] New module `claude_admin_api.py`
- [x] `get_usage_report(start, end, group_by)` wrapper (plus `get_cost_report`)
- [x] CLI flag `--usage-report` (prints table)
- [x] Cross-link from `claude_cost_optimizer.py` docstring
- [x] CLI help text clearly flags Admin API key requirement (avoid silent 401)

**Sign-off**
- Reviewed by: zcoder maintainers  Date: v1.15.0 release
- Notes: Named `claude_admin_api.py`, not `claude_usage_api.py` — see
  Form 5, folded into the same module.

---

## Form 5 — 🟡 P2: API key management (Admin API)

| Field | Value |
|---|---|
| Priority | 🟡 P2 |
| Module(s) affected | `claude_admin_api.py` |
| Est. effort | ~80 lines, combined with Usage API module |
| Owner | zcoder maintainers |
| Target date | v1.15.0 |
| Status | ☐ Not started ☐ In progress ☐ In review ☑ Done (list/revoke — create is N/A by design) |

**Task list**
- [x] Decide module grouping — folded into `claude_admin_api.py` alongside Usage API
- [x] CLI flag `--admin-list-keys`
- [x] CLI flag `--admin-create-key NAME` — implemented as an explanation, not a real call: no documented create-key endpoint exists (Console-only, secret shown once), so this prints why rather than faking success
- [x] CLI flag `--admin-revoke-key ID`
- [x] Admin API auth requirements documented alongside Usage API

**Sign-off**
- Reviewed by: zcoder maintainers  Date: v1.15.0 release
- Notes: `--admin-create-key` deliberately does not call an endpoint —
  see the module docstring for why that's a documented boundary, not a
  gap.

---

## Form 6 — 🟡 P2: Compliance API

| Field | Value |
|---|---|
| Priority | 🟡 P2 |
| Module(s) affected | New: `claude_compliance_api.py`; integration: `main.py` (new `Compliance API` argument group + dispatch block) |
| Est. effort | Originally estimated N/A (documented gap only); actual: ~450 lines (client + all `cmd_*` wrappers) |
| Owner | zcoder maintainers |
| Target date | v1.16.0 |
| Status | ☐ Documented gap (default) ☑ Reconsidered — built |

**Task list**
- [x] Confirm gap remained documented in `ROADMAP.md` / `README.md` through v1.15.0
- [x] No speculative implementation in v1.15.0 — waited, as recommended
- [x] Revisit trigger arrived: the Compliance API is now real and documented
  at `platform.claude.com/docs/en/manage-claude/compliance-api*`
  (confirmed 2026-07-04), which is the "concrete request" condition the
  v1.15.0 recommendation named
- [x] `ComplianceApiClient`: documented retry contract (429 + retryable
  5xx back off exponentially 1s→60s; 400/401/403/404/409 never retry)
- [x] Activity Feed: list + cursor-safe pagination (`iterate_activities`)
- [x] Chats: list, get messages, hard-delete
- [x] Files: download (with `Content-Disposition` filename parsing), hard-delete
- [x] Projects: list, info, attachments, hard-delete
- [x] Directory: orgs, org users, org roles, org settings, groups, group members
- [x] Dry-run-by-default guard on every destructive `cmd_*`, requires
  explicit `yes=True` (`--compliance-yes`)
- [x] Surfaces the documented 403 scope-mismatch message with a concrete
  fix instead of a bare permission error
- [x] 23 new CLI flags wired into `main.py` under a `Compliance API`
  argument group, dispatch mirrors `claude_admin_api.py`'s block
- [x] Key fallback order documented: `--compliance-api-key` →
  `ANTHROPIC_COMPLIANCE_API_KEY` → `--admin-api-key` →
  `ANTHROPIC_ADMIN_API_KEY` (Admin key fallback reaches only the Activity
  Feed endpoint)
- [x] Tests: `tests/test_claude_compliance_api.py`, 28 tests, all passing

**Sign-off**
- Reviewed by: zcoder maintainers  Date: v1.16.0 release
- Notes: This is not a reversal of the v1.15.0 "leave as a gap" call —
  that recommendation's own stated exit condition was met, so building
  it now is consistent with the original plan, not a departure from it.

---

## Form 7 — 🟠 P1: Mid-conversation system messages

| Field | Value |
|---|---|
| Module(s) affected | `claude_cache.py`; integration: `main.py` (new `Prompt Caching` group flags + dispatch) |
| Est. effort | ~150 lines (builder + validator + threading through `generate_cached()`/`multi_turn_cached()`) |
| Owner | zcoder maintainers |
| Target date | v1.18.0 |
| Status | ☑ Done |

**Task list**
- [x] Confirmed genuinely absent — zero matches for `role.*system` message
  construction anywhere in the tree outside test fixtures, not just no
  module with a matching name
- [x] `build_mid_system_message(text)` — builds the `{"role": "system", ...}`
  message block (text-only content, per docs)
- [x] `validate_system_message_placement(messages)` — encodes all five
  documented placement rules (not first entry; not adjacent to another
  system message; must follow a user turn or an assistant turn ending in
  server tool use; cannot sit between a tool_use and its tool_result; must
  be the last entry or followed by an assistant turn) and raises a
  dedicated `SystemMessagePlacementError` naming which rule failed
- [x] `MID_SYSTEM_SUPPORTED_MODELS = {"claude-opus-4-8"}` model gate, since
  this feature is Opus 4.8 only (no beta header) per docs
- [x] `mid_system` param threaded through `generate_cached()`
- [x] `mid_system_updates` (turn-index → text map) threaded through
  `multi_turn_cached()` — the realistic use case, since the placement
  rules require existing conversation history to attach to
- [x] CLI: `--cache-multi-turn TEXT [TEXT...]`, `--cache-mid-system TEXT`,
  `--cache-mid-system-after N`, dispatched via new `cmd_cache_multi_turn()`
- [x] Confirm default behavior unchanged — `mid_system`/`mid_system_updates`
  both default to `None`/`{}`, no effect unless explicitly passed
- [x] Tests: `tests/test_claude_cache.py` (new file — this module had zero
  test coverage before this cycle)

**Sign-off**
- Reviewed by: zcoder maintainers  Date: v1.18.0 release
- Notes: Placement validation runs client-side before the request goes
  out, so a misplaced system message fails fast with a specific message
  instead of spending a round trip on the API's 400.

---

## Form 8 — 🟡 P2: Cache diagnostics (beta) — CLI wiring

| Field | Value |
|---|---|
| Module(s) affected | `main.py` only — `claude_cache.py`'s client-side support already existed |
| Est. effort | ~10 lines (one flag, one kwarg passthrough) |
| Owner | zcoder maintainers |
| Target date | v1.18.0 |
| Status | ☑ Done |

**Task list**
- [x] Initial grep for `cache_diagnostic`/`cache.diagnostic` found nothing
  and looked like a fresh P1/P2 gap
- [x] Read `claude_cache.py` directly before writing new code (per the
  Methodology note's "confirm with a second grep" correction) — found
  `diagnose=` on `generate_cached()`, the `cache-diagnosis-2026-04-07`
  beta header, the `diagnostics.previous_message_id` request field, and
  `cache_miss_reason` surfaced through `cache_stats()`/`print_cache_stats()`
  already fully implemented
- [x] Real gap identified: `main.py` never set `diagnose=True` anywhere —
  the feature was unreachable from the CLI despite being fully built
- [x] Added `--cache-diagnose` flag, wired to `cmd_cache_generate(diagnose=...)`
- [x] Tests: `tests/test_claude_cache.py` covers the `diagnose=True` request
  shape (both the first-call `previous_message_id: None` case and the
  second-call reference-prior-id case) and the beta header

**Sign-off**
- Reviewed by: zcoder maintainers  Date: v1.18.0 release
- Notes: Not a reversal or correction of any prior claim — Part 1 of
  `ROADMAP.md` always listed Prompt caching as covered by `claude_cache.py`
  and that was accurate; this was a CLI-reachability gap, not a coverage
  gap.

---

## Form 9 — 🟠 P1: Managed Agents memory stores

| Field | Value |
|---|---|
| Module(s) affected | `claude_agents_sdk.py`, `main.py` |
| Est. effort | ~90 lines + tests |
| Owner | zcoder maintainers |
| Target date | v1.19.0 |
| Status | ☑ Done |

**Task list**
- [x] Found via `requirements.txt` SDK-drift check (step 6 of the audit
  methodology), not a direct docs-feature-list grep: `anthropic-sdk-python`
  v0.116.0's changelog mentions a new `agent-memory-2026-07-22` beta
  header, which led to the Managed Agents memory-store docs pages
- [x] Confirmed absence with two differently-worded greps
  (`memory_store` and `memory.?store|agent-memory|resources.*memory`)
  before concluding it was a real gap
- [x] Checked the other two "memory" features already in the tree
  (`claude_memory.py`'s `memory_20250818` tool, Claude Code's local
  `MEMORY.md`) to confirm neither already implements this under a
  different name — confirmed they don't; different scope and storage
  model each
- [x] Added `ManagedAgentsClient.create_memory_store(name)`
- [x] Added `memory_store_id` param to `create_session()`, mounting a
  `{"type": "memory_store", "memory_store_id": ...}` `resources` entry
  and the new beta header when set
- [x] Added `cmd_agent_memory_store_create()` standalone helper
- [x] `cmd_managed_agent_run()` gained an optional `memory_store` param
- [x] CLI: `--agent-memory-store NAME`, `--agent-memory-store-create`
- [x] Tests: new `tests/test_claude_agents_sdk.py` (10 tests) — module
  had zero coverage before this cycle, so also covers pre-existing
  `PermissionMode`, `TOOL_PRESETS`, and `MANAGED_AGENTS_BETA`

**Sign-off**
- Reviewed by: zcoder maintainers  Date: v1.19.0 release
- Notes: Purely additive — `memory_store_id` defaults to `None` and
  `create_session()`'s existing callers are unaffected; `--agent-managed-run`
  behaves exactly as before when `--agent-memory-store` isn't passed.

---

## Form 10 — 🟠 P1 / 🟡 P2: Dreaming, Outcomes, Webhooks (native Multiagent orchestration deferred)

| Field | Value |
|---|---|
| Module(s) affected | `claude_agents_sdk.py`, `main.py` |
| Est. effort | ~180 lines + tests |
| Owner | zcoder maintainers |
| Target date | v1.20.0 |
| Status | ☑ Done (Dreaming, Outcomes, Webhooks) / ⏸ Deferred (native Multiagent orchestration) |

**Task list**
- [x] Re-checked Managed Agents docs for what shipped alongside the
  memory-store feature closed in v1.19.0 (per this cycle's step 6),
  surfacing Dreaming, Outcomes, Webhooks, and native Multiagent
  orchestration as candidates
- [x] Confirmed each candidate's absence with two differently-worded
  greps before writing it up: Dreaming (`dream`, then
  `curat|reflect.*session|memory.*consolidat`); Outcomes
  (`define_outcome`, then `outcome_evaluation|rubric`); Webhooks
  (`webhook`, only an unrelated comment matched); native Multiagent
  orchestration (`multiagent|coordinator.*agents`, confirmed distinct
  from the pre-existing client-side `--agent-orchestrate` by reading
  the code directly, not just grep output)
- [x] Added `ManagedAgentsClient.create_dream/.get_dream/.list_dreams/.cancel_dream`
  (`dreaming-2026-04-21` beta header)
- [x] Added `ManagedAgentsClient.define_outcome/.wait_for_outcome`;
  `cmd_managed_agent_run()` gained opt-in outcome params
- [x] Added `ManagedAgentsClient.register_webhook`
- [x] CLI: `--agent-dream(-sessions/-instructions/-list/-get)`,
  `--agent-outcome(-rubric/-max-iter)`, `--agent-webhook-register`,
  `--agent-webhook-events`
- [x] Tests: 16 new tests added to `tests/test_claude_agents_sdk.py`
  (26 total in that file)
- [ ] Native Multiagent orchestration — deliberately not implemented
  this cycle; see `ROADMAP.md`'s Priority Summary section for the full
  reasoning and stated exit condition

**Sign-off**
- Reviewed by: zcoder maintainers  Date: v1.20.0 release
- Notes: All three shipped features are purely additive —
  `outcome_description`/`outcome_rubric` default to `None` so
  `cmd_managed_agent_run()`'s existing plain-task behavior is unchanged
  when they're not passed. Native Multiagent orchestration intentionally
  left open with a stated exit condition, matching the Compliance API
  precedent from v1.15.0 → v1.16.0.

---

## Shared Definition of Done (all forms)

- [x] CLI flag follows house naming style (`--flag-name`)
- [x] Module docstring documents the feature and its relationship to any similar existing feature
- [x] Tests added/updated
- [x] `README.md` per-flag reference updated
- [x] `CHANGELOG.md` entry added
- [x] No regression to existing default behavior
- [x] `ROADMAP.md` updated — item moved from Part 2 (gap) to Part 1 (implemented)

## Rollup Status

| # | Item | Priority | Status |
|---|---|---|---|
| 1 | Server-side `fallbacks` param | 🔴 P0 | ✅ Done (v1.15.0) |
| 2 | Context editing | 🟠 P1 | ✅ Done (v1.15.0) |
| 3 | Agent Skills API (`skill_id`) | 🟠 P1 | ✅ Done (v1.15.0) |
| 4 | Usage and Cost API | 🟡 P2 | ✅ Done (v1.15.0) |
| 5 | API key management | 🟡 P2 | ✅ Done (v1.15.0) |
| 6 | Compliance API | 🟡 P2 | ✅ Done (v1.16.0) |
| 7 | Mid-conversation system messages | 🟠 P1 | ✅ Done (v1.18.0) |
| 8 | Cache diagnostics CLI wiring | 🟡 P2 | ✅ Done (v1.18.0) |
| 9 | Managed Agents memory stores | 🟠 P1 | ✅ Done (v1.19.0) |
| 10a | Managed Agents Dreaming | 🟠 P1 | ✅ Done (v1.20.0) |
| 10b | Managed Agents Outcomes | 🟠 P1 | ✅ Done (v1.20.0) |
| 10c | Managed Agents Webhooks | 🟡 P2 | ✅ Done (v1.20.0) |
| 10d | Managed Agents native Multiagent orchestration | 🟡 P2 | ⏸ Deferred (v1.20.0) |
| 11 | Managed Agents self-hosted sandboxes | 🟠 P1 | ✅ Done (v1.26.0) |
| 12 | Memory store beta-header regression fix + memory/memory-store CRUD | 🔴 P0 / 🟠 P1 | ✅ Done (v1.27.0) |
| 13 | CLI-to-API wiring audit (GitHub, Router, Prompt Optimizer, Metrics) | 🟠 P1 | ✅ Done (v1.31.0) |
| 14 | Claude Opus 5 catalog entry + fast-mode enforcement + fallbacks "default" | 🔴 P0 bug fix + 🟡 P2 | ✅ Done (v1.32.0) |

---

## Form 11 — 🟠 P1: Managed Agents self-hosted sandboxes

| Field | Value |
|---|---|
| Module(s) affected | `claude_agents_sdk.py`, `main.py` |
| Est. effort | ~90 lines + tests |
| Owner | zcoder maintainers |
| Target date | v1.26.0 |
| Status | ☑ Done |

**Task list**
- [x] Found via the docs-feature-list sweep (step 1 of the audit
  methodology): the Managed Agents docs tree lists "Self-hosted
  sandboxes" alongside "Cloud environment setup" as a peer configuration
  path, not a variant of it
- [x] Confirmed absence with a repo-wide grep for `self_hosted`/
  `self-hosted` before concluding it was a real gap — zero matches
- [x] Verified both the create config shape (`{"type": "self_hosted"}`,
  no networking/pool/capacity sub-fields, unlike `"cloud"`) and the
  `environments.work.stats()` read shape directly against current docs
  rather than guessing — both confirmed, so this did not need the
  "implemented defensively, needs a follow-up verification pass" caveat
  the v1.25.0 CMEK finding required
- [x] Added `env_type` param to `ManagedAgentsClient.create_environment()`
- [x] Added `ManagedAgentsClient.get_environment_work_stats(environment_id)`
- [x] Added `cmd_agent_env_self_hosted_create()` and
  `cmd_agent_env_work_stats()` CLI-facing wrappers
- [x] CLI: `--agent-env-self-hosted NAME`, `--agent-env-work-stats
  ENVIRONMENT_ID`
- [x] Tests: 6 new tests in `tests/test_claude_agents_sdk.py`
- [x] Deliberately did not build a worker/poller component (no concrete
  deployment target yet) — noted as a deferred, not abandoned, item in
  `docs/38_upgrade_v1.26.0_audit_and_impl.md`
- [x] Fixed a stale pre-existing test assertion in the same test file
  (`run_task` missing `stream_deltas=False`) while it was already open
- [x] Fixed `main.py`'s `VERSION` constant, which had drifted stale at
  `"1.16.0"`

**Sign-off**
- Reviewed by: zcoder maintainers  Date: v1.26.0 release
- Notes: Purely additive — `env_type` defaults to `"cloud"`, so every
  existing `create_environment()` caller is unaffected.

---

## Form 12 — 🔴 P0 bug fix + 🟠 P1: Memory store beta-header regression, memory/memory-store CRUD

| Field | Value |
|---|---|
| Module(s) affected | `claude_agents_sdk.py`, `main.py`, `tests/test_claude_agents_sdk.py` |
| Est. effort | ~260 lines + tests |
| Owner | zcoder maintainers |
| Target date | v1.27.0 |
| Status | ☑ Done |

**Task list**
- [x] Re-fetched `platform.claude.com/docs/en/release-notes/overview`
  live (not reused from a prior cycle) and re-read
  `.../managed-agents/memory` end to end per this cycle's step 6
  (drift check on an already-"done" area)
- [x] **Bug found:** `create_memory_store()` and `list_memories()` both
  sent `betas=[MANAGED_AGENTS_BETA, MEMORY_STORE_BETA]`; the July 2,
  2026 docs state this combination now 400s on memory store endpoints
  (`agent-memory-2026-07-22` replaces, not adds to,
  `managed-agents-2026-04-01` there)
- [x] Fixed both call sites to send `betas=[MEMORY_STORE_BETA]` alone
- [x] Confirmed `create_session()`'s `memory_store_id` branch is
  correctly unchanged — it's a `/v1/sessions` call, not a memory store
  endpoint, so the additive header combination still applies there
- [x] Updated the two pre-existing tests that asserted the now-wrong
  header combination (`test_create_memory_store_sends_expected_betas`,
  the `list_memories` beta-header assertion)
- [x] **Gap found:** memory store management (`retrieve`, `update`,
  `list`, `archive`, `delete`) and memory CRUD (`retrieve`, `create`,
  `update`, `delete`) were never built beyond `create_memory_store` and
  `list_memories`
- [x] Added `get_memory_store()`, `list_memory_stores()`,
  `archive_memory_store()`, `delete_memory_store()`
- [x] Added `create_memory()`, `get_memory()`, `update_memory()` (with
  `content_sha256` optimistic-concurrency precondition support),
  `delete_memory()`
- [x] Gave `create_memory_store()` the `description` param the docs'
  create call takes but the existing wrapper silently dropped
- [x] CLI: `--agent-memory-stores-list`
  (+`--agent-memory-stores-include-archived`),
  `--agent-memory-store-archive`, `--agent-memory-store-delete`
  (+`--agent-memory-store-delete-yes`, dry-run by default),
  `--agent-memory-get/-create/-update/-delete`
  (+`--agent-memory-id/-path/-content`, delete gated behind
  `--agent-memory-delete-yes`)
- [x] Tests: 13 new tests in `tests/test_claude_agents_sdk.py` (beta
  header correctness for every new method, dry-run/confirm gating for
  both delete commands)
- [x] Deliberately deferred memory versions (`list`/`retrieve`/`redact`)
  — audit/compliance-shaped feature, same "wait for a concrete request"
  call as Compliance API (v1.15.0→v1.16.0) and native Multiagent
  orchestration (v1.20.0); see `docs/39_upgrade_v1.27.0_audit_and_impl.md`
  for the exit condition
- [x] Checked API key expiration (July 8) and CMEK docs expansion (July
  10) release notes — confirmed non-gaps, documented why
- [x] Bumped `main.py`'s `VERSION` to `"1.27.0"`

**Sign-off**
- Reviewed by: zcoder maintainers  Date: v1.27.0 release
- Notes: Finding 1 is a regression fix (previously-correct code broken
  by a platform change), filed ahead of Finding 2's new-capability work
  since a live 400 on every memory-store call outranks an unbuilt
  feature. `create_session()`'s additive header usage was checked and
  left alone deliberately, not overlooked.

---

## Form 13 — 🟠 P1: CLI-to-API wiring audit (GitHub, Router, Prompt Optimizer, Metrics)

| Field | Value |
|---|---|
| Module(s) affected | `main.py`, `tests/test_cli_wiring.py` (new) |
| Est. effort | ~170 lines (main.py) + ~220 lines (new test file) |
| Owner | zcoder maintainers |
| Target date | v1.31.0 |
| Status | ☑ Done |

**Task list**
- [x] Different audit type this cycle: not platform.claude.com/docs vs.
  code, but `claude_*.py`'s own `cmd_*` functions vs. `main.py`'s
  dispatch — checked with `ast.parse` per module, not a docs fetch
- [x] Found 4 modules (`claude_github.py`, `claude_router.py`,
  `claude_prompt_optimizer.py`, `claude_metrics.py`) with 13 `cmd_*`
  functions total, none referenced in `main.py`
- [x] Caught and avoided a naming collision before wiring anything:
  `claude_prompt_optimizer.py`'s docstring specifies `--v2` for the
  second A/B variant, but `--v2` already exists as a `type=int` artifact
  flag — used `--ab-prompt-b` instead
- [x] Added argument groups: GitHub Integration, Multi-Agent Router,
  Prompt Optimizer, Metrics (local usage log)
- [x] Added dispatch blocks calling each `cmd_*` function with correct
  positional argument order (verified against each function's real
  signature, not assumed)
- [x] Evaluated `claude_evals.py`'s `cmd_eval` — confirmed superseded by
  the already-wired `claude_eval.py`, left unwired on purpose, recorded
  in `tests/test_cli_wiring.py`'s `KNOWN_EXCEPTIONS`
- [x] Evaluated `claude_router.py`'s `--route-add-agent` (docstring-only,
  no backing `cmd_*` function) — left as a follow-up, not guessed at
- [x] New `tests/test_cli_wiring.py`: parametrized regression test over
  every `claude_*.py` module (62 new tests total, includes flag-parsing
  and dispatch-level coverage for all 4 newly-wired modules)
- [x] Bumped `main.py`'s `VERSION` to `"1.31.0"`
- [x] `ROADMAP.md`, `CHANGELOG.md`, `README.md` updated

**Sign-off**
- Reviewed by: zcoder maintainers  Date: v1.31.0 release
- Notes: Purely additive — no existing flag, dest name, or dispatch
  order was changed. The `test_cli_wiring.py` regression test is the
  actual deliverable of this cycle as much as the 4 modules' flags are;
  it's what prevents this exact gap from reappearing for the next
  fully-built-but-unwired module.

---

## Form 14 — 🔴 P0 bug fix + 🟡 P2: Claude Opus 5, fast-mode enforcement, fallbacks "default"

| Field | Value |
|---|---|
| Module(s) affected | `claude_models.py`, `coder.py`, `claude_fable5.py`, `main.py` |
| Est. effort | ~120 lines + tests |
| Owner | zcoder maintainers |
| Target date | v1.32.0 |
| Status | ☑ Done |

**Task list**
- [x] Re-fetched `platform.claude.com/docs/en/release-notes/overview`
  live (not reused from a prior cycle), covering 2026-07-14 → 2026-07-26
- [x] **Gap found:** Claude Opus 5 (launched 2026-07-24) entirely
  missing from `MODEL_CATALOG`
- [x] Added `claude-opus-5` with correct specs and the effort/thinking
  breaking-change note vs. Opus 4.8
- [x] **Bug found:** `FAST_MODE_SUPPORTED`/`FAST_MODE_DEPRECATED` existed
  in `claude_models.py` but zero call sites read them — `coder.py` sent
  `speed:"fast"` unconditionally for any model
- [x] Replaced with `FAST_MODE_SUPPORTED`, `FAST_MODE_REMOVED_ERROR`
  (Opus 4.7, hard 400 since 2026-07-24),
  `FAST_MODE_REMOVED_SILENT` (Opus 4.6, silent standard-speed downgrade
  since 2026-06-29), and `validate_fast_mode()`
- [x] Wired `validate_fast_mode()` into `Coder.generate()` — Opus 4.7 +
  `--fast-mode` now short-circuits locally instead of sending a
  guaranteed-400 request
- [x] Added first-ever test coverage for `--fast-mode` payload behavior:
  5 new tests in `tests/test_coder.py`
- [x] **Gap found:** `fallbacks` parameter's new `"default"` mode
  (2026-07-24), gated behind a beta header distinct from the existing
  fallback-credit one
- [x] Extended `Fable5Client.fallback_chain` and `parse_fallback_chain()`
  to accept the literal string `"default"`; beta header attached only
  for that mode, list mode unchanged
- [x] 3 new tests in `tests/test_claude_fable5.py`
- [x] Checked and confirmed non-gaps: MCP tunnels, advisor `max_tokens`,
  `code_execution_20260120`
- [x] Deliberately deferred (documented, not dropped): mid-conversation
  tool changes (beta); July 22 Managed Agents items (agent-level
  `effort`, environment/memory-store webhooks, session `initial_events`,
  optional `version` on agent update, thread-level event deltas)
- [x] Bumped `main.py`'s `VERSION` to `"1.32.0"`
- [x] Full suite: 392 passed, 1 skipped, regression-clean

**Sign-off**
- Reviewed by: zcoder maintainers  Date: v1.32.0 release
- Notes: Finding 2 (fast-mode enforcement) is the highest-priority item
  here despite being smaller in surface area than the model-catalog
  addition — a client that can silently attempt a guaranteed-400 request
  is a worse failure mode than a model being briefly absent from a local
  cache, since `GET /v1/models` always remains the live source of truth
  for the latter.

---

## Form 15 — 🟡 P2: Dedicated deep-detail modules — Claude Opus 5, Sonnet 5, Haiku 4.5

| Field | Value |
|---|---|
| Module(s) affected | `claude_opus5.py` (new), `claude_sonnet5.py` (new), `claude_haiku45.py` (new), `main.py` |
| Est. effort | ~300 lines + tests |
| Owner | zcoder maintainers |
| Target date | v1.33.0 |
| Status | ☑ Done |

**Task list**
- [x] Requested as "deep upgrade Opus 5, and separate each current-tier
  model out in detail" — starting point was that every current-tier
  model lived only as one shallow `MODEL_CATALOG` row
- [x] **Finding 1:** Opus 5's effort/thinking breaking change existed
  only as a `notes` string, not enforcement — added
  `validate_effort_thinking()` client-side guard in `claude_opus5.py`,
  called inside `Opus5Client.call()` before any HTTP request is built
- [x] Added `OPUS5_EFFORT_BUDGETS` with the `xhigh` rung
  `claude_models.EFFORT_BUDGETS` still lacks
- [x] Flagged (not fixed): `INFERENCE_GEO_SUPPORTED` predates Opus 5's
  launch and doesn't list it — `--opus5-geo` warns as *unconfirmed*
  rather than assuming either way
- [x] **Finding 2:** Sonnet 5's "$2/$10 introductory through 2026-08-31"
  pricing note was prose, not a comparison the code makes — added
  `current_pricing(as_of=None)` with a real `date` comparison against
  `PROMO_END_DATE`, plus `estimate_cost_usd()` / `--sonnet5-cost IN,OUT`
- [x] Surfaced that Sonnet 5 is the one current-tier model without
  `service_tier`/Priority Tier support, while it does support
  `inference_geo` — `validate_service_tier()` warns rather than
  silently sending a rejected parameter
- [x] **Finding 3:** Haiku 4.5 is the only current-tier model on
  extended (not adaptive) thinking — added `build_thinking_param()` in
  `claude_haiku45.py`, always returns the extended shape, raises
  `ValueError` below the 1024-token floor
- [x] Resolved dateless alias `claude-haiku-4-5` → `claude-haiku-4-5-20251001`
  via `resolve_model_id()`; flagged fast-mode and `inference_geo` as
  unsupported for this model
- [x] All three modules follow existing `claude_fable5.py`/
  `claude_mythos5.py` conventions: shared `retry`/`CircuitBreaker`
  decorator, `cmd_*_info()`, `cmd_*_call()`, validators returning `None`
  (safe) or a message string (not safe)
- [x] `main.py` gained three new argument groups wired into the
  existing info-command/call-command dispatch blocks
- [x] New flags: `--opus5-info`/`--opus5`/`--opus5-effort`/
  `--opus5-disable-thinking`/`--opus5-fast`/`--opus5-geo`;
  `--sonnet5-info`/`--sonnet5`/`--sonnet5-geo`/`--sonnet5-cost`;
  `--haiku45-info`/`--haiku45`/`--haiku45-thinking-budget`
- [x] 30 new tests: `tests/test_claude_opus5.py` (9),
  `tests/test_claude_sonnet5.py` (9), `tests/test_claude_haiku45.py` (12)
- [x] Full existing suite passes with no regressions (excluding the
  pre-existing `fastapi`-dependent `test_webapp_server.py`, unrelated to
  this change)
- [x] Deliberately out of scope: `claude_models.EFFORT_BUDGETS` not
  patched (wider blast radius than this cycle); `--upgrade-all` not
  extended to target Sonnet 5/Haiku 4.5 (product decision)
- [x] `README.md`, `CHANGELOG.md`, `CHECKLIST.md`, `ROADMAP.md` all
  updated for this cycle
- [x] Bumped `main.py`'s `VERSION` to `"1.33.0"`

**Sign-off**
- Reviewed by: zcoder maintainers  Date: v1.33.0 release
- Notes: this cycle also closed a standing documentation gap —
  `CHECKLIST.md` had not been updated since v1.20.0 and this file had
  no entry for the v1.33.0 cycle itself; both backfilled alongside the
  code changes above.

---

## Form 16 — 🟠 P1 / 🟡 P2: Re-validation cycle — Opus, Sonnet, Haiku, Fable, Mythos

| Field | Value |
|---|---|
| Module(s) affected | `claude_tools.py`, `claude_sonnet5.py`, `main.py` |
| Est. effort | ~100 lines + tests |
| Owner | zcoder maintainers |
| Target date | v1.34.0 |
| Status | ☑ Done |

**Task list**
- [x] Requested: "upgrade all model below to latest update and
  validate: Opus, Sonnet, Haiku, Fable, Mythos"
- [x] Fetched `platform.claude.com/docs/en/release-notes/overview`
  directly (2026-07-26) — confirmed nothing newer than July 24, 2026
- [x] Re-checked `MODEL_CATALOG`, `FAST_MODE_*` sets, and every
  existing per-model validator (Opus 5 effort/thinking, Haiku 4.5
  thinking shape, Fable 5/Mythos 5 refusal/fallback) against the docs
  line by line — all still correct, no drift found
- [x] **Gap found:** mid-conversation tool changes beta
  (`mid-conversation-tool-changes-2026-07-01`; Fable 5, Mythos 5,
  Opus 4.8, Opus 5 only) — zero matches on
  `mid-conversation-tool-changes|mid_conversation_tool` anywhere in
  the tree before this cycle
- [x] Added `MID_CONVERSATION_TOOL_CHANGES_SUPPORTED`,
  `validate_mid_conversation_tool_change()`,
  `with_mid_conversation_tool_changes()` to `claude_tools.py`
- [x] Wired `--mid-conv-tool-check MODEL_ID` into `main.py`'s Tool Use
  group and dispatch block
- [x] **Gap found:** Sonnet 5 returns a 400 on any non-default
  `temperature`/`top_p`/`top_k` — `claude_sonnet5.py` didn't expose or
  guard these at all
- [x] Added `validate_sampling_params()`; `Sonnet5Client.call()` now
  accepts and rejects these client-side before building a request
- [x] Checked and confirmed non-gaps: Dreaming's July 10 Fable 5/
  Sonnet 5 expansion (Managed Agents concern, out of scope for
  per-model modules); Fable 5/Mythos 5 prefill/thinking guards (no
  live code path exposes either parameter)
- [x] 10 new tests: `tests/test_claude_tools.py` (+5),
  `tests/test_claude_sonnet5.py` (+5)
- [x] Full suite: 506 passed, regression-clean (excluding the
  pre-existing `fastapi`-dependent `test_webapp_server.py`)
- [x] `README.md`, `CHANGELOG.md`, `CHECKLIST.md` updated
- [x] Bumped `main.py`'s `VERSION` and `pyproject.toml` to `"1.34.0"`

**Sign-off**
- Reviewed by: zcoder maintainers  Date: v1.34.0 release
- Notes: this was a re-validation cycle, not a rebuild — the goal was
  confirming the five model modules still match the live docs, not
  assuming they do because they were correct at v1.33.0. Most of the
  catalog and validators held up; the two gaps found were both real
  and both defensive/beta-adoption gaps rather than active bugs.
