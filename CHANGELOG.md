# Changelog

Full per-version detail lives in `docs/*_upgrade_*.md` — this file is a
high-level index. Two project lineages (`ai-coder-cli-v1`, the modular
`claude_*.py`-per-feature codebase, and `ai-coder-cli-v2`, a smaller
single-`coder.py` CLI with its own PyInstaller packaging) were merged into
this release; see "v1.12.0" below for exactly what came from where.

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
network exception into the `AICoderError` hierarchy `retry()` already
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


- Merged in `ai-coder-cli-v2`'s standalone-executable packaging: `build.sh`
  / `build.bat` (PyInstaller, produces a single `dist/ai-coder` binary with
  no local Python required), `setup.sh` / `setup.bat` (venv + `.env` setup
  for running from source), `ai-coder.spec`, `LICENSE` (MIT).
- Added `.env.example` (referenced by `setup.sh`/`setup.bat` but missing
  from both source projects) documenting `ANTHROPIC_API_KEY` (required),
  `VOYAGE_API_KEY` (optional, `claude_embeddings.py`), `GITHUB_TOKEN`
  (optional, `claude_github.py`).
- `requirements.txt`: bumped minimum `anthropic` SDK to `>=0.75.0`,
  required for `client.beta.agents/.environments/.sessions`
  (`--agent-managed-run`, see `claude_agents_sdk.ManagedAgentsClient`).
- Everything else in `ai-coder-cli-v2` (`coder.py`, `config.py`, `utils.py`,
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
