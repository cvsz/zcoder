# Upgrade notes — v1.10.5 → v1.11.0 → v1.11.1

Two passes, both prompted by fresh audits against platform.claude.com/docs
(checked 2026-07-02). This file was referenced from the README's "New in
v1.11.0" section before it existed — it's the missing doc that closes that
loop, plus the smaller v1.11.1 follow-up pass.

## v1.11.0 — closing the `claude-api-gap-audit-v1.10.5` list

Everything below was "missing entirely" or "present but stale" per
`docs/claude-api-gap-audit-v1.10.5.md`. Confirmed against the live docs
before implementing (see that file's own citations) — none of this was
taken on faith from the audit text alone.

| Item | Where | Notes |
|---|---|---|
| Advisor tool | `claude_advisor.py` (new) | `advisor_20260301` / beta `advisor-tool-2026-03-01`. Pairs a fast executor model with a stronger advisor consulted mid-generation. |
| Task budgets | `claude_tools.py` — `build_task_budget()` | Beta `task-budgets-2026-03-13`. Opus 4.7/4.8, Fable 5, Mythos 5 only. Advisory, not a hard cap. |
| Tool Use Examples | `claude_tools.py` — `with_input_examples()` | `input_examples` field, beta `advanced-tool-use-2025-11-20`. |
| Programmatic Tool Calling (real implementation) | `claude_tools.py` — `with_allowed_callers()` | `allowed_callers`, `code_execution_20260120`, `caller` field on `tool_use` blocks. Previously a docstring bullet with no code. |
| Embeddings | `claude_embeddings.py` (new) | Anthropic doesn't host an embedding model — wraps Voyage AI's HTTP endpoint (`voyage-3.5` default), which is what Anthropic's own embeddings doc page points to. |
| Compaction | `claude_tools.py` — `build_context_management(compact=True)`, `resume_after_compaction()` | Beta `compact-2026-01-12`. Distinct from context editing: compaction *summarizes*, clearing *drops*. |
| Fine-grained tool streaming | `claude_stream.py` — `with_eager_input_streaming()`, `stream_with_tools()` | GA, no beta header — per-tool `eager_input_streaming` field, not the legacy blanket header (kept for back-compat). |
| `stop_details` on refusals | `claude_stream.py` — `handle_refusal()` | Reads `category` (`cyber`/`bio`/null) + `explanation` off a refusal response. |
| Refusal billing exemption | `claude_metrics.py` | `stop_reason:"refusal"` with no generated output isn't billed; metrics stopped counting cost for it. |

Not done in this pass (see `claude-api-gap-audit-v1.10.5.md` §1 for why):
MCP tunnels — picked up in v1.11.1 below.

## v1.11.1 — follow-up pass

A second check turned up items the v1.11.0 pass didn't cover, plus one
functional bug introduced by Claude Sonnet 5 becoming the default model:

- **MCP tunnels** (research preview, beta `mcp-tunnels-2026-06-22`,
  `/v1/tunnels`) — `claude_agents_sdk.py`, new `McpTunnel` class. Exposes a
  local-only MCP server via a public Anthropic-routed URL so it can be
  wired up as an `mcp_servers` entry without deploying it first. Wired to
  `--code-agent-mcp-tunnel PORT` in `main.py`.
- **`RETIRED_TOOL_VERSIONS` table** — `claude_tools.py`, new
  `RETIRED_TOOL_VERSIONS` dict + `check_retired_tool_version()`, mirroring
  `claude_models.py`'s `RETIRED_MODELS` / `check_retired()` pattern that
  existed for model IDs but not tool-type strings. Surfaced in
  `cmd_list_server_tools()`.
- **Refusal billing exemption in the cost optimizer** — `claude_metrics.py`
  had this from the v1.11.0 pass; `claude_cost_optimizer.py`'s
  `optimized_call()` did not. Fixed to match: a refusal with zero output
  tokens now logs `$0.00` instead of running it through `estimate_cost()`.
- **Sonnet-5 sampling-parameter bug** — not in either gap audit, found
  while implementing the above. Per "What's new in Claude Sonnet 5":
  Sonnet 5 (and Fable 5 / Mythos 5) return a `400 invalid_request_error` if
  `temperature`/`top_p`/`top_k` are set to non-default values at all. Six
  modules hardcoded a `temperature=` value directly into a `messages.create`
  call/payload — harmless on older models, but a hard failure the moment
  `model` defaults to `claude-sonnet-5` (which it does: `coder.py` and
  `claude_cost_optimizer.py`'s `TIER_MODELS` both default there). Fixed by
  adding `utils.sampling_kwargs(model, temperature=...)`, which omits the
  parameter entirely for Sonnet-5-and-newer models and passes it through
  unchanged otherwise, and routing every hardcoded call site through it:
  `claude_cost_optimizer.py`, `claude_router.py` (4 call sites),
  `claude_git.py`, `claude_github.py`, `claude_prompt_optimizer.py` (2 call
  sites), `claude_rag.py`, `claude_research.py`.

  Not yet converted: `claude_eval.py`, `claude_evals.py`, `claude_live.py`
  (its `temperature` is a user-facing constructor parameter, not a stray
  hardcode — worth a follow-up pass to decide the right default rather
  than a mechanical fix), and `coder.py`/`main.py`'s `--temperature` flag
  (accepted but currently unused by `Coder.generate()`, so it's inert
  rather than broken — flagging in case a future change starts sending it).

## Suggested next pass

1. Finish the `sampling_kwargs()` conversion for the four call sites listed
   above as not yet converted.
2. Re-verify beta headers most likely to flip to GA soon: Advisor tool,
   task budgets, and PTC/Tool Use Examples (`advanced-tool-use-2025-11-20`)
   are all still beta as of this check — re-check before removing the beta
   header logic.
3. MCP tunnels is a research preview and the most likely item here to
   change shape entirely; treat `claude_agents_sdk.McpTunnel` as a starting
   point, not a stable contract.