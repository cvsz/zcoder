# ROADMAP.md

**AI Model Coder CLI (zcoder) — v1.32.0**
Last audited against `platform.claude.com/docs`: 2026-07-26 (release
notes overview, full July 14→24 window — see
`docs/44_upgrade_v1.32.0_release_validation.md`)

v1.32.0 re-fetched `platform.claude.com/docs/en/release-notes/overview`
directly and found **Claude Opus 5** (launched 2026-07-24) entirely
missing from `claude_models.MODEL_CATALOG`, plus a real bug: fast-mode
removal-behavior constants (`FAST_MODE_SUPPORTED`/`FAST_MODE_DEPRECATED`)
existed in `claude_models.py` but nothing ever checked them —
`coder.py` sent `speed:"fast"` unconditionally regardless of model, even
though Opus 4.7's fast mode was hard-removed (error) on 2026-07-24 while
Opus 4.6's was silently downgraded (no error) on 2026-06-29. Also added
the `fallbacks` parameter's new `"default"` mode. See
`docs/44_upgrade_v1.32.0_release_validation.md`. v1.31.0 was a
CLI-to-API *wiring* audit — cross-referencing every `claude_*.py`
module's own `cmd_*` functions against `main.py`'s dispatch, rather than
against platform.claude.com/docs. Found four fully-implemented, fully
undocumented-in-`main.py` modules (`claude_github.py`,
`claude_router.py`, `claude_prompt_optimizer.py`, `claude_metrics.py`) —
see `docs/43_upgrade_v1.31.0_cli_wiring_audit.md`. v1.30.0 re-ran the
docs gap-audit against
`build-with-claude/extended-thinking` and `.../adaptive-thinking`
directly and found `--thinking` was sending a request shape that 400s
on 5 of 9 models in `claude_models.MODEL_CATALOG` — see `CHANGELOG.md`
and `docs/42_upgrade_v1.30.0.md` for the full writeup. v1.29.0 was a
front-end deep-dive (Textual TUI + web console
streaming/sessions/theme/hardening — see `docs/41_upgrade_v1.29.0.md`),
not a docs re-audit.

This roadmap has two parts:

1. **Where zcoder stands today** — a full inventory of what's implemented,
   module by module, mapped to the Anthropic feature it covers.
2. **What's missing** — every gap found by cross-referencing zcoder against
   the live Features overview and API reference at platform.claude.com/docs,
   with a concrete implementation plan for each one, ranked by priority.

Nothing in Part 2 is speculative. Each gap was confirmed by grepping the
actual source tree for the relevant API surface (parameter names, endpoint
paths, header strings) and finding nothing — not just "no module with this
name," but no code path that could plausibly implement the feature under a
different name either.

---

## Part 1 — Current Coverage (46 modules, ~11,700 lines)

### Models & model metadata
| Feature | Module | Notes |
|---|---|---|
| Model catalog (Opus 5, Opus 4.8, Sonnet 5, Haiku 4.5, legacy tiers) | `claude_models.py` | Local cache + live `/v1/models` |
| Claude Fable 5 / Claude Mythos 5 | `claude_fable5.py`, `claude_mythos5.py` | Refusal detection, client-side fallback, fallback-credit header |
| Retired-model registry / deprecation scanner | `claude_models.py` | `--check-deprecated PATH` |
| Computer use | `claude_models.py` | `--computer-use PROMPT` |
| Adaptive / interleaved thinking, fast mode, effort levels | `claude_models.py`, `claude_thinking.py` | Mode auto-selected per model *(fixed v1.30.0 — see docs/42)* |

### Core Messages API features
| Feature | Module |
|---|---|
| Extended thinking | `claude_thinking.py` *(adaptive/effort routing fixed v1.30.0)* |
| Structured outputs | `claude_structured.py` *(stale beta header removed v1.30.0)* |
| Citations | `claude_citations.py` |
| Streaming | `claude_stream.py` |
| Batch processing | `claude_batch.py` |
| Token counting | `claude_tokens.py` |
| Prompt caching, Cache diagnostics (beta), Mid-conversation system messages *(v1.18.0)* | `claude_cache.py` |
| Data residency (`inference_geo`) | `coder.py`, `claude_models.py`, `claude_cost_optimizer.py` |
| Vision / multimodal | `claude_vision.py` |
| Embeddings | `claude_embeddings.py` |
| Files API | `claude_files.py` |

### Tools
| Feature | Module |
|---|---|
| Web search, web fetch | `claude_search.py`, `claude_tools.py` |
| Code execution | `claude_code_exec.py` |
| Advisor tool | `claude_advisor.py` |
| Bash, text editor, computer use (client-side tools) | `claude_tools.py`, `claude_models.py` |
| Memory tool | `claude_memory.py` |
| Tool search tool | `claude_tools.py` |
| Programmatic tool calling | `claude_tools.py` |
| Fine-grained tool streaming | `claude_stream.py` |
| MCP connector (`mcp_servers`, stdio/SSE/HTTP, MCP tunnels) | `claude_agents_sdk.py` |

### Context management
| Feature | Module |
|---|---|
| Compaction | `claude_code.py`, `claude_tools.py` |
| Token budgets | `claude_tools.py` |
| Context editing (`clear_tool_uses`, `clear_thinking`) | `claude_tools.py` (`build_context_management`), wired into `claude_code.py`'s agent loop via `--agent-context-editing` *(v1.15.0)* |

