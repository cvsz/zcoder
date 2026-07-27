# v1.32.0 — Release validation: Claude Opus 5, fast-mode enforcement, fallbacks "default"

Requested as "upgrade all source code to release, validate" — fetched
`platform.claude.com/docs/en/release-notes/overview` directly (not
reused from a prior cycle) to see everything since the last audit
(2026-07-14, v1.30.0). Ten days of release notes, most consequential:
**Claude Opus 5 launched July 24, 2026** — a new model, not in
`MODEL_CATALOG` until this cycle.

## Finding 1 — Claude Opus 5 was entirely missing from the model catalog

`claude-opus-5`: 1M token context window (both default and max), 128k
max output tokens, thinking on by default, $5/$25 per MTok (same as
Opus 4.8), full effort ladder (`low`/`medium`/`high`/`xhigh`/`max`).
Added to `MODEL_CATALOG` in `claude_models.py` with a `notes` field
calling out the one breaking behavior change from Opus 4.8: disabling
thinking (`thinking.type="disabled"`) is only allowed at effort `high`
or below — `xhigh` or `max` combined with thinking disabled now returns
a 400. Opus 4.8 stays in the catalog as `"current"` tier (still GA, no
retirement announced) rather than being downgraded to `"legacy"` — Opus
5 is a new option alongside it, not a like-for-like replacement the way
Opus 4.7→4.8 was.

## Finding 2 — Fast mode's removal-behavior sets were defined but never actually checked against anything

`claude_models.py` already had `FAST_MODE_SUPPORTED`/`FAST_MODE_DEPRECATED`
constants (added in the 2026-07-02 cycle), but a repo-wide grep found
zero call sites reading them. `coder.py`'s `Coder.generate()` sent
`payload["speed"] = "fast"` unconditionally whenever `--fast-mode` was
passed, for *any* model — the constants existed purely as documentation,
never as validation. This was tolerable while Opus 4.7 fast mode was
merely deprecated (still functioned), but the July 24, 2026 release note
says fast mode for Opus 4.7 is now **removed with a hard error** — unlike
Opus 4.6's removal on June 29, which silently falls back to standard
speed/pricing instead of erroring. Two different removal behaviors,
neither enforced anywhere.

**Fix:** replaced the single stale `FAST_MODE_DEPRECATED` set with
`FAST_MODE_REMOVED_ERROR = {"claude-opus-4-7"}` and
`FAST_MODE_REMOVED_SILENT = {"claude-opus-4-6"}`, added
`FAST_MODE_SUPPORTED = {"claude-opus-5", "claude-opus-4-8"}`, and added
`validate_fast_mode(model_id)` returning `None` (safe) or a reason
string. Wired it into `Coder.generate()`: a model in
`FAST_MODE_REMOVED_ERROR` now short-circuits locally with a clear
`[ERROR]` string *before* making a network call (instead of burning a
request on a guaranteed 400); a model in `FAST_MODE_REMOVED_SILENT`
still sends the request (it's not wrong, just pointless) but logs a
warning explaining why the response won't actually be faster or
differently priced. 5 new tests in `tests/test_coder.py` — this is also
the first test coverage `--fast-mode` has had at all; there was no
existing assertion anywhere that `payload["speed"]` gets set correctly.

## Finding 3 — `fallbacks` parameter's new "default" mode

The July 24, 2026 note: `fallbacks` now also accepts the literal string
`"default"` (not just an explicit model list), which applies Anthropic's
own recommended fallback models by refusal category, gated behind a
*different* beta header (`server-side-fallback-2026-07-01`) than the
one this project already sends on manual fallback retries
(`fallback-credit-2026-06-01`, a different mechanism entirely — see
`claude_fable5.py`'s existing comment distinguishing them). Extended
`Fable5Client.fallback_chain` to accept the string `"default"` alongside
the existing list form; `parse_fallback_chain()` (used by
`--fable5-fallback-chain`) now recognizes the literal value `default`
(case-insensitively) and returns it as-is instead of trying to
comma-split it. The beta header is attached automatically only when
`fallback_chain == "default"` — an explicit list still sends no beta
header, matching the existing, previously-verified behavior. 3 new
tests in `tests/test_claude_fable5.py`.

## Checked and confirmed already correct / out of scope this cycle

- **MCP tunnels, advisor `max_tokens`, `code_execution_20260120`** — all
  reconfirmed already implemented (no change since the June sweep noted
  in `docs/38`).
- **Mid-conversation tool changes** (beta, `mid-conversation-tool-changes-
  2026-07-01`, on Fable 5/Mythos 5/Opus 4.8/Opus 5) — genuinely new and
  not built. Different shape of feature from the already-implemented
  mid-conversation *system messages* (`docs/35`) — this one lets tools
  themselves be added/removed between turns. Not implemented this cycle;
  flagged as a follow-up, since it touches the same tool-definition
  plumbing as several existing modules and deserved its own pass rather
  than a rushed addition alongside a model-catalog + fast-mode fix.
- **Managed Agents `effort` on agent model config, environment/memory-
  store webhook events, session `initial_events` seeding, optional
  `version` on agent update, thread-level event deltas** (all July 22) —
  real gaps in `claude_agents_sdk.py`, not touched this cycle. Noted here
  rather than silently dropped so the next Managed-Agents-focused cycle
  picks them up instead of re-discovering them from scratch.
- **Workbench sunset / experimental prompt-tools retirement** (both
  August 17, 2026) — Console-side deprecations of endpoints
  (`/v1/experimental/generate_prompt` etc.) this project's own
  `claude_prompt_optimizer.py` module doesn't call (confirmed by grep) —
  not a code gap.

## Validation

Full suite after this cycle: **392 tests passed, 1 skipped, 0 failed**
(`test_webapp_server.py` excluded from the run — needs `fastapi`, an
optional dependency not installed in this environment; the 1 skip is
`test_tui.py`'s own optional-dependency guard, same caveat as prior
cycles, not a code issue). `main.py`'s `VERSION` bumped to `"1.32.0"`.
