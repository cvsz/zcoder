# AI Model Coder CLI — v1.29.0 "TUI + Web console upgrade"
All Claude API Features + Claude Code / Agent SDK + Cowork + Plugins

## New in v1.29.0 — Textual TUI + web console streaming/sessions/theme upgrade

A third front end joins the plain CLI and the web console: `--tui` opens
a full-screen terminal interface (`tui.py`, built on
[Textual](https://textual.textualize.io/)) with the same model /
personality / agent-role / skill-focus sidebar as the web console, a
scrolling transcript, and live token-by-token streaming — no browser
needed. `textual` is an optional dependency; `--tui` prints a clear
install hint if it's missing rather than a traceback.

The web console (`webapp/`) gets four additions, none of which change
existing endpoint behaviour:
- **Streaming** — new `POST /api/chat/stream` (Server-Sent Events);
  the frontend's "stream response" toggle uses it by default, falling
  back to the original blocking `/api/chat` when unchecked.
- **Sessions sidebar** — new `GET /api/sessions` lists every in-memory
  session with a preview and turn count; the frontend renders it and
  lets you click back into an old session's `/api/sessions/{id}`
  transcript.
- **Lite markdown** — fenced code blocks render with a monospace block
  and a copy button; inline `` `code` `` gets a pill. No external
  markdown library, consistent with the frontend's dependency-free
  design.
- **Light/dark theme toggle**, and backend hardening: `ChatRequest`
  field validation (temperature/max_tokens bounds, a prompt length
  cap) and a simple per-IP fixed-window rate limit (429 past 30
  requests/min) on both chat endpoints.

```bash
python main.py --tui        # or: make tui
make build && make start    # web console, unchanged — http://localhost:8420
```

See `docs/41_upgrade_v1.29.0.md` for the full write-up.

## New in v1.28.0 — Web console (frontend + backend + lifecycle Makefile)

A browser-based chat UI now sits alongside the CLI — same core
(`coder.Coder`, personalities, skills, agent roles, health checks), just
reachable from a browser instead of a terminal. See `webapp/README.md`
for the full write-up and `CHANGELOG.md` for what's new.

```bash
make build && make start   # http://localhost:8420
make stop / restart / update / upgrade / status / logs
```

## New in v1.27.0 — Memory store beta-header regression fix + memory/memory-store CRUD

One bug fixed, one gap closed from re-running `ROADMAP.md`'s gap-audit
methodology against platform.claude.com/docs (checked 2026-07-13); see
`IMPLEMENTATION_CHECKLIST.md` Form 12 and
`docs/39_upgrade_v1.27.0_audit_and_impl.md` for the full write-up.

```bash
# BUG FIX -- create_memory_store()/list_memories() were sending both
# managed-agents-2026-04-01 and agent-memory-2026-07-22 beta headers on
# memory store endpoints; a July 2, 2026 platform change made the
# newer header REPLACE the older one there, so sending both now 400s.
# Both call sites now send agent-memory-2026-07-22 alone -- no CLI
# surface change, just a fix to calls that were silently broken since
# July 2, 2026 (existing --agent-memory-store-create / --agent-memory-list
# flags now actually work again).

# P1 -- memory store management: list/inspect/archive/permanently
# delete stores directly, without spinning up a session
python main.py --agent-memory-stores-list --agent-memory-stores-include-archived
python main.py --agent-memory-store-archive memstore_01AbCDefGhIjKlMnOpQrStUv
python main.py --agent-memory-store-delete memstore_01AbCDefGhIjKlMnOpQrStUv \
    --agent-memory-store-delete-yes   # dry-run without --...-yes

# P1 -- memory CRUD: seed/correct/inspect individual memories directly,
# without a live agent session (review workflows, pre-seeding a store,
# fixing a bad memory)
python main.py --agent-memory-create memstore_01AbCD \
    --agent-memory-path "/preferences/formatting.md" \
    --agent-memory-content "Always use tabs, not spaces."
python main.py --agent-memory-get memstore_01AbCD --agent-memory-id mem_01XyZ
python main.py --agent-memory-update memstore_01AbCD --agent-memory-id mem_01XyZ \
    --agent-memory-content "Always use 2-space indentation."
python main.py --agent-memory-delete memstore_01AbCD --agent-memory-id mem_01XyZ \
    --agent-memory-delete-yes   # dry-run without --...-yes
```

## New in v1.26.0 — Managed Agents self-hosted sandboxes

One item closed from re-running `ROADMAP.md`'s gap-audit methodology
against platform.claude.com/docs (checked 2026-07-13); see
`IMPLEMENTATION_CHECKLIST.md` Form 11 and
`docs/38_upgrade_v1.26.0_audit_and_impl.md` for the full write-up.

```bash
# P1 -- Self-hosted sandboxes (public beta): run Managed Agents tool
# execution on infrastructure you control instead of Anthropic's cloud
# sandbox. Creating the environment is the only part this CLI does for
# you -- generating the environment key is Console-only, and running a
# worker (EnvironmentWorker SDK / `ant beta:worker poll`) is a separate
# long-lived process you run yourself.
python main.py --agent-env-self-hosted my-ci-sandbox

# Check whether a worker is actually connected before pointing a session
# at a self-hosted environment -- workers_polling=0 means sessions will
# queue forever instead of failing outright
python main.py --agent-env-work-stats env_01AbCDefGhIjKlMnOpQrStUv
```

## New in v1.20.0 — Dreaming, Outcomes, Webhooks (Managed Agents)

Three items closed from re-running `ROADMAP.md`'s gap-audit methodology
against platform.claude.com/docs (checked 2026-07-08); see
`IMPLEMENTATION_CHECKLIST.md` Form 10 and `docs/33_upgrade_v1.20.0.md`
for the full write-up. Native Managed Agents Multiagent orchestration
was found but deliberately deferred — see that doc and `ROADMAP.md`.

```bash
# P1 -- Dreaming (research preview): curate a memory store by reviewing
# it alongside past session transcripts, producing a new, cleaned-up
# output store (duplicates merged, stale entries dropped, patterns
# promoted). The input store is never modified.
python main.py --agent-dream project-x-notes-store-id \
    --agent-dream-sessions sesn_01,sesn_02 \
    --agent-dream-instructions "Focus on coding-style preferences"
python main.py --agent-dream-get drm_01AbCDefGhIjKlMnOpQrStUv
python main.py --agent-dream-list

# P1 -- Outcomes (public beta): define a rubric and let the agent iterate
# against an independent grader until it's satisfied, instead of a
# single plain task
python main.py --agent-managed-run "unused, ignored when --agent-outcome is set" \
    --agent-outcome "Build a DCF model for Costco in .xlsx" \
    --agent-outcome-rubric rubric.md --agent-outcome-max-iter 5

# P2 -- Webhooks (public beta): get notified of session/outcome/dream
# events instead of holding an SSE stream open
python main.py --agent-webhook-register https://example.com/hooks/agents \
    --agent-webhook-events session.status_idle,span.outcome_evaluation_end
```

## New in v1.19.0 — Managed Agents memory stores

One item closed from re-running `ROADMAP.md`'s gap-audit methodology
against platform.claude.com/docs (checked 2026-07-08); see
`IMPLEMENTATION_CHECKLIST.md` Form 9 and `docs/32_upgrade_v1.19.0.md`
for the full write-up.

```bash
# P1 -- create a persistent, workspace-scoped Managed Agents memory store
# once, then mount it into a hosted-agent session so its work survives
# past a single throwaway session (agent-memory-2026-07-22 beta)
python main.py --agent-memory-store-create --agent-memory-store project-x-notes

python main.py --agent-managed-run "Continue the refactor from last time" \
    --agent-memory-store project-x-notes
```

## New in v1.18.0 — Mid-conversation system messages, Cache diagnostics CLI wiring

Two items closed from re-running `ROADMAP.md`'s gap-audit methodology
against platform.claude.com/docs (checked 2026-07-08); see
`IMPLEMENTATION_CHECKLIST.md` Forms 7–8 and `docs/31_upgrade_v1.18.0.md`
for the full write-up.

```bash
# P1 -- update Claude's instructions partway through an already-cached
# conversation without invalidating the cached prefix (Opus 4.8 only)
python main.py --cache --cache-multi-turn "First question" "Follow-up question" \
    --cache-mid-system "From now on, answer in bullet points." \
    --cache-mid-system-after 0 --model claude-opus-4-8

# P2 -- Cache diagnostics (beta): report *why* a cache read missed
# (client-side support existed since ~v1.10.x; this flag was the only
# missing piece, so it was previously unreachable from the CLI)
python main.py --cache -p "..." --cache-diagnose
```

## New in v1.17.0 — Resilience wired into every direct-HTTP module

No new CLI flags — internal only. Every module that talks to the Claude
API via raw `urllib` (19 of them, not just the ones going through the
`anthropic` SDK client) now retries transient failures (429/5xx/network)
with exponential backoff and fails fast via a circuit breaker once a
downstream is clearly down. External behavior is unchanged — see
`CHANGELOG.md` for the full module list.

## New in v1.15.0 — Server-side fallback, context editing, Skills API, Admin API

Five items closed out from `ROADMAP.md`'s gap audit against
platform.claude.com/docs (checked 2026-07-04); see `CHECKLIST.md` for the
itemized task list and `docs/29_upgrade_v1.15.0.md` for the full write-up.

```bash
# P0 -- let the platform retry a refused Fable 5 call itself, in one round
# trip, instead of the existing client-side manual retry (--fallback-model)
python main.py --fable5 "..." --fable5-fallback-chain claude-opus-4-8,claude-sonnet-5

# P1 -- opt-in context editing for long --code-agent runs: auto-clears
# stale tool results once the conversation crosses a token trigger,
# complementary to (not a replacement for) existing Compaction support
python main.py --code-agent -p "..." --agent-context-editing

# P1 -- platform Agent Skills (skill_id-based), distinct from Claude Code's
# local .claude/skills/*/SKILL.md loader; info-only for now
python main.py --skills-list
python main.py --skills-info xlsx

# P2 -- Usage/Cost reporting and API key management (requires an Admin API
# key, sk-ant-admin..., not a regular key)
python main.py --usage-report --usage-report-group-by model
python main.py --cost-report --cost-report-start 2026-06-01 --cost-report-end 2026-07-01
python main.py --admin-list-keys
python main.py --admin-revoke-key key_abc123
python main.py --admin-create-key "new-key"   # explains why this isn't supported, doesn't fake it
```

Also new this release: `--excel-native` / `--pptx-native` route
`--excel` / `--pptx` through the platform's pre-built Skills instead of
the hand-rolled pandas/openpyxl / python-pptx exec loop, which stays as
the fallback when Skills access isn't available.

## New in v1.16.0 — Compliance API

`claude_compliance_api.py` closes the gap the previous section left
open — the roadmap's "revisit only if there's an actual concrete
request" condition was met. Wraps the org-wide Activity Feed plus (with
a Compliance Access Key) read/hard-delete access to chats, files, and
projects, plus directory endpoints:

```bash
python main.py --compliance-activities --compliance-api-key sk-ant-api01-...
python main.py --compliance-chats-list --compliance-user-ids user_abc,user_def
python main.py --compliance-chat-delete chat_123                 # dry-run preview
python main.py --compliance-chat-delete chat_123 --compliance-yes  # actually deletes
```

Every destructive flag (`--compliance-chat-delete`,
`--compliance-file-delete`, `--compliance-project-delete`) is a dry-run
preview unless `--compliance-yes` is also passed. See
`docs/30_upgrade_v1.16.0.md` for the full key-model and reliability
write-up.

## New in v1.14.0 — Interactive chat + conversational Excel assistant

`-i`/`--interactive` has existed as a bare CLI flag since v1.7.0 but was
never actually wired to anything — passing it silently fell through to
`parser.print_help()`. It's now a real persistent, multi-turn chat REPL.

```bash
# Chat interface — persistent multi-turn conversation
python main.py -i
python main.py -i --interactive-system "You are a terse Rust reviewer."
```

Inside the session: `/help`, `/reset`, `/system TEXT`, `/model NAME`,
`/save FILE`, `/history`, `/exit`.

Also new: `--excel`, a conversational spreadsheet assistant in the spirit
of Anthropic's own Claude-in-Excel experience — no Office add-in, just a
terminal chat that keeps a real `.xlsx` file in sync with the conversation.

```bash
# Build financial models, analyze data, and create tables and charts
# with Claude directly in a real .xlsx file
python main.py --excel messy_sales_data.csv --excel-output clean_model.xlsx

# Transform complex data tasks or messy data clean-ups into simple
# conversations — e.g. inside the session:
#   you› drop empty rows, standardize the date column, and add a
#         month-over-month growth % column
#   you› build a simple 3-line revenue/cost/profit model from this data
#   you› add a bar chart of revenue by region
```

Requires `pandas` and `openpyxl` (see `requirements.txt`) — every other
flag in this CLI is unaffected if they aren't installed; only `--excel`
needs them, and it errors out clearly if they're missing.

This is a CLI hitting the Anthropic API directly with your own API key,
not a Claude Pro/Max/Team/Enterprise consumer plan — there's no seat or
plan gate here, `--excel` and `-i` work with any valid `ANTHROPIC_API_KEY`.

See `docs/28_upgrade_v1.14.0.md` for full detail.

## New in v1.13.0 — Enterprise hardening

Production-readiness pass: structured JSON logging with automatic secret
redaction, retry-with-backoff + a circuit breaker around the core API
call, path/URL/input security controls, a `--health-check` flag for
container orchestrators, and a full test suite + CI pipeline + Docker
packaging. No existing CLI flags were removed or renamed. See
`docs/27_upgrade_v1.13.0.md` for the full detail and `ARCHITECTURE.md` /
`SECURITY.md` / `docs/deployment.md` / `docs/observability.md` for the
new reference docs.

```bash
# Health check (fast — no network call; add --health-check-deep for one)
python main.py --health-check

# Structured JSON logs to stderr (auto-on when stdout isn't a TTY)
ZCODER_LOG_FORMAT=json python main.py -p "..."

# Run the test suite / lint / security scan
pip install -r requirements-dev.txt
make check          # or: pytest && ruff check . && bandit -r . -x ./tests

# Container
docker build -t zcoder .
docker run --rm -e ANTHROPIC_API_KEY=sk-ant-... zcoder -p "hello"
```

## New in v1.12.0 — standalone packaging (merged from ai-coder-cli-v2)

Packaging-only release, no API/functional changes from v1.11.1. Added a
working standalone-executable build story this project never had:
`./setup.sh` (or `.bat`) for a venv + `.env` from source, `./build.sh` (or
`.bat`) to produce a single dependency-free `dist/ai-coder` binary via
PyInstaller, plus `LICENSE` (MIT) and `.env.example`. See
`docs/25_merge_v2_into_release.md` for exactly what was merged in from the
`ai-coder-cli-v2` lineage and — just as importantly — what wasn't and why
(mostly: v1 already had a more complete, already-wired implementation of
the same ground under the same file/class names). `QUICKSTART.md` has the
fastest path to a first run either way.

## New in v1.11.1 — MCP tunnels, retired tool-version tracking, refusal
## billing in the cost optimizer, Sonnet-5 sampling-parameter fix

A follow-up pass on top of v1.11.0 below: closed the remaining item from
the v1.10.5 gap audit (MCP tunnels), added the tool-version equivalent of
`claude_models.py`'s retired-model registry, brought `claude_cost_optimizer.py`
in line with `claude_metrics.py`'s refusal-billing fix, and fixed a
functional bug found while doing that work — six modules hardcoded a
`temperature=` value that 400s on Claude Sonnet 5 (the default model).

```bash
# MCP tunnels — expose a local-only MCP server via a public URL
python main.py --code-agent-mcp-tunnel 8787

# See which server-tool versions have a newer replacement available
python main.py --list-server-tools
```

See `docs/24_upgrade_v1.11.0.md` for the full v1.11.0 + v1.11.1 changelog,
including the full list of files touched by the sampling-parameter fix and
what's still open.

# AI Model Coder CLI — v1.11.0 (superseded by v1.11.1 above)
All Claude API Features + Claude Code / Agent SDK + Cowork + Plugins

## New in v1.11.0 — Advisor tool, real Programmatic Tool Calling, Tool Use
## Examples, task budgets, compaction, embeddings, fine-grained tool streaming

Prompted by a follow-up audit of the v1.10.5 gap list plus a fresh check
against platform.claude.com/docs (2026-07-02). Every item below was either
completely absent from the codebase, or present only as a docstring bullet
with no actual implementation behind it.

```bash
# Advisor tool — pair a fast executor with a stronger advisor model
python main.py --advisor "Refactor auth.py to use JWT, then write tests" \
                --advisor-model claude-opus-4-8

# Programmatic Tool Calling — mark your --tool-file tools callable from
# code_execution instead of one model round-trip per call
python main.py --server-tool code_execution --file my_tools.json --ptc \
                -p "Query sales for West/East/Central and compare revenue"

# Tool Use Examples — see claude_tools.with_input_examples() to attach
# worked examples to a tool definition (parameter-accuracy improvement on
# complex schemas, per Anthropic's own reported 72%->90% internal number)

# Task budgets — advisory token countdown for a whole agentic loop
python main.py --server-tool code_execution --task-budget 200000 \
                -p "Migrate this repo from unittest to pytest"

# Compaction — server-side conversation summarization for long sessions
python main.py --server-tool web_search,code_execution --compaction \
                -p "Research and summarize five competing products"

# Embeddings (Voyage AI — Anthropic doesn't host its own embedding model)
export VOYAGE_API_KEY=...
python main.py --embed "some text to embed"
python main.py --embed-similarity "cat" "kitten"

# Fine-grained tool streaming — tool input arrives as Claude generates it
python main.py --stream-tools "Write a long poem to poem.txt" --file tools.json
```

`claude_tools.py` bumped its server-tool version strings (`web_search`
20250305→20260209, `code_execution` 20250522→20260120 — the documented
minimum for programmatic tool calling), split `computer_use` by model
generation instead of one fixed version, and added real implementations
for `allowed_callers` (PTC), `input_examples` (Tool Use Examples),
`task_budget`, and the `compact_20260112` context-management edit —
previously only the first of these was even mentioned, and only as a
docstring bullet with no code behind it.

New modules: **`claude_advisor.py`** (the advisor tool — didn't exist at
all before this pass) and **`claude_embeddings.py`** (thin Voyage AI
wrapper + an `EmbeddingIndex` helper, since Anthropic's own docs point to
Voyage rather than a first-party embedding endpoint).

`claude_fable5.py`'s refusal handling read `data["refusal"]["classifier"]`,
a field this project invented rather than one the API documents. Fixed to
read the documented `stop_details: {category, explanation}` shape, with
`classifier` kept as a backward-compatible alias so existing callers don't
break. `claude_metrics.py`'s `record()` now takes `stop_reason` and skips
billing for refusal-only calls, matching the documented "not billed" rule
for empty refusals.

See `docs/24_upgrade_v1.11.0.md` for the full list of what changed and why,
and what's still open after this pass.

## Quick Start
```bash
unzip ai-coder-cli-v1.9.0.zip && cd ai-coder-cli
export ANTHROPIC_API_KEY=sk-ant-...
python main.py -p "Write a Python web scraper"
```

## New in v1.8.0 — Claude Code / Agent SDK

```bash
# Agent loop with full tool execution
python main.py --code-agent -p "Refactor auth.py to use JWT"

# Resume a session
python main.py --code-agent-session <id> -p "Now add tests"

# Tool presets + permission modes
python main.py --code-agent -p "..." --code-agent-tools readonly --code-agent-permission planMode

# Hooks (PreToolUse, PostToolUse, Stop, SubagentStart, PermissionRequest, ...)
python main.py --code-agent -p "..." --code-agent-hooks hooks.json

# MCP servers (auto-loads .mcp.json)
python main.py --code-agent -p "..." --code-agent-mcp https://my-server.com/mcp

# Subagents
python main.py --code-agent-subagent "Find all security issues in src/"

# Slash commands
python main.py --code-agent-slash help
python main.py --code-agent-slash doctor

# Todo lists
python main.py --code-agent-todo "Build a REST API with auth, tests, docs"

# Cost tracking
python main.py --code-agent-cost
python main.py --code-agent-list-sessions
python main.py --code-agent-list-tools
```

## New in v1.9.0 — Plugins, Output Styles, Sandbox, Headless, Settings

```bash
# Marketplaces — register a source of plugins (local dir, .zip, or URL)
python main.py --plugin-marketplace-add ./my-marketplace --plugin-marketplace-name acme
python main.py --plugin-marketplace-list
python main.py --plugin-marketplace-remove acme

# Install / manage plugins
python main.py --plugin-install code-reviewer@acme
python main.py --plugin-dir ./local-plugin        # install directly, no marketplace needed
python main.py --plugin-list
python main.py --plugin-info code-reviewer
python main.py --plugin-enable code-reviewer
python main.py --plugin-disable code-reviewer
python main.py --plugin-uninstall code-reviewer
python main.py --plugin-validate ./my-plugin       # lint a plugin before installing

# Installed plugins automatically contribute their bundled skills, commands,
# agents, output-styles, hooks, and MCP servers to --code-agent — no extra flags needed.
python main.py --code-agent -p "lint this repo"    # can invoke a plugin's /lint command
python main.py --code-agent-slash plugin           # list installed plugins
python main.py --code-agent-slash agents           # plugin agents show as plugin:name

# Output styles — change how the agent narrates/formats without changing its tools
python main.py --list-output-styles
python main.py --code-agent -p "Refactor db.py" --code-agent-output-style explanatory
python main.py --code-agent -p "Fix the bug"     --code-agent-output-style concise

# Sandboxed Bash — filesystem + network isolation for tool-call execution
python main.py --code-agent -p "Run the test suite" --code-agent-sandbox
python main.py --code-agent -p "Install deps and test" --code-agent-sandbox --code-agent-sandbox-allow-net
python main.py --code-agent -p "..." --code-agent-sandbox --code-agent-sandbox-roots ../shared-lib

# Headless / print mode — one-shot, non-interactive, plain-text output for scripting
python main.py --code-agent-headless -p "Summarize open TODOs in this repo" -o todos.md

# Settings — layered user/project/local settings.json (same precedence as Claude Code)
python main.py --settings-show
python main.py --status-line
```

## New in v1.10.5 — Native memory tool, context editing, tool search tool

```bash
# Agent loop backed by Claude's native memory tool (memory_20250818, GA)
python main.py --memory-agent "Remember that I prefer TypeScript and dark mode" \
                --memory-dir ./my-project-memory

# Auto-clear stale tool results on a long server-tool call
python main.py --server-tool web_search,code_execution -p "..." --context-management

# See every server tool, including which ones still need a beta header
python main.py --list-server-tools
```

`claude_tools.py` was missing three capabilities that ship on the current
API: the native memory tool, context editing, and the tool search tool.
`claude_memory.py` already existed in this project, but it's a custom
reimplementation — not Anthropic's `memory_20250818` server tool, which
is a different thing (server-declared, client-executed, GA since
2025-09-29, no beta header required).

- **`MemoryToolHandler`** — client-side handler for `memory_20250818`:
  view/create/str_replace/insert/delete/rename against a local directory,
  with every path resolved and checked to stay inside that directory
  before touching disk (path-traversal protection, per Anthropic's
  documented requirement for memory tool implementations).
- **`ToolCoder.run_agent_with_memory()`** / **`--memory-agent PROMPT`**
  (+ `--memory-dir DIR`, default `~/.ai-coder/memory`) — a full agent
  loop that dispatches `memory` tool_use blocks to `MemoryToolHandler`
  automatically, so memory persists across calls without hand-rolling
  the command dispatch yourself.
- **`build_context_management()`** — builds the `context_management`
  payload (`clear_tool_uses_20250919`, optionally `clear_thinking_20251015`)
  that auto-clears stale tool results / old thinking blocks once a long
  agent run crosses a token threshold, keeping the most recent N tool
  uses intact. New `--context-management` flag wires it into
  `--server-tool` calls; `--memory-agent` uses it by default.
- **`tool_search` server tool** (`tool_search_tool_20251019`) added to
  `SERVER_TOOLS` for on-demand tool discovery on large tool libraries —
  descriptor and beta header only; marking your own tool definitions
  with `defer_loading: true` is still on the caller.
- **Fixed a beta-header bug found while wiring this in**: the old code
  applied a single `computer-use-2025-01-24` check to
  bash/text_editor/computer_use/*and* code_execution. code_execution
  actually needs its own `code-execution-2025-05-22` beta line — that's
  now a proper per-tool map (`SERVER_TOOL_BETAS`) instead of one
  membership test.

## New in v1.10.4 — Retired-model registry, deprecation scanner, effort-level info

```bash
# Check whether a model ID you have pinned somewhere is actually retired
python main.py --model-info claude-sonnet-4-20250514

# Scan a file or an entire project for retired model ID strings
python main.py --check-deprecated ./src
python main.py --check-deprecated app.py
```

`claude_models.py` now separates two different kinds of "old model" instead
of folding them together:

- **`MODEL_CATALOG`'s `legacy` tier** — superseded but still callable
  (Opus 4.5/4.6/4.7, Sonnet 4.5/4.6). Calling these works; you're just not
  on the newest version.
- **New `RETIRED_MODELS`** — IDs that now return API errors: the original
  Claude 4.0 releases (`claude-opus-4-20250514` / `claude-sonnet-4-20250514`
  and their dateless `-4-0` aliases, retired 2026-06-15) and Claude Haiku 3
  (`claude-haiku-3-20240307`, retired 2026-02-19). Each entry carries a
  recommended replacement model ID.

`--model-info ID` now checks `RETIRED_MODELS` first and prints a clear
migration notice — with the replacement ID — before attempting the live
API call, instead of surfacing a bare 404/400 for an ID that will never
succeed again.

New `--check-deprecated PATH` command greps a file or walks a directory
for any retired model ID string and reports every hit with file:line
locations and its replacement, following Anthropic's own documented
migration advice to check the whole codebase (API calls, env files, CI
configs) rather than just the primary call site.

`cmd_model_info()`'s live-API path also now prints the response's
`effort` capability block (supported levels and default) when the API
returns one, alongside the vision/thinking/structured-outputs fields it
already showed.

## New in v1.10.3 — Full model catalog, verified pricing, legacy tier

`claude_models.py` now ships a `MODEL_CATALOG` covering every current and
still-callable legacy model (Mythos 5, Fable 5, Opus 4.8, Sonnet 5, Haiku
4.5, plus legacy Opus 4.7/4.6/4.5 and Sonnet 4.6/4.5), each with context
window, max output, pricing, and thinking mode (adaptive vs. extended vs.
none) — sourced from Anthropic's live docs, not carried-over guesses.

Pricing was also corrected in three places where it had drifted from
official numbers (Opus was showing $15/$75 instead of the real $5/$25;
Haiku was showing $0.80/$4 instead of $1/$5): `claude_cost_optimizer.py`,
`claude_metrics.py`, and `claude_tokens.py` all now use the verified
figures, and `claude_cost_optimizer.py` separately tracks Sonnet 5's
$2/$10 introductory pricing (through 2026-08-31) via
`SONNET5_INTRO_PRICE` / `estimate_cost(..., use_intro_pricing=True)`
rather than conflating it with the standing $3/$15 rate.

```bash
python main.py --list-models                # current + Mythos-class tiers
python main.py --list-models --list-models-legacy   # + superseded models
python main.py --model-info claude-opus-4-8  # live capabilities when online,
                                               # catalog fallback when offline
```

`--model-info` now also surfaces the live API's `capabilities` object
(vision, adaptive/extended thinking, structured outputs) when reachable,
instead of only context window and creation date.

## New in v1.10.2 — Model lineup refresh (correct/current model IDs)

Earlier versions of this CLI had accumulated several speculative or
outdated model IDs (`claude-sonnet-4-6`, `claude-opus-4-6`/`4-7`,
`claude-haiku-4-5` without a date suffix) scattered across pricing
tables and defaults, some of which never corresponded to real,
callable Anthropic model strings. This release normalizes every
module — `claude_models.py`, `claude_cost_optimizer.py`,
`claude_metrics.py`, `claude_tokens.py`, and the `--model` default in
`main.py` — to the current lineup:

| Model ID | Display name | Tier |
|---|---|---|
| `claude-opus-4-8` | Claude Opus 4.8 | Opus |
| `claude-sonnet-5` | Claude Sonnet 5 | Sonnet |
| `claude-haiku-4-5-20251001` | Claude Haiku 4.5 | Haiku |
| `claude-fable-5` | Claude Fable 5 | Mythos-class (public) |
| `claude-mythos-5` | Claude Mythos 5 | Mythos-class (Project Glasswing only) |

Also folded in: Fable 5 / Mythos 5 access was briefly suspended
2026-06-12 → 2026-06-30 for US export-control compliance and restored
2026-07-01 — see `--fable5-info` / `--mythos5-info` and
https://www.anthropic.com/news/fable-mythos-access. Note above the
Mythos-tier chat model (not exposed in this API-driven CLI) sits one
rung above Opus; a not-yet-public `Claude Mythos Preview` also exists
under Project Glasswing — see https://www.anthropic.com/glasswing.

```bash
python main.py --list-models       # now shows the deduped, current lineup
python main.py --fable5-info       # pricing/retention, now with the access-restoration note
python main.py --mythos5-info      # same, for the Glasswing-gated sibling
```

## New in v1.10.1 — Claude Mythos 5 companion module

```bash
# What's known about Mythos 5 (limited-availability access, Project Glasswing)
python main.py --mythos5-info

# Call Mythos 5 directly — only works if your account has approved access
python main.py --mythos5 "your prompt"
```

`claude_mythos5.py` is deliberately thinner than `claude_fable5.py`: Mythos 5
is documented as the same underlying model as Fable 5 *without* safety
classifiers, so there's no refusal/fallback mechanic to implement. It does
add one thing Fable 5's module doesn't need: a pointed error
(`MythosAccessError`) when a call gets an HTTP 403/404, since that's the
expected outcome for most accounts that haven't been granted Project
Glasswing access — you get a clear explanation instead of a generic
traceback. Same confidence caveats as Fable 5 apply, stated even more
directly in the module's docstring since access-gating adds another layer
of things that could be wrong or could change.

## New in v1.10.0 — Memory, Sessions, zai-live, Deep Research, RAG, Evals, Git, Cost Optimizer, Observability, Workflows, Hooks, Permissions, Plan Mode

```bash
# Persistent memory across every future session
python main.py --memory-add "Team prefers trunk-based development" --memory-type preference
python main.py --memory-recall "development workflow"
python main.py --memory-stats

# Resumable sessions with named checkpoints and rewind
python main.py --sessions-list
python main.py --checkpoint-list <session-id>
python main.py --away-summary <session-id>

# Real-time streaming session with ambient background context
python main.py --live

# Multi-step research: plan sub-questions, gather, synthesize a cited report
python main.py --research "How do CRDTs resolve write conflicts?" --research-depth 5

# Local RAG over a folder of files, no vector DB required
python main.py --rag-index docs --rag-folder ./documentation
python main.py --rag-query "how does auth work" --rag-index-name docs

# AI-graded prompt/model evaluation suites
python main.py --eval-scaffold suite.json
python main.py --eval-run suite.json
python main.py --eval-compare claude-sonnet-4-6 claude-haiku-4-5-20251001

# AI-powered git: commit messages, PR descriptions, changelogs, diff review
python main.py --git-commit --git-commit-write
python main.py --git-pr main feature-branch
python main.py --git-changelog v1.9.0

# Cost-aware model routing — cheap prompts auto-route to Haiku
python main.py --optimized "What's 2+2?"
python main.py --cost-summary

# Request logging, latency histograms, AI error-trend analysis
python main.py --obs-latency
python main.py --obs-errors

# Declarative YAML/JSON multi-step pipelines with variable interpolation
python main.py --workflow-scaffold pipeline.json
python main.py --workflow-run pipeline.json --workflow-input "auth module"

# Lifecycle hooks (pre/post tool-use, session start/end)
python main.py --hooks-add pre_tool_use "echo blocked" --hook-tool-match delete_file
python main.py --hooks-list

# Fine-grained allow/deny/ask permission rules per tool name
python main.py --perms-list
python main.py --perms-add "run_shell" ask

# Propose a numbered plan, review it, then approve execution
python main.py --plan "Add rate limiting to the API" --plan-execute
```

See `docs/19_upgrade_v1.10.0.md` for what was actually tested (not just
compiled) and the known limitations of each new module.

## New in v1.9.1 — Claude Fable 5 / Mythos 5

```bash
# What's known about Fable 5 / Mythos 5 (pricing, context, refusal handling)
python main.py --fable5-info

# Call Fable 5 directly; falls back to --fallback-model automatically on refusal
python main.py --fable5 "Refactor this 50k-line module for clarity"

# Disable auto-fallback — just report the refusal and which classifier triggered it
python main.py --fable5 "..." --fable5-no-fallback

# Use a different fallback target than the default (claude-opus-4-6)
python main.py --fable5 "..." --fallback-model claude-sonnet-4-6
```

> **Confidence note:** Fable 5 / Mythos 5 details come from recent web search
> results (~June 2026), not from this CLI's own bundled product knowledge —
> `claude_fable5.py`'s docstring carries the same caveat. Verify pricing and
> availability at platform.claude.com/docs before relying on them for
> anything billing-sensitive. `claude-mythos-5` requires Project Glasswing
> approval; most accounts should use `claude-fable-5`.

## Cowork (12 task types)
```bash
python main.py --cowork research   --cowork-prompt "Latest Rust async advances"
python main.py --cowork review     --cowork-prompt "Review" --cowork-files app.py
python main.py --cowork architect  --cowork-prompt "Microservices for e-commerce"
python main.py --cowork debug      --cowork-prompt "Memory leak in FastAPI"
python main.py --cowork write      --cowork-prompt "Blog: Why Python wins at AI" -o post.md
python main.py --cowork-list
```

## All Claude API Features

```bash
# Extended Thinking
python main.py --thinking --effort max -p "Hard problem"
python main.py --adaptive -p "Design a caching strategy"

# Streaming
python main.py --stream -p "Explain monads"

# Web Search
python main.py --web-search -p "Python 3.14 features"

# Vision
python main.py --vision ui.png --vision-code   # generate code from screenshot
python main.py --vision-pdf report.pdf -p "Key metrics?"

# Batch API (50% cost discount)
python main.py --batch-submit prompts.jsonl
python main.py --batch-results <id>

# Prompt Caching
python main.py --cache -p "Question" --cache-docs large_doc.md
python main.py --cache-warm --cache-docs docs/
python main.py --cache -p "Question" --cache-diagnose            # v1.18.0: report why a cache read missed
python main.py --cache --cache-multi-turn "Turn 1" "Turn 2" \
    --cache-mid-system "Answer in bullet points from now on."     # v1.18.0: Opus 4.8 only

# Tool Use (agentic loop)
python main.py --tool-agent -p "Read all .py files and write a summary"

# Structured Outputs
python main.py --structured --schema product.json -p "Parse this listing"
python main.py --structured-analyse myapp.py

# Files API
python main.py --file-upload report.pdf
python main.py --file-ask <id> -p "What are the revenue figures?"

# Code Execution (Anthropic sandbox)
python main.py --code-exec -p "Plot sin(x) and return the chart"

# Token Counting
python main.py --count-tokens -f large_file.py --count-budget 100000

# Citations / RAG
python main.py --cite doc1.md doc2.md -p "What does the spec say?"
python main.py --rag ./docs/ -p "How do I configure the DB?"

# Computer Use
python main.py --computer-use "Open browser, go to github.com"

# Models API
python main.py --list-models
```

## Modules (46 total, 11,050 lines)

| Module | Purpose |
|--------|---------|
| `claude_skills_api.py` (NEW, v1.15.0) | Platform Agent Skills (`skill_id`-based); base client + `--excel-native`/`--pptx-native` primitives |
| `claude_admin_api.py` (NEW, v1.15.0) | Admin API: Usage/Cost reporting, API key list/revoke (requires an Admin API key) |
| `claude_mythos5.py` (NEW) | Claude Mythos 5: limited-access companion to claude_fable5.py, pointed access-gate error handling |
| `claude_memory.py` (NEW) | Persistent cross-session memory: facts, preferences, events, tasks, retention policy |
| `claude_sessions.py` (NEW) | Resumable sessions, named checkpoints/rewind, away-summary (repo activity while absent) |
| `claude_live.py` (NEW) | zai-live: real-time streaming REPL with ambient background context |
| `claude_research.py` (NEW) | Deep Research: plan sub-questions → gather (URL-grounded) → synthesize a cited report |
| `claude_rag.py` (NEW) | Local retrieval-augmented generation over a folder, keyword/BM25-style scoring, no vector DB |
| `claude_eval.py` (NEW) | LLM-judged eval suites; single-run and head-to-head model comparison |
| `claude_git.py` (NEW) | AI-powered commit messages, PR descriptions, changelogs, diff review, blame explanations |
| `claude_cost_optimizer.py` (NEW) | Complexity-based model routing (Haiku/Sonnet/Opus) + cumulative spend tracking |
| `claude_observability.py` (NEW) | Structured request logging, latency histograms, AI-powered error-trend analysis |
| `claude_workflow.py` (NEW) | Declarative YAML/JSON multi-step pipelines with `{{variable}}` interpolation and dependencies |
| `claude_hooks_perms_plan.py` (NEW) | Lifecycle hooks, fine-grained tool permissions (allow/deny/ask), Plan Mode (propose→approve→execute) |

| Module | Purpose |
|--------|---------|
| `claude_code.py` (1386L) | Agent SDK: sessions, tools, hooks, MCP, subagents, skills, slash cmds, todos, memory |
| `claude_plugins.py` (NEW) | Plugin system: marketplaces, install/uninstall, skills/commands/agents/hooks/MCP loading |
| `claude_fable5.py` (219L) | Claude Fable 5 / Mythos 5: model info, refusal detection, automatic fallback |
| `claude_output_styles.py` (NEW) | Output styles: built-in + custom/plugin .md styles |
| `claude_settings.py` (NEW) | Layered settings.json precedence, statusLine |
| `claude_sandbox.py` (NEW) | Sandboxed Bash: filesystem + network isolation |
| `claude_cache.py` (297L) | Prompt caching, pre-warming, cache stats |
| `cowork.py` (448L) | 12 Cowork task types with specialist system prompts |
| `claude_tools.py` (375L) | Tool use, parallel tools, agentic runner, server tools |
| `claude_agents_sdk.py` (332L) | Managed agents, orchestration, subagents |
| `claude_models.py` (286L) | Models API, Computer Use, Adaptive/Interleaved Thinking |
| `claude_files.py` (272L) | Files API upload/list/ask/download/delete |
| `claude_batch.py` (258L) | Batch API, 50% cost discount |
| `claude_structured.py` (210L) | Structured outputs, JSON schema, code analysis |
| `claude_code_exec.py` (210L) | Code Execution tool, live debugging |
| `claude_citations.py` (202L) | Document citations, search result citations, RAG |
| `claude_thinking.py` (189L) | Extended thinking, effort levels, streaming thinking |
| `claude_vision.py` (182L) | Images, PDFs, OCR, code from screenshot |
| `claude_search.py` (136L) | Web search, web fetch, citations |
| `claude_stream.py` (117L) | Real-time streaming |
| `claude_tokens.py` (109L) | Token counting, budget checking |
| `projects.py` (469L) | Feature Projects |
| `artifacts.py` (435L) | Versioned Artifacts |
| `main.py` (521L) | CLI entry point, all flags |

## Storage
```
~/.ai-coder/code_sessions/   # Agent sessions
~/.ai-coder/projects/        # Feature projects
~/.ai-coder/artifacts/       # Versioned artifacts
.claude/CLAUDE.md            # Project memory (auto-loaded)
~/.claude/CLAUDE.md          # User memory (always loaded)
.mcp.json                    # MCP servers (auto-loaded)
.claude/agents/*.md          # Subagent definitions
.claude/skills/*/SKILL.md   # Agent skills
.claude/commands/*.md        # Slash commands
.claude/output-styles/*.md   # Project-level custom output styles
~/.claude/output-styles/*.md # User-level custom output styles
.claude/settings.json        # Project settings
.claude/settings.local.json  # Local overrides (highest precedence, gitignore this)
~/.claude/settings.json      # User settings (lowest precedence)
~/.claude/plugins/marketplaces/   # Registered plugin marketplaces
~/.claude/plugins/installed/      # Installed plugins
~/.claude/plugins/registry.json   # Plugin/marketplace index
```