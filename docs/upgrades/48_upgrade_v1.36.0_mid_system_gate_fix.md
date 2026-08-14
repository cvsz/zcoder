# v1.36.0 — Mid-system model-gate regression, cross-file doc bookkeeping

Triggered by a plain "update to latest and validate/test all features"
request rather than a scheduled per-cycle audit. Started by running the
full suite (475 passed, 0 failures — confirms the tree was regression-clean
going in) and diffing the shipped state against a fresh fetch of the
release-notes overview (checked 2026-07-26).

## Finding 1 (🔴 P0, regression) — stale mid-conversation-system model gate

`claude_cache.py`'s `MID_SYSTEM_SUPPORTED_MODELS` had been `{"claude-opus-4-8"}`
since the feature launched in v1.18.0 (checked against docs as of
2026-07-08 at the time). The July 15, 2026 release notes explicitly
corrected the platform's own earlier availability note:

> Mid-conversation system messages are available on Claude Fable 5, Claude
> Mythos 5, and Claude Opus 4.8 [...] This corrects earlier availability
> notes.

So this wasn't code drifting out of date with a changing platform — the
platform's docs themselves had been wrong, got corrected, and this module
had frozen in the pre-correction state. Net effect: every call to
`generate_cached(..., mid_system=...)` or `multi_turn_cached(...,
mid_system_updates=...)` on Fable 5 or Mythos 5 raised `ValueError` for a
feature those models actually support, since v1.18.0.

Confirmed against two independently-worded searches (the release-notes
overview and the dedicated mid-conversation-system-messages doc page)
before changing anything, per this project's dual-verification convention.
Still explicitly unsupported, confirmed unchanged: Claude Sonnet 5 (use
top-level `system` instead) and Claude Opus 5 (not listed on either
source, unlike the *tool-changes* variant which does include it — these
are two different features gated on two different model sets, worth
flagging since it's an easy mix-up).

**Fix:** `MID_SYSTEM_SUPPORTED_MODELS = {"claude-fable-5", "claude-mythos-5",
"claude-opus-4-8"}`. Updated four stale "Opus 4.8 only" docstring/comment
references in the same file. Rewrote the test that had been asserting the
wrong value (`test_mid_system_supported_models_is_opus_4_8_only` →
`test_mid_system_supported_models_matches_docs`) and added parametrized
coverage confirming `generate_cached()` now accepts both `claude-fable-5`
and `claude-mythos-5` with a mid-system update.

## Finding 2 (bookkeeping, not a code bug) — v1.35.0 cross-file updates incomplete

The uploaded zip was labeled and `pyproject.toml`-pinned at v1.34.0, but
`CHANGELOG.md` already contained a full, accurate v1.35.0 entry (Dreaming
audit — see `docs/47_upgrade_v1.35.0_dreaming_audit.md`), and the code and
tests for that cycle were genuinely present and passing (91 tests
collected in `tests/test_claude_agents_sdk.py`, matching the feature set
CHANGELOG.md described). What hadn't happened:

- `pyproject.toml` version: stuck at 1.34.0 (main.py's own `VERSION`
  constant had correctly been bumped to 1.35.0, so the two files
  disagreed with each other)
- `docs/47_upgrade_v1.35.0_dreaming_audit.md`: referenced by
  `CHANGELOG.md` but did not exist
- `README.md`: headline still read "New in v1.34.0" as the newest entry

This is exactly the kind of gap this project's own methodology (dual grep
verification, cross-file documentation updates every cycle) exists to
catch — it just hadn't been pointed at itself. Backfilled all three; see
`docs/47_upgrade_v1.35.0_dreaming_audit.md`'s provenance note for detail
on the reconstruction.

## Also checked, confirmed non-gaps

- Claude Opus 5: present in `MODEL_CATALOG`, fast-mode support, and
  effort/thinking validation (`claude_opus5.py`) all correct.
- Fast mode removal for Opus 4.7 (2026-07-24) and silent removal for Opus
  4.6 (2026-06-29): both correctly gated in `validate_fast_mode()`.
- MCP tunnels: already on the current `/v1/tunnels` surface with the
  `mcp-tunnels-2026-06-22` beta header, not the old Admin API path.
- Mid-conversation *tool* changes (`claude_tools.py`,
  `MID_CONVERSATION_TOOL_CHANGES_SUPPORTED`): already correctly includes
  Opus 5 alongside Fable 5, Mythos 5, and Opus 4.8 — this is the sibling
  feature to Finding 1 above and was not affected by the same bug, since
  it was added fresh in v1.34.0 against current docs rather than inherited
  from a stale v1.18.0 note.

## Deferred, with reasoning

- **Claude Opus 4.1 deprecation** (retirement announced for 2026-08-05):
  flagged during this cycle's release-notes check, but `claude-opus-4-1-20250805`
  was never present in `MODEL_CATALOG` or `RETIRED_MODELS` to begin with —
  there's no existing zcoder code path this touches. Adding a new
  "announced but not yet retired" tracking structure for a model the
  project never had a reference to felt like scope creep for this cycle
  rather than a gap in existing functionality; revisit if a concrete need
  shows up (same reasoning pattern used for Compliance API and native
  Multiagent orchestration in earlier cycles).
- **Usage-tier consolidation** (Start/Build/Scale) and **Workbench /
  experimental prompt-tools retirement** (2026-08-17): both Console-only
  or account-management surface changes with no corresponding API
  parameter or endpoint zcoder calls — same category as the API-key
  expiration and CMEK-docs items correctly deferred in the v1.27.0 cycle.

## Test suite

475 passed before this cycle's changes; 477 after (net +2: 1 old test
rewritten in place, 1 regression test for the `MID_SYSTEM_SUPPORTED_MODELS`
fix, 2 parametrized Fable 5/Mythos 5 coverage cases — 3 additions minus 1
replaced). No regressions.
