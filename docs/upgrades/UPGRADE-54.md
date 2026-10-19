# Upgrade-54 — Claude Code Product-Parity Audit (Update Plan)

## Goal

Produce the full-scale feature-parity audit of ZCoder against the
`anthropics/claude-code` product changelog, structured as a prioritized
update plan so ZCoder can be evolved to cover every feature area the
Claude Code CLI exposes. This cycle is documentation-only: it records the
audit, the scorecard, and twelve workstreams (W1–W12); it changes no code
semantics.

## Method and sources

- `anthropics/claude-code` `CHANGELOG.md` fetched from
  `raw.githubusercontent.com` on 2026-10-19: 423 release entries,
  9,197 lines. The most recent window (2.1.300–2.1.303) was read in full;
  the remaining history was indexed by theme-frequency grep
  (MCP 566 lines, plugins 575, hooks 390, background 560, permissions 471,
  subagents 269, skills 279, compaction 171, worktrees 153, sandbox 144,
  VS Code 93, Slack 116, desktop 124, remote control 215, cloud sessions 186).
- ZCoder side verified at source level: `src/zcoder/claude/` (65 modules,
  21,101 lines) mapped feature-family by feature-family, plus
  `services/`, `enterprise/`, `interfaces/`, README, and this ROADMAP's
  Part 1 coverage tables.

## Evidence-tier caveat

Per the repository's evidence-tier discipline, this audit sits at
Tier 1–2 (source + documentation). Claude Code's side consists of vendor
changelog claims, not runtime tests; ZCoder's side was confirmed by
source-level grep and coverage tables, not by executing every surface.
Verdicts below must be re-verified at Tier 3+ before any "parity reached"
claim ships through the release gate.

## Scorecard (15 domains)

Legend: ✅ parity · 🟡 partial · ❌ absent · ⭐ ZCoder differentiator.

| # | Domain | Claude Code evidence | Verdict | Note |
|---|---|---|---|---|
| 1 | Agent loop & core toolset | whole changelog | 🟡 | core tools covered; gaps: PowerShell tool, Notebook, AskUserQuestion, TodoList UX |
| 2 | Permission modes & plan mode | permissions 471, plan 43+7 | 🟡 | hooks/perms + policy engine present; plan-file approval card and auto-mode classifier missing |
| 3 | Context management | compaction 171 | 🟡 | compaction + context editing shipped v1.15; idle compaction and model-switch summarization missing |
| 4 | Sessions, rewind, checkpoints | multiple entries | 🟡 | resume/rewind/branch present; fork subagents, /export, /rename missing |
| 5 | Extensibility (skills/hooks/plugins/MCP/styles) | plugins 575, MCP 566, hooks 390, skills 279 | 🟡 | all families have modules; marketplace depth and the new "mods" UI extension system missing |
| 6 | Subagents & multi-agent | subagents 269, background 560 | 🟡 | subagents + router + multiagent config present; fork subagents and background-by-default missing |
| 7 | Providers & models | Bedrock 172, Vertex 122 | ⭐ | ZCoder is provider-neutral + local-first; Claude Code is Anthropic + gateways only |
| 8 | Enterprise & governance | managed settings 108 | ⭐ | ZCoder RBAC/SCIM/tenancy/audit/billing go far beyond; managed-settings precedence partial |
| 9 | Clients & IDE surfaces | VS Code 93, desktop 124, Slack 116, remote 215 | ❌ | largest gap; ZCoder has Chrome/Excel/PowerPoint analogs + Web Console only |
| 10 | Cloud/automation products | cloud sessions 186, routines 56, runners 47 | 🟡 | self-hosted analogs exist (workers/leases/campaigns/GitHub orchestrator); no hosted product |
| 11 | Local AI infrastructure | absent from Claude Code | ⭐⭐ | Ollama/llama.cpp/vLLM adapters, hardware profiler, local RAG, zero-cost policy |
| 12 | Sandbox & security | sandbox 144 | 🟡 | OS-level (bwrap) vs ZCoder application-level containment (SEC-001..010) — different mechanics |
| 13 | Observability | OpenTelemetry 45 | 🟡 | OTel/Prometheus present; GenAI semantic conventions and `tool_decision` events missing |
| 14 | Release & quality engineering | absent from Claude Code | ⭐⭐ | release gates, evidence tiers, SBOM/attestation, reproducibility |
| 15 | Windows & terminal ergonomics | PowerShell 63, vim 38, keybinds 43 | 🟡 | Windows binary shipped; PowerShell tool and terminal-protocol polish missing |

## Workstreams (update plan)

Each workstream names the Claude Code features it closes and the ZCoder
files it would touch. Bounded, one-PR-per-slice per the house protocol.

### W1 — Context & compaction family (P0)

Idle compaction (configurable), auto-summarization when switching to a
smaller-context model, `/context` budget visualization, microcompaction.
Targets: `claude/capabilities/code.py`, `claude/tools/registry.py`,
`orchestration/interactive.py`, `interfaces/`.

