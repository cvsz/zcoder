# v1.34.0 — Re-validation cycle: Opus, Sonnet, Haiku, Fable, Mythos

**Scope requested:** "upgrade all model below to latest update and
validate: Opus, Sonnet, Haiku, Fable, Mythos" — a targeted re-audit of
the five per-model modules (`claude_opus5.py`, `claude_sonnet5.py`,
`claude_haiku45.py`, `claude_fable5.py`/`claude_mythos5.py`) and
`claude_models.MODEL_CATALOG` against a fresh, direct fetch of
`platform.claude.com/docs/en/release-notes/overview` (fetched
2026-07-26 — no release notes exist past July 24, 2026 as of this
fetch, so this cycle is current through the same date range v1.33.0
already covered, re-checked line by line rather than assumed correct).

## What was re-confirmed as already correct

- `MODEL_CATALOG` entries for `claude-opus-5`, `claude-sonnet-5`,
  `claude-haiku-4-5-20251001`, `claude-fable-5`, `claude-mythos-5`:
  context windows, max output, pricing, thinking mode, and the Opus 5
  effort/thinking breaking change all match the live models overview
  and July 24 release note exactly.
- `FAST_MODE_SUPPORTED`/`FAST_MODE_REMOVED_ERROR`/
  `FAST_MODE_REMOVED_SILENT` in `claude_models.py` correctly reflect
  the July 24 removal of fast mode for Opus 4.7 (hard error, no silent
  fallback — distinct from the Opus 4.6 removal, which does silently
  fall back to standard speed).
- `claude_opus5.py`'s effort/thinking guard, `claude_haiku45.py`'s
  extended-thinking-only shape, and `claude_fable5.py`/
  `claude_mythos5.py`'s refusal/fallback handling (including the
  `"default"` fallback mode added 2026-07-24) all still match the docs.

## Finding 1 — Mid-conversation tool changes (beta, 2026-07-01) was entirely missing

**What it is:** add or remove tools between turns of a conversation
while preserving the prompt cache. Supported on exactly four models:
Claude Fable 5, Claude Mythos 5, Claude Opus 4.8, and Claude Opus 5.
Requires the `mid-conversation-tool-changes-2026-07-01` beta header.

**Why it's a gap:** grepped the entire tree for
`mid-conversation-tool-changes|mid_conversation_tool` — zero matches.
None of the five model modules, nor `claude_tools.py` (the shared home
for cross-cutting tool-use features like context editing and task
budgets), had any awareness of this feature.

**Priority: 🟠 P1.** A caller building a long-running agentic loop on
any of these four models who tries to vary `tools` mid-conversation had
no way to know this was supported, safe, or which header it needed.

**Fix:** `claude_tools.py` gains
`MID_CONVERSATION_TOOL_CHANGES_SUPPORTED` (the four-model set),
`validate_mid_conversation_tool_change(model_id)` (warns for any other
model, following the same not-a-hard-block convention as every other
per-model validator in this project), and
`with_mid_conversation_tool_changes(headers, model_id)` (appends the
beta header only for supported models, no-ops otherwise). Wired a new
`--mid-conv-tool-check MODEL_ID` diagnostic flag into `main.py`'s Tool
Use group. 5 new tests in `tests/test_claude_tools.py`.

## Finding 2 — Sonnet 5's strict sampling-parameter rejection was undocumented in code

**What it is:** Claude Sonnet 5 returns a 400 error if `temperature`,
`top_p`, or `top_k` is set to **any** non-default value — stricter
than every other current-tier model, which simply accept non-default
sampling values.

**Why it's a gap:** `claude_sonnet5.py`'s `Sonnet5Client.call()` didn't
expose these parameters at all, so there was no live bug today — but
also no guard if a future caller (or a copy-paste from another
model's client) added them. Grepped `claude_sonnet5.py` for
`temperature|top_p|top_k`: zero matches, despite the module's own
docstring already tracking two other Sonnet-5-specific parameter facts
(`service_tier`, `inference_geo`) in exactly this style.

**Priority: 🟡 P2** (defensive — no current call path was broken, but
the gap was inconsistent with how this module already treats every
other Sonnet-5-specific behavior difference). **Fix:**
`validate_sampling_params(temperature, top_p, top_k)` added alongside
the existing `validate_service_tier()`; `Sonnet5Client.call()` now
accepts (optional) `temperature`/`top_p`/`top_k` kwargs and returns a
client-side error before building the request if any is set, instead
of letting a caller burn a request on a guaranteed 400. 5 new tests in
`tests/test_claude_sonnet5.py`.

## Deliberately out of scope this cycle

- **Managed Agents Dreaming's July 10 expansion** (now supports Claude
  Fable 5 and Claude Sonnet 5 in addition to whatever it already
  supported) is a Managed Agents / `claude_agents_sdk.py` concern, not
  a per-model-module concern — left for a Managed Agents cycle rather
  than touched here, since it doesn't change how `claude_fable5.py` or
  `claude_sonnet5.py` themselves work.
- **Fable 5 / Mythos 5 assistant-prefill and manual-thinking-budget
  rejection** was checked and found to be a non-issue in practice:
  neither module exposes a `thinking` parameter or assistant-prefill
  path in `call()` today, so there's no live code path that could send
  either — flagged here as a note for whichever future cycle adds
  either capability to these two modules, rather than built
  speculatively now.

## Tests

10 new tests total (`tests/test_claude_tools.py` +5,
`tests/test_claude_sonnet5.py` +5). Full existing suite (`pytest`,
excluding the pre-existing `fastapi`-dependent `test_webapp_server.py`)
still passes with no regressions — 506 passed.