### Claude Code / Agent SDK
| Feature | Module |
|---|---|
| Agent loop, sessions, rewind/checkpointing | `claude_code.py` |
| Permissions, hooks, plan mode | `claude_hooks_perms_plan.py` |
| Plugins, output styles, sandbox, headless, settings | `claude_plugins.py`, `claude_output_styles.py`, `claude_sandbox.py`, `claude_settings.py` |
| Agent Skills (local `.claude/skills/*/SKILL.md`) | `claude_code.py` |
| Agent Skills API (platform, `skill_id`-based) | `claude_skills_api.py` *(v1.15.0)* |
| Managed Agents (environments, sessions) | `claude_agents_sdk.py` |
| Managed Agents memory stores (`resources: memory_store`) *(v1.19.0)* | `claude_agents_sdk.py` (`--agent-memory-store`, `--agent-memory-store-create`) |
| Managed Agents memory store management (retrieve/list/archive/delete) + memory CRUD (retrieve/create/update/delete) *(v1.27.0)* | `claude_agents_sdk.py` (`--agent-memory-stores-list`, `--agent-memory-store-archive`, `--agent-memory-store-delete`, `--agent-memory-get/-create/-update/-delete`) |
| Managed Agents Dreaming (research preview) *(v1.20.0)* | `claude_agents_sdk.py` (`--agent-dream`, `--agent-dream-list`, `--agent-dream-get`) |
| Managed Agents Outcomes (public beta) *(v1.20.0)* | `claude_agents_sdk.py` (`--agent-outcome`, `--agent-outcome-rubric`) |
| Managed Agents Webhooks (public beta) *(v1.20.0)* | `claude_agents_sdk.py` (`--agent-webhook-register`) |
| Managed Agents Vaults & credentials (public beta) *(v1.21.0)* | `claude_agents_sdk.py` (`--agent-vault-create`, `--agent-vault-add-credential`, `--agent-vault-list`, `--agent-vault`) |
| Managed Agents Scheduled deployments (public beta) *(v1.21.0)* | `claude_agents_sdk.py` (`--agent-schedule-create`, `--agent-schedule-list`, `--agent-schedule-cancel`) |
| Managed Agents native Multiagent orchestration *(v1.21.0)* | `claude_agents_sdk.py` (`build_multiagent_config`, `--agent-review-multiagent`) |
| Managed Agents Outcomes `file_id` rubric form *(v1.21.0)* | `claude_agents_sdk.py` (`--agent-outcome-rubric-upload`, `--agent-outcome-rubric-file`) |
| Managed Agents session-level overrides (public beta) *(v1.22.0)* | `claude_agents_sdk.py` (`--agent-override-json`, `--agent-override-model`, `--agent-override-system`) |
| Managed Agents vault `injection_location` (public beta) *(v1.22.0)* | `claude_agents_sdk.py` (`--agent-vault-injection-location`) |
| Managed Agents session event deltas (public beta) *(v1.22.0)* | `claude_agents_sdk.py` (`--agent-stream-deltas`) |
| code_execution tool version bump to `code_execution_20260120` *(v1.22.0)* | `claude_code_exec.py` (`--code-exec-version`) |
| Server tool version bumps: `code_execution_20260521`, `web_search_20260318`, `web_fetch_20260318`, `response_inclusion` *(v1.24.0)* | `claude_tools.py`, `claude_search.py` (`--response-inclusion`), `claude_code_exec.py` |
| Managed Agents memory listing (`agent-memory-2026-07-22` list behavior) *(v1.24.0)* | `claude_agents_sdk.py` (`--agent-memory-list`) |
| Admin API key `expires_at` surfaced *(v1.24.0)* | `claude_admin_api.py` (`--admin-list-keys`) |
| Claude Code Analytics API *(v1.24.0)* | `claude_admin_api.py` (`--claude-code-usage-report`) |
| Extended thinking `display: "omitted"` (GA) *(v1.25.0)* | `claude_thinking.py` (`--thinking-display-omitted`) |
| CMEK `external_keys` Admin API *(v1.25.0, ⚠️ unverified endpoint shape — see docs/37)* | `claude_admin_api.py` (`--cmek-list`) |
| Managed Agents self-hosted sandboxes (public beta) *(v1.26.0)* | `claude_agents_sdk.py` (`--agent-env-self-hosted`, `--agent-env-work-stats`) |
| Server-side model fallback (`fallbacks` param) | `claude_fable5.py` (`--fable5-fallback-chain`) *(v1.15.0)* |
| Admin API: usage/cost reporting, API key list/revoke | `claude_admin_api.py` *(v1.15.0)* |
| Admin API: Spend Limits API (Claude Enterprise only) *(v1.23.0)* | `claude_admin_api.py` (`--spend-limits-list`, `--spend-limit-set`, `--spend-limit-get`, `--spend-limit-delete`, `--spend-limit-requests-list`, `--spend-limit-request-approve`, `--spend-limit-request-deny`) |
| Admin API: Rate Limits API (read-only) *(v1.23.0)* | `claude_admin_api.py` (`--rate-limits`, `--rate-limits-workspace`) |
| Compliance API: Activity Feed, chats/files/projects, directory | `claude_compliance_api.py` *(v1.16.0)* |
| Workload Identity Federation (WIF, GA): token exchange + env-var auto-detection + service account/issuer/rule setup *(v1.23.0)* | `claude_wif.py` (`--wif-exchange-token`, `--wif-status`, `--wif-create-service-account`, `--wif-create-issuer`, `--wif-create-rule`, `--wif-list-*`) |