### W2 — Permission modes & plan-mode UX (P0)

Plan-file artifact with an approval card, session-scoped permission rules
(allow/deny/ask), self-hosted auto-mode classifier (must offer a
local-model route to stay zero-cost-compatible). Targets:
`claude/enterprise/hooks_perms.py`, `services/agent_runtime.py`.

### W3 — Background execution & task view (P0)

Interactive background shells, `/tasks` view, queued prompts sent
mid-turn, agents view. Distinct from the existing server-side durable
jobs/workers/outbox plane, which stays as is. Targets: `interfaces/`,
`services/agent_runtime.py`, `worker/`.

### W4 — Toolset robustness & missing tools (P0 robustness / P2 breadth)

Read-tool hardening (refuse image sources over 128 MB, binary sniffing for
`.xlsm`/`.parquet`/`.epub`/`.heic`, pipe/device guards), PowerShell tool
for Windows-native sessions, Notebook tool depth, AskUserQuestion and
TodoList as first-class tools. WebSearch must keep a zero-cost route under
`ZERO_COST_ONLY`. Targets: `claude/tools/registry.py`,
`claude/capabilities/{code,search}.py`.

### W5 — Plugins & marketplace (P1)

Git-based marketplaces, plugin commands/agents/bin discovery, built-in
plugins, `--plugin-dir` semantics, self-hosted registry (no paid
dependency). Decision required on mirroring the new "mods" UI-extension
system (2.1.30x, unstable spec) — observe first. Targets:
`claude/tools/plugins.py`, `services/skills.py`.

### W6 — MCP conformance depth (P1)

`claude mcp serve` equivalent, OAuth reconnection, protocol
2026-07-28 negotiation coverage (`resultType`, `ttlMs`, `cacheScope`),
`deniedMcpServers`-style policy, conformance tests against servers that
negotiate the newer protocol version. Targets: `claude/tools/mcp.py`,
`enterprise/local_ai_stack.py`.

### W7 — Subagent semantics (P1)

Fork subagents (`subagent_type: "fork"`), background-by-default behavior
for the primary app's subagents, agents view with breadcrumb, subagent
pane disconnect states. Targets: `claude/orchestration/{agents_sdk,router,workflow}.py`,
`services/agent_runtime.py`.

### W8 — Observability: GenAI semantic conventions (P1)

Adopt `gen_ai.*` span attributes, `tool_decision` events with classifier
verdict/category, and `cache_creation_5m_tokens`/`cache_creation_1h_tokens`
splitting. Targets: `claude/observability.py`, `claude/enterprise/metrics.py`.

### W9 — Terminal ergonomics (P1)

Deeper vim mode, keybindings, status-line customization, theme polish,
OSC 8 hyperlinks, screen-reader mode, fullscreen transcript, upstream
terminal-setup equivalents (iTerm2/Ghostty/Warp/Kitty/tmux).
Targets: `interfaces/` (Textual TUI), `claude/capabilities/code.py`.

### W10 — Client surfaces as self-hosted analogs (P2, selective)

Do not clone hosted products. Raise the Web Console into the central
surface: remote-control-style session view, artifacts viewer, routine
scheduler UI; optionally a VS Code extension speaking to the local API
server. Existing analogs (`integrations/chrome.py`, `excel.py`,
`powerpoint.py`, GitHub orchestrator, maintenance campaigns) already cover
part of this plane.

### W11 — Managed settings & policy precedence (P2)

User → project → organization settings precedence matching Claude Code's
managed-settings model, wired into the existing policy engine. Targets:
`claude/enterprise/settings.py`.

### W12 — Windows native (P2)

PowerShell tool parity, background PowerShell output handling, drive-type
write rules (exFAT/FAT32). Targets: `claude/tools/registry.py`, release
build scripts.

## Priorities

| Tier | Workstreams | Rationale |
|---|---|---|
| P0 | W1, W2, W3, W4 (robustness half) | daily-driver experience; W4 aligns with the house fail-closed posture |
| P1 | W5, W6, W7, W8, W9 | extensibility and interop carry the most changelog weight |
| P2 | W10, W11, W12 | product-surface decisions and platform-specific breadth |

Rough sizing: P0 ≈ 4–6 release cycles, P1 ≈ 6–8, P2 per product decision.
Each slice ships independently through the standard gate.

## Anti-goals

- No hosted-service clones (cloud sessions, Slack, desktop, mobile);
  self-hosted analogs via the Web Console instead.
- No silent paid-provider fallback in zero-cost mode; classifier and
  search features must expose local/free routes.
- No weakening of the release gate, evidence tiers, or tenant isolation
  while porting product features.
- Every parity claim must state its evidence tier; changelog-derived
  claims about Claude Code do not count as ZCoder evidence.

## Boundedness

This cycle adds one documentation file and one ROADMAP section. It changes
no source, no tests, no workflow gates, and no release semantics. The
workstreams above are proposals; each future slice passes through the
standard GPG → PR → dual-account approval → merge → release-gate protocol.
