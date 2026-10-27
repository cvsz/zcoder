# zcoder — next updates (as of 2026-10-25)

Sources: Claude Platform release notes (entries through 2026-10-22), Claude Help Center release notes (headlines only). Every item is a claim to re-verify live before coding (see _SHARED.md rule 2).
Base: zcoder-v1_60_0 (5.5-generation model catalog already added).

## Execution order

| # | Cycle | Priority | Size | Why now | Depends on |
|---|---|---|---|---|---|
| 1 | U61 Lineage reconciliation + version source of truth | P0 | L | Two diverging trees; everything else lands in one canonical tree | none |
| 2 | U62 Deprecation clock | P0 | S | Sonnet 4.5 retires on the API 2026-11-30 | U61 |
| 3 | U71 SDK majors + API version 2026-10-21 | P0 | L | New breaking SDK/API release (2026-10-21) | U61 |
| 4 | U63 Capability discovery + catalog completion (Mythos 5.1, Haiku 5.5 tier) | P0 | M | Replaces stale hand-kept capability sets | U61 |
| 5 | U64 Per-model request guards | P0 | M | 5.5/5.1 models return 400 on old request shapes | U63 |
| 6 | U66 Pricing and cost engine | P1 | M | Cache-read prices and refusal billing changed | U63 |
| 7 | U65 Messages API feature wave | P1 | L | Compaction, inline tools, per-message effort, cache diagnostics GA | U63, U64 |
| 8 | U76 Enterprise hardening (parallel after U61) | P1 | L | 891 lint findings, non-hermetic tests, CI gates | U61 |
| 9 | U67 Computer / browser use toolsets | P1 | M | `computer_20251124` rejected on 5.5 models | U64 |
| 10 | U68 Managed Agents wave | P1 | L | Dynamic workflows, `auto` permissions, budgets, web restrictions | U63 |
| 11 | U74 Multi-platform providers | P2 | L | Google Cloud Anthropic-managed (10-22), Bedrock, AWS, Foundry differences | U63, U64 |
| 12 | U69 Admin / org / compliance APIs | P2 | L | Admin out of beta, user profiles, org webhooks, Claude Tag API | U61 |
| 13 | U70 OpenTelemetry + workspace attribution | P2 | M | OTel export beta (10-14) | U61 |
| 14 | U72 Files / Skills GA cleanup | P2 | S | Beta headers dropped; skill delete now deletes all versions | U71 |
| 15 | U73 `ant` CLI parity | P3 | M | `ant apply`, sessions connect | U71 |
| 16 | U75 Product-surface registry + parity audit | P3 | M | Needs live research first (Claude Code, Agent SDK, MCP not yet audited) | U61 |

## What each cycle closes (one line)
- U61: pick canonical tree, port unique work, drift-proof version.
- U62: Sonnet 4.5 → DEPRECATED_MODELS, verify RETIRED_MODELS.
- U63: capabilities from Models API (`line`, `thinking.types.*`, `server_tools`); add `claude-mythos-5-1`; Haiku 5.5 second price tier.
- U64: pre-flight validator for the 400-error matrix of Fable 5.1, Mythos 5.1, Opus 5.5, Sonnet 5.5, Haiku 5.5, Sonnet 5.
- U65: ten opt-in beta features (see prompt) with typed response blocks.
- U66: per-model cache-read multiplier, refusal billing, geo multiplier, tokenizer caveat.
- U67: `computer_toolset_20260801`, `browser_toolset_20260801`, safe defaults.
- U68: ~20 Managed Agents features, exact beta-header rules.
- U69: Admin/Compliance/Enterprise endpoints, read-only first.
- U70: OTel spans, bounded cardinality.
- U71: SDK 2.x/1.x majors, Apache-2.0 license check, rollback flag.
- U72: GA Files/Skills shapes, delete-all-versions guard.
- U73: `ant apply`/lockfile awareness, delegate rather than reimplement.
- U74: provider abstraction + verified availability matrix.
- U75: audit-only until verified.
- U76: lint, hermetic tests, CI, supply-chain, docs.

## Not covered (no verified facts yet)
Claude Code CHANGELOG, Agent SDK, MCP spec changes, Claude apps feature detail, Swift/Apple Foundation Models package (out of scope for a Python CLI). U75 audits these before any code.

## Known open items from v1.60.0
Haiku 5.5 higher price tier; unverified capability sets for the 5.5 models; no per-model modules/flags; Mythos 5.1 not catalogued; 891 pre-existing ruff findings. Covered by U63, U64, U76.