### Claude apps / product surfaces (non-API products)
| Product | Module |
|---|---|
| Claude Cowork (12 task types) | `cowork.py` |
| Claude in Excel analog | `claude_excel.py` |
| Claude in PowerPoint analog | `claude_powerpoint.py` *(v1.15.0)* |
| Claude in Chrome analog (headless browse loop) | `claude_chrome.py` *(v1.15.0)* |

### zcoder's own front ends (not an Anthropic product surface — how zcoder itself is used)
| Front end | Module | Notes |
|---|---|---|
| Argparse CLI | `main.py` | One-shot flags, `-p`/`-f`/`-o` |
| REPL | `claude_interactive.py` (`--interactive`) | Persistent multi-turn terminal chat |
| Full-screen TUI | `tui.py` (`--tui`) *(v1.29.0)* | Textual app; sidebar mirrors the web console, streamed replies. Optional dep (`textual`) |
| Web console | `webapp/` (`make build && make start`) | FastAPI + static JS; streaming, sessions sidebar, lite-markdown, theme toggle *(v1.28.0, upgraded v1.29.0)* |

### Everything else
Git integration, GitHub integration, cost optimizer, observability/metrics,
research (deep research style multi-source), RAG, evals, workflows,
sessions, personalities, interactive REPL, artifacts, projects, resilience
(retry/circuit breaker), security scanning.

*Note (v1.31.0):* "GitHub integration," "multi-agent router," "prompt
optimizer," and "local metrics" were listed here as covered — accurately,
in the sense that the modules existed and worked — but weren't actually
*reachable*: `main.py` had no CLI flags for any of `claude_github.py`,
`claude_router.py`, `claude_prompt_optimizer.py`, or `claude_metrics.py`
until this cycle wired them. See
`docs/43_upgrade_v1.31.0_cli_wiring_audit.md`.

Full per-flag reference: see `README.md`.

---

## Part 2 — Gap Audit vs. platform.claude.com/docs

Checked 2026-07-04 against the Features overview, API reference, and
Admin/Usage/Compliance API sections. Six real gaps, ranked by priority.

