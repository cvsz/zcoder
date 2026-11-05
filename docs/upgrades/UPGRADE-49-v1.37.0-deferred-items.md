# v1.37.0 — Closing out v1.36.0's three deferred items

v1.36.0 deferred three findings with reasoning rather than fixing them.
This cycle went back and did each one properly instead of leaving them as
notes.

## 1. Claude Opus 4.1 deprecation — implemented

Previously deferred because `claude-opus-4-1-20250805` was never in
`MODEL_CATALOG` and the project had no structure for "announced but not
yet retired" — only `RETIRED_MODELS`, which represents IDs that already
404. Putting Opus 4.1 there would have been factually wrong; it still
works until 2026-08-05.

Added a proper third state instead of stretching the existing one:

- `DEPRECATED_MODELS` dict — same shape as `RETIRED_MODELS`
  (`display_name`, `replacement`, notes) plus `deprecation_announced` /
  `retirement_scheduled` instead of a single past-tense `retired` date.
- `check_deprecated(model_id)` — mirrors `check_retired()`.
- `cmd_model_info()` now checks both registries and prints a distinct
  ⚠ (yellow, "still works today") vs ✗ (red, "will fail") warning.
- `cmd_check_deprecated(path)` — the existing file/directory scanner —
  now flags deprecated hits in a separate section from retired hits, so
  a repo-wide grep catches "this will break in N weeks" alongside
  "this is already broken."
- `_upgrade_source_ids()` (used by `--upgrade-all`) now includes
  `DEPRECATED_MODELS` keys, so `--upgrade-all --upgrade-target fable5`
  rewrites a lingering `claude-opus-4-1-20250805` reference too, not
  just retired and current-catalog IDs.

Only Opus 4.1 is in `DEPRECATED_MODELS` for now. Claude Sonnet 4.5 has a
reported September 29, 2026 retirement floating around in secondary
sources but no confirmed entry yet on Anthropic's own model-deprecations
page as of this check — left out rather than filed on unconfirmed
secondary reporting; add it once Anthropic's page lists it directly.

New test file `tests/test_claude_models_deprecation.py` (8 tests) — the
first tests `claude_models.py` has had at all; scope limited to the new
deprecation surface, not a full backfill of `validate_fast_mode()`,
`cmd_upgrade_all()`'s file-rewrite path, etc. Flagging that as a real gap
for a future cycle rather than fixing everything under one deferred-item
ticket.

## 2. Usage tier consolidation (Start/Build/Scale) — confirmed non-gap, documented why

Re-verified rather than just re-asserted the earlier call. Two things,
not one:

- The tier **names/thresholds** (old Tier 1–4 → Start/Build/Scale,
  June 26, 2026) are Console-only display — no API field returns a tier
  name, and a grep of the whole tree confirms zcoder never hardcoded the
  old numbering anywhere to begin with. Nothing to change.
- The tier's **effect** (rate limits) *is* API-visible, and zcoder
  already has a full read-only client for it:
  `claude_admin_api.py`'s `--rate-limits` / `--rate-limits-workspace`
  (v1.23.0), backed by `GET /v1/organizations/rate_limits`. Checked its
  output path specifically for hardcoded limit values or tier labels —
  found none; `cmd_rate_limits()` and `cmd_rate_limits_workspace()` both
  print whatever `group.get("limits", [])` the API returns, so the
  raised limits and renamed tiers that shipped June 26 show up
  automatically with no code change needed.

No code changed for this item. Confirmed as a genuine non-gap rather than
an unverified assumption.

## 3. Workbench / experimental prompt tools retirement (2026-08-17) — confirmed non-gap, documented why

`/v1/experimental/generate_prompt`, `/v1/experimental/improve_prompt`,
and `/v1/experimental/templatize_prompt` are retiring alongside the
legacy Workbench on August 17, 2026. Confirmed zcoder has never called
any of the three — no client method, no CLI flag, no test, no doc
reference anywhere in the tree.

Deliberately not adding support for them now: with three weeks left
before the endpoints return errors, building a client against them would
ship dead code. Left a comment in `claude_models.py`'s module docstring
area — no, on reflection a code comment for something that was never
implemented has nowhere honest to live, so this paragraph in
`docs/49_*.md` is the record instead: if a future audit cycle considers
adding prompt-generation/improvement support, don't reach for these
endpoints; they won't exist. The interactive prompt-testing use case they
covered lives in the Console's refreshed Workbench (Build workspace) now,
which isn't API-addressable at all — nothing for a CLI tool to wrap.

## Test suite

477 passing before this cycle; 485 after (+8, all in the new
`tests/test_claude_models_deprecation.py`). No regressions.