> **Status update (v1.15.0):** the five buildable gaps below (P0, both
> P1s, both usage/admin P2s) have been implemented — see
> `docs/29_upgrade_v1.15.0.md`, `CHANGELOG.md`, and `CHECKLIST.md` for
> what shipped and Part 1 above for where each landed. Compliance API
> remained a documented gap, not built, per its own recommendation below.
> One correction surfaced during implementation: the context-editing gap
> description below is **inaccurate** — `claude_tools.py` already had a
> complete `build_context_management()` with `clear_tool_uses` support;
> the grep that produced this audit missed it. The real gap was that
> `claude_code.py`'s agent loop never called it. Left as originally
> written below for an accurate record of the original audit; see the
> Part 1 table and v1.15.0 docs for the corrected version.
>
> **Status update (v1.16.0):** the sixth gap, Compliance API, is now
> also implemented — see `docs/30_upgrade_v1.16.0.md`,
> `CHANGELOG.md`, and `CHECKLIST.md`. This was the recommendation's own
> exit condition ("revisit only if there's an actual concrete request
> for it") being met, not a reversal of the original call to wait.

> **Status update (v1.19.0):** one new gap found and closed — Managed
> Agents memory stores. See the v1.19.0 audit cycle note below and
> `docs/32_upgrade_v1.19.0.md`.

> **Status update (v1.20.0):** three new gaps found and closed —
> Dreaming, Outcomes, and Webhooks (all Managed Agents features that
> shipped alongside/after the memory-store feature closed in v1.19.0).
> A fourth item, native Multiagent orchestration, was confirmed real and
> absent but deliberately left undocumented-as-built pending a concrete
> use case — see the v1.20.0 audit cycle note below and
> `docs/33_upgrade_v1.20.0.md`.

> **Status update (v1.26.0):** one new gap found and closed — Managed
> Agents self-hosted sandboxes (public beta). See the v1.26.0 audit cycle
> note and `docs/38_upgrade_v1.26.0_audit_and_impl.md`.

> **Status update (v1.27.0):** one regression found and fixed —
> `create_memory_store()`/`list_memories()` sent a beta-header
> combination that a July 2, 2026 platform change now rejects with a
> 400 on memory store endpoints — plus one gap found and closed: memory
> store management and memory CRUD beyond create/list. Memory versions
> (list/retrieve/redact) deliberately deferred. See the v1.27.0 audit
> cycle note and `docs/39_upgrade_v1.27.0_audit_and_impl.md`.

### 🔴 P0 — Server-side fallback (`fallbacks` parameter) ✅ IMPLEMENTED (v1.15.0)

**What it is:** A `fallbacks` array in the Messages API request body lets
you name up to 3 models in one call. If the primary model (e.g. Fable 5)
returns `stop_reason: "refusal"`, the platform itself retries the *same*
request against the next model in the list, server-side, in the same
round trip — no second HTTP call from the client.

**Why it was a gap:** `claude_fable5.py`'s `call_with_fallback()` only
implemented the *client-side manual* pattern (a second, separate `_post()`
call to `self.fallback_model`). That's a legitimate documented pattern
too, but it's a different one from the `fallbacks` param, and at the time
zcoder only had the manual path.

**What changed:** `Fable5Client` now takes a `fallback_chain` param; when
set, `call()` sends `payload["fallbacks"] = fallback_chain` and reads back
which model in the chain actually served the request instead of making a
second round trip. `call_with_fallback()` falls through to the legacy
manual-retry path only when `fallback_chain` is unset. New flag:
`--fable5-fallback-chain MODEL1,MODEL2`. See `tests/test_claude_fable5.py`
and `IMPLEMENTATION_CHECKLIST.md` Form 1.

**Original implementation plan (for reference):**
- Add `fallback_chain: list[str] = None` param to `Fable5Client.__init__`.
- In `call()`, if `fallback_chain` is set, add `payload["fallbacks"] = fallback_chain`
  instead of (not in addition to) the manual retry path.
- `call_with_fallback()` becomes a thin compatibility wrapper: if
  `fallback_chain` is set, just inspect the response's `stop_reason` and
  which model actually answered (docs specify the response echoes back
  which model in the chain served the request); only fall through to the
  manual retry path if `fallback_chain` is unset.
- New CLI flag: `--fable5-fallback-chain MODEL1,MODEL2` (up to 3 total
  including the primary).
- Update `claude_fable5.py`'s module docstring to explain both patterns and
  when to use each (manual retry: you want to change the prompt/system
  before retrying; `fallbacks` param: you want the platform to just handle
  it).

---

### 🟠 P1 — Context editing ✅ IMPLEMENTED (v1.15.0)

**What it is:** Configurable strategies (`clear_tool_uses`, thinking-block
handling) that automatically prune the context window mid-conversation —
distinct from Compaction, which does server-side summarization. Context
editing *removes* stale tool results/thinking blocks by rule; Compaction
*summarizes* the conversation. They solve the same problem (long-running
agent sessions blowing the context window) with different mechanisms and
are meant to be used together.

**Why it was a gap:** `claude_code.py` and `claude_tools.py` both had
Compaction. Neither had a `context_management` block in any payload.

**Correction during implementation:** the audit's premise that context
editing was entirely missing turned out to be *partly* wrong — a
`build_context_management()` helper already existed in `claude_tools.py`
with no caller wiring it up. The real gap was narrower than described:
finish wiring it into both agent loops, not build it from scratch.

**What changed:** `context_management` (with `clear_tool_uses` and
thinking-block handling) is now wired into both `claude_code.py`'s and
`claude_tools.py`'s agent loops via `--agent-context-editing` /
`use_context_management`, used alongside (not instead of) Compaction. See
`IMPLEMENTATION_CHECKLIST.md` Form 2 and `CHANGELOG.md`.

---

### 🟠 P1 — Agent Skills via the API (`skill_id`, not Claude Code's local loader) ✅ IMPLEMENTED (v1.15.0)

**What it is:** A platform-level Skills feature distinct from Claude
Code's local `.claude/skills/*/SKILL.md` convention: Anthropic-provided
pre-built Skills (PowerPoint, Excel, Word, PDF generation/editing) plus
custom Skills, referenced by `skill_id` in a Messages API request and
loaded server-side with progressive disclosure (the model only pulls in
skill content as needed rather than the whole thing up front).

**Why it was a gap:** `claude_code.py`'s skill loader
(`_load_skills_from_dir`) was real but was Claude Code's *local
filesystem* convention — it reads a directory on the caller's machine and
stuffs `SKILL.md` content into context itself. Nothing sent `skill_id` in
a request, listed available Skills, or uploaded a custom Skill.

**What changed:** `claude_skills_api.py` wraps the List/Create/Delete
Skills endpoints and builds the `skill_id` container reference for a
Messages request (`--skills-list`, `--skills-info ID`). The originally
planned follow-up also shipped in the same cycle: `claude_excel.py` and
`claude_powerpoint.py` gained `--excel-native` / `--pptx-native` flags
that route through the Anthropic-maintained pre-built Skill instead of
the local pandas/openpyxl or python-pptx loop, with the hand-rolled
implementation kept as the no-Skills-access fallback. See
`tests/test_claude_skills_api.py` and `IMPLEMENTATION_CHECKLIST.md` Form 3.

---

### 🟡 P2 — Usage and Cost API ✅ IMPLEMENTED (v1.15.0)

**What it is:** Org-level endpoints for querying actual historical spend
and usage (as opposed to estimating it from token counts you already have
locally).

**Why it was a gap:** `claude_cost_optimizer.py` only did local estimation
from token counts it was told about — it never called a usage/cost
endpoint.

**What changed:** folded into `claude_admin_api.py` (grouped with API key
management below, since both are thin Admin-API wrappers with the same
auth requirements) rather than a separate `claude_usage_api.py` module.
`get_usage_report(start, end, group_by)` and a matching cost-report call,
`--usage-report` / `--cost-report` CLI flags (plus `-start`/`-end`/
`-group-by`), and `claude_cost_optimizer.py`'s docstring cross-links to
it. Requires an Admin API key, not a regular one — the CLI help text
flags this so it doesn't silently 401. See `tests/test_claude_admin_api.py`.

---

### 🟡 P2 — API key management (Admin API) ✅ IMPLEMENTED (v1.15.0)

**What it is:** Programmatic create/list/rotate/revoke for API keys at the
organization level.

**Why it was a gap:** No code anywhere touched this endpoint family.

**What changed:** added to `claude_admin_api.py` alongside the Usage/Cost
API above — `--admin-list-keys`, `--admin-revoke-key ID` (update status to
revoke). Anthropic does not document a create-key endpoint (keys are
created through the Console UI, where the secret is shown exactly once —
creating one programmatically would be an exfiltration risk), so
`--admin-create-key NAME` is deliberately wired to an explanatory refusal
rather than a silent no-op or a fake success; see
`cmd_admin_create_key()`'s docstring in `claude_admin_api.py`.

---

### 🟡 P2 — Compliance API ✅ IMPLEMENTED (v1.16.0)

**What it is:** Org-level compliance/audit-log endpoints.

**Why it was a gap:** No matches anywhere in the tree, at the time this
audit was written (2026-07-04) — probably because the Compliance API
hadn't shipped yet, not because the audit missed it.

**Why P2, and why it was originally left as just a gap:** Least likely
of the six to matter for a personal/small-team coding CLI — built for
enterprise compliance teams, not developers. Guessing at endpoint shapes
without a concrete use case risked building the wrong thing, so the
original recommendation was to wait for one.

**What changed:** the exit condition in that recommendation ("revisit
only if there's an actual concrete request for it") was met. Implemented
in `claude_compliance_api.py` — Activity Feed, chats/files/projects
read+hard-delete (dry-run by default, `--compliance-yes` required),
directory endpoints, and the documented retry/pagination-cursor
contract. See `docs/30_upgrade_v1.16.0.md` and `CHECKLIST.md`.

---

### 🟠 P1 — Managed Agents memory stores ✅ IMPLEMENTED (v1.19.0)

**What it is:** A workspace-scoped, persistent, versioned file directory
(`memory_store`) that can be mounted into a Managed Agents session via the
`resources` param. Every write gets an immutable version for audit/
point-in-time recovery. Public beta, requires the `agent-memory-2026-07-22`
beta header (in addition to `managed-agents-2026-04-01`).

**Why it was a gap:** `claude_agents_sdk.py`'s `ManagedAgentsClient` had
`create_agent`/`create_environment`/`create_session`/`run_task` but nothing
touched a `memory_stores` endpoint, and `create_session` never sent a
`resources` param at all.

**Why P1, not P2:** without it, every Managed Agents session in zcoder is
necessarily stateless past the one throwaway session `cmd_managed_agent_run`
creates — there's no supported way for a hosted agent's work to survive
into a second session. That's a capability gap for the CLI's stated use
case (multi-session agentic coding), not just an admin/reporting nicety.

**Why this isn't a duplicate of existing "memory" features:** zcoder
already has two other things called "memory" — `claude_memory.py`'s
`memory_20250818` client-side tool, and Claude Code's local
`.claude`/`MEMORY.md` auto-memory. Both are real, different features, not
this one: the client-side tool requires the caller's own app to implement
storage and is scoped to a single Messages API conversation; Claude Code's
auto-memory never leaves the developer's machine. Managed Agents memory
stores are the only one of the three that's Anthropic-hosted, versioned,
and shared across a Managed Agents agent's sessions.

**What changed:** `ManagedAgentsClient.create_memory_store(name)` wraps
`client.beta.memory_stores.create`; `create_session()` gained an optional
`memory_store_id` param that, when set, adds a
`{"type": "memory_store", "memory_store_id": ...}` entry to `resources`
and includes the new beta header. New CLI flags: `--agent-memory-store
NAME` (create/reuse and mount into `--agent-managed-run`'s session) and
`--agent-memory-store-create` (create a store standalone, for reuse
across multiple later runs under the same name). See
`tests/test_claude_agents_sdk.py` and `IMPLEMENTATION_CHECKLIST.md`
Form 9.

---

## Priority Summary

### 🟠 P1 — Managed Agents Dreaming ✅ IMPLEMENTED (v1.20.0)

**What it is:** A research-preview process that reads a memory store
alongside past session transcripts and produces a new, curated output
memory store: duplicates merged, stale/contradicted entries replaced,
recurring patterns promoted to top-level memories. Requires the
`dreaming-2026-04-21` beta header in addition to `managed-agents-2026-04-01`.

**Why it was a gap:** `claude_agents_sdk.py`'s `ManagedAgentsClient`
gained `create_memory_store`/`create_session` memory-store wiring in
v1.19.0 but nothing touched a `dreams` endpoint. A first grep for
`dream` found nothing; a second, differently-worded grep for
`curat|reflect.*session|memory.*consolidat` also came up empty before
this was written up as a real gap.

**Why P1, not P2:** without it, a memory store only ever accumulates —
there's no supported way to clean up duplicates/staleness short of
manually calling `memories.delete` one at a time. For any Managed
Agents workflow that runs long enough to make memory stores worth using
at all, that's a capability gap, not just a nicety.

**What changed:** `ManagedAgentsClient.create_dream(memory_store_id,
session_ids=None, model=..., instructions=None)` wraps
`client.beta.dreams.create`; `.get_dream()`, `.list_dreams()`, and
`.cancel_dream()` wrap the matching read/list/cancel endpoints. New CLI
flags: `--agent-dream STORE_ID` (+ `--agent-dream-sessions`,
`--agent-dream-instructions`), `--agent-dream-list`, `--agent-dream-get
DREAM_ID`. See `tests/test_claude_agents_sdk.py` and
`IMPLEMENTATION_CHECKLIST.md` Form 10.

---

### 🟠 P1 — Managed Agents Outcomes ✅ IMPLEMENTED (v1.20.0)

**What it is:** A `user.define_outcome` session event (description +
rubric + `max_iterations`) that starts a rubric-graded self-correction
loop: a separate grader model evaluates the agent's work against the
rubric in its own context window, and the agent revises until the
grader is satisfied or `max_iterations` is hit. Public beta, no extra
beta header beyond `managed-agents-2026-04-01`.

**Why it was a gap:** `ManagedAgentsClient.run_task()` only ever sent a
plain `user.message` event and stopped at `session.status_idle` — there
was no code path that sent `user.define_outcome` or handled
`span.outcome_evaluation_*` events. Confirmed absent with a grep for
`define_outcome|outcome_evaluation|rubric` before writing this up.

**Why P1, not P2:** this is a different, independently-gradeable
execution mode for the CLI's core Managed Agents use case (autonomous
coding tasks), not an admin/reporting convenience — it changes what
"done" means for a session, from "the agent stopped talking" to "an
independent grader confirmed the rubric is met."

**What changed:** `ManagedAgentsClient.define_outcome(session_id,
description, rubric_text, max_iterations=3)` sends the event;
`.wait_for_outcome(session_id)` streams until a terminal
`span.outcome_evaluation_end`. `cmd_managed_agent_run()` gained opt-in
`outcome_description`/`outcome_rubric`/`outcome_max_iterations` params —
when both description and rubric are given it runs the outcome loop
instead of `run_task()`; otherwise behavior is unchanged. New flags:
`--agent-outcome DESC`, `--agent-outcome-rubric FILE`,
`--agent-outcome-max-iter N`. See `tests/test_claude_agents_sdk.py` and
`IMPLEMENTATION_CHECKLIST.md` Form 10.

---

### 🟡 P2 — Managed Agents Webhooks ✅ IMPLEMENTED (v1.20.0)

**What it is:** Subscribe a URL to Managed Agents lifecycle events
(session, outcome, dream) so a long-running task doesn't need a client
holding an SSE stream open. Public beta.

**Why it was a gap:** No code anywhere called a `webhooks` endpoint;
confirmed with a grep for `webhook` finding only an unrelated comment.

**Why P2:** the CLI's existing `run_task()`/`wait_for_outcome()` stream
patterns cover the CLI's own single-process use case adequately;
webhooks matter most for server-side integrations outside this CLI's
current scope, similar in kind to the Usage/Cost and API-key-management
P2s from earlier cycles.

**What changed:** `ManagedAgentsClient.register_webhook(url,
event_types=None)` wraps `client.beta.webhooks.create`. New flags:
`--agent-webhook-register URL`, `--agent-webhook-events LIST`. See
`tests/test_claude_agents_sdk.py` and `IMPLEMENTATION_CHECKLIST.md`
Form 10.

---

### 🟡 P2 — Managed Agents native Multiagent orchestration ⏸ DEFERRED (v1.20.0)

**What it is:** A lead/specialist coordinator topology configured on
the Agent resource itself (`multiagent: {type: "coordinator", agents:
[...]}`), where a lead agent decomposes a task and delegates to up to
20 specialist subagents running in parallel *inside the same Managed
Agents session*, sharing one filesystem and one event stream. Public
beta.

**Why it looked like a gap:** `claude_agents_sdk.py` already has
`--agent-orchestrate` / `ManagedAgent.orchestrate()` /
`spawn_subagent()`, but that's a client-side pattern: it makes separate
Messages API calls per subagent from the local process, with no shared
Managed Agents session, no shared sandbox filesystem, and no
`multiagent` field on any Agent resource. A grep for
`multiagent|coordinator.*agents|"type".*"coordinator"` confirmed zero
matches for the native feature, so this is a real, additional gap on
top of the existing client-side orchestration — not a rename of it.

**Why deferred rather than built:** the native feature's value is
specifically the shared-sandbox, shared-event-stream, in-session
delegation model — subagents that can all read/write the same files and
that the lead agent can "check back in with... mid-workflow." Building
a faithful wrapper means designing how `claude_agents_sdk.py` exposes
per-subagent model/prompt/tool configuration and multi-thread event
handling, which is a meaningfully larger surface than the other three
gaps closed this cycle, and zcoder doesn't yet have a concrete
multi-subagent-in-one-session use case to build it against (the
existing `--agent-orchestrate` already covers "decompose a goal into
independent subtasks" for zcoder's actual usage patterns). Same
reasoning the Compliance API used between v1.15.0 and v1.16.0.

**Exit condition:** revisit if there's an actual concrete need for
subagents to share a live sandbox/filesystem within a single Managed
Agents session, rather than the current independent-Messages-API-calls
pattern.

---

## Priority Summary

| Priority | Item | Rationale |
|---|---|---|
| 🔴 P0 | Server-side `fallbacks` param | ✅ Done v1.15.0 — strictly better than the prior client-side-only fallback |
| 🟠 P1 | Context editing | ✅ Done v1.15.0 — wired existing `build_context_management()` into `claude_code.py` |
| 🟠 P1 | Agent Skills API (`skill_id`) | ✅ Done v1.15.0 — plus the `--excel-native`/`--pptx-native` follow-up in the same cycle |
| 🟡 P2 | Usage and Cost API | ✅ Done v1.15.0 — folded into `claude_admin_api.py` |
| 🟡 P2 | API key management | ✅ Done v1.15.0 — same module; no create-key (Anthropic doesn't expose one) |
| 🟡 P2 | Compliance API | ✅ Done v1.16.0 — exit condition ("concrete request") was met |
| 🟠 P1 | Mid-conversation system messages | ✅ Done v1.18.0 — new in `claude_cache.py`, Opus 4.8 only |
| 🟡 P2 | Cache diagnostics CLI wiring | ✅ Done v1.18.0 — client support existed since ~v1.10.x, `--cache-diagnose` was the missing piece |
| 🟠 P1 | Managed Agents memory stores | ✅ Done v1.19.0 — new in `claude_agents_sdk.py`, distinct from the two other "memory" features already in the tree |
| 🟠 P1 | Managed Agents Dreaming | ✅ Done v1.20.0 — research preview, curates a memory store's contents without modifying the input store |
| 🟠 P1 | Managed Agents Outcomes | ✅ Done v1.20.0 — public beta, rubric-graded self-correction loop, opt-in alternative to plain `run_task()` |
| 🟡 P2 | Managed Agents Webhooks | ✅ Done v1.20.0 — public beta, out-of-band notifications alongside existing SSE stream patterns |
| 🟡 P2 | Managed Agents native Multiagent orchestration | ⏸ Deferred v1.20.0 — confirmed real, larger surface than the other three, no concrete use case yet |

Every buildable item raised by an audit cycle to date has been closed;
one (native Multiagent orchestration) is a documented, deliberate defer
with a stated exit condition, matching how the Compliance API gap was
handled between v1.15.0 and v1.16.0. See the v1.20.0 audit note below
for how this cycle's items were found.

## v1.18.0 audit cycle (2026-07-08)

Re-ran the methodology below against the live docs. Two real findings,
both closed in this cycle — see `CHANGELOG.md` and
`docs/31_upgrade_v1.18.0.md` for the full writeup:

- **Mid-conversation system messages** — genuinely absent (zero matches
  for `role.*system` anywhere in the tree outside test fixtures). New,
  Opus-4.8-only feature: `role: "system"` messages appended mid-`messages`
  to update instructions without invalidating a cached prefix. Added
  `build_mid_system_message()`, `validate_system_message_placement()`
  (encodes all five documented placement rules), and threaded a
  `mid_system` / `mid_system_updates` param through both
  `generate_cached()` and `multi_turn_cached()` in `claude_cache.py`.

- **Cache diagnostics (beta) — CLI wiring only.** The initial grep for
  `cache_diagnostic`/`cache.diagnostic` found nothing and looked like a
  fresh gap, but the feature itself (`diagnose=` param, `cache-diagnosis-
  2026-04-07` beta header, `cache_miss_reason` surfaced via
  `cache_stats()`) was already fully implemented in `claude_cache.py` —
  the grep pattern just didn't match the actual identifier names used
  (`diagnose`, `diagnostics`, `cache_miss_reason`). The real, narrower gap:
  nothing in `main.py` ever set `diagnose=True`, so the feature was
  unreachable from the CLI. Added `--cache-diagnose`.

Also checked for drift (not just net-new features) per this cycle's
methodology: `claude_models.py`'s catalog (Fable 5, Mythos 5, Opus 4.8,
Sonnet 5, Haiku 4.5, legacy tiers) matches the live Models overview
exactly — no stale entries, no missing releases. No `requirements.txt`
version drift found either.

`claude_cache.py` had zero test coverage before this cycle; added
`tests/test_claude_cache.py` (18 tests) covering both the pre-existing
caching behavior and both features closed above.

## v1.19.0 audit cycle (2026-07-08)

Re-ran the methodology below against the live docs. One real finding,
closed in this cycle — see `CHANGELOG.md` and
`docs/32_upgrade_v1.19.0.md` for the full writeup:

- **Managed Agents memory stores** — genuinely absent. Found not by
  grepping the docs' feature list directly but by checking
  `requirements.txt`'s SDK-pin drift first (per this cycle's step 6):
  `anthropic-sdk-python` v0.116.0's release notes mention a new
  `agent-memory-2026-07-22` beta header, which led to the Managed
  Agents memory-store docs pages. A first grep for `memory_store`
  confirmed zero matches, and a second, differently-worded grep for
  `memory.?store|agent-memory|resources.*memory` also came up empty
  before concluding it was a real gap, per this cycle's step 3.

Checked for false positives on the two other names in the tree that
contain "memory" (`claude_memory.py`'s `memory_20250818` tool,
Claude Code's local `MEMORY.md` auto-memory) before writing the gap —
neither implements the `memory_store` resource type or talks to a
`memory_stores` endpoint, so this was not a case of the grep missing an
existing implementation under a different name.

Also checked for drift (not just net-new features) per this cycle's
methodology: `claude_models.py`'s catalog still matches the live Models
overview exactly — no stale entries, no missing releases. The
`requirements.txt` pin (`anthropic>=0.75.0`) itself needed no change
(it's a floor, not an exact pin, and the installed/available SDK
version is well above it) — but checking the SDK's own changelog for
drift, rather than just the pin string, is what surfaced the memory-store
gap above.

`claude_agents_sdk.py` had zero test coverage before this cycle; added
`tests/test_claude_agents_sdk.py` (10 tests) covering both pre-existing
behavior (`PermissionMode`, `TOOL_PRESETS`, the `MANAGED_AGENTS_BETA`
header) and the new memory-store support closed above.

## v1.20.0 audit cycle (2026-07-08)

Re-ran the methodology below against the live docs. Per this cycle's
step 6, re-checked the Managed Agents docs for what shipped alongside
the memory-store feature closed in v1.19.0 (the v1.19.0 note had
flagged "Dreaming" as a name seen mentioned nearby but not yet
investigated). That led to three real, closed findings and one real,
deferred finding:

- **Dreaming** — genuinely absent (research preview). A first grep for
  `dream` found zero matches; a second, differently-worded grep for
  `curat|reflect.*session|memory.*consolidat` also came up empty before
  concluding it was a real gap, per this cycle's step 3.
- **Outcomes** — genuinely absent (public beta). A first grep for
  `define_outcome` found zero matches; a second grep for
  `outcome_evaluation|rubric` also came up empty.
- **Webhooks** — genuinely absent (public beta). A grep for `webhook`
  matched only an unrelated comment in `claude_agents_sdk.py`'s
  docstring noting the *existing* SSE-stream approach as an alternative
  to webhooks — not an implementation.
- **Native Multiagent orchestration** — genuinely absent as a Managed
  Agents Agent-resource feature (`multiagent: {type: "coordinator", ...}`).
  Confirmed this is not the same as the pre-existing client-side
  `--agent-orchestrate` (checked both greps and read the code directly,
  per this cycle's step 4, since `orchestrate`/`Orchestrator` appear
  throughout `claude_agents_sdk.py` already and a naive grep could have
  produced a false "already covered"). Real gap, but deliberately
  deferred — see the Priority Summary section above for the full
  reasoning and exit condition.

Also checked for drift (not just net-new features) per this cycle's
methodology: `claude_models.py`'s catalog still matches the live Models
overview exactly (Fable 5, Mythos 5, Opus 4.8, Sonnet 5, Haiku 4.5, plus
the legacy 4.5/4.6/4.7 tiers) — no stale entries, no missing releases,
no new retirements beyond what's already in `RETIRED_MODELS`. The
`requirements.txt` floor pin (`anthropic>=0.75.0`) needed no change.

`claude_agents_sdk.py` already had test coverage from v1.19.0; added 16
more tests to `tests/test_claude_agents_sdk.py` (26 total in that file)
covering Dreaming, Outcomes, and Webhooks.

## v1.27.0 audit cycle (2026-07-13)

Re-ran the methodology below against a live fetch of the release-notes
overview (not reused from the v1.26.0 cycle) and, per step 6, re-read
the Managed Agents memory docs page end to end rather than just
re-checking for net-new top-level release-note entries. That surfaced
two findings — one regression, one gap — see `CHANGELOG.md` and
`docs/39_upgrade_v1.27.0_audit_and_impl.md` for the full writeup:

- **Regression (🔴 P0):** `create_memory_store()` and `list_memories()`
  were sending `betas=[MANAGED_AGENTS_BETA, MEMORY_STORE_BETA]`, a
  combination the July 2, 2026 docs say now 400s on memory store
  endpoints (`agent-memory-2026-07-22` replaces, not adds to,
  `managed-agents-2026-04-01` there). This is the first cycle where a
  finding was "previously-correct code broken by a platform change"
  rather than "code never written" — filed and fixed ahead of the P1
  gap below.
- **Gap (🟠 P1):** memory store management (`retrieve`/`update`/`list`/
  `archive`/`delete`) and memory CRUD (`retrieve`/`create`/`update`/
  `delete`) were never built beyond the `create`/`list` pair from
  v1.19.0/v1.24.0. Closed this cycle; memory *versions*
  (`list`/`retrieve`/`redact`) deliberately deferred as an
  audit/compliance-shaped feature with no concrete zcoder use case yet
  — same reasoning pattern as the Compliance API (v1.15.0 → v1.16.0)
  and native Multiagent orchestration (v1.20.0 → still deferred).

Also checked for drift (not just net-new features) per this cycle's
methodology: `claude_models.py`'s catalog still matches the live Models
overview exactly — no new releases since Claude Sonnet 5 (June 30,
2026). Two release notes since the last cycle were checked and
confirmed non-gaps: API key expiration (July 8 — Console-only UI
feature, not a new API parameter) and the CMEK content-preservation
Access Transparency docs expansion (July 10 — documentation-only,
no new endpoint or parameter).

`claude_agents_sdk.py`'s test file gained 13 new tests this cycle (on
top of the 2 fixed to match the corrected beta-header behavior).



Everything in Part 1's coverage tables. If it's checked off there, it's
implemented and tested, not just planned.

## Methodology note

This audit was produced by fetching the live Features overview and API
reference from `platform.claude.com/docs` (checked 2026-07-08) and grepping
the zcoder source tree for the concrete API surface of each feature —
parameter names (`fallbacks`, `skill_id`, `clear_tool_uses`, `diagnostics`,
`role: "system"`), endpoint paths, and beta header strings — rather than
trusting module docstrings or README changelog entries at face value.
Where a docstring claimed coverage that the grep didn't confirm, the grep
won — except where the grep itself was wrong (see the Cache diagnostics
correction above): confirm with a second, differently-worded grep before
concluding a feature is missing, not just one pattern match.

## Note on cycles after v1.27.0

Audit cycles from v1.28.0 through v1.36.0 are documented in `CHANGELOG.md`
(high-level index) and their individual `docs/*_upgrade_*.md` writeups
rather than as new sections in this file — this file's Part 2 gap-audit
narrative wasn't kept current past v1.27.0 in practice, matching the same
pattern `CHECKLIST.md` notes about itself. `CHANGELOG.md` is the
authoritative index of every cycle in order.
