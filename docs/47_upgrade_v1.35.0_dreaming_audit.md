# v1.35.0 — Dreaming audit: model-support expansion, missing archive, unreachable cancel

> **Note on this file's provenance:** this write-up was reconstructed in the
> v1.36.0 cycle. `CHANGELOG.md`'s v1.35.0 entry pointed to this path, and the
> code/tests for v1.35.0 were genuinely present and passing in the tree, but
> this file itself — along with the `pyproject.toml` version bump and the
> README headline — had never actually been written. Content below matches
> what shipped in the code and what `CHANGELOG.md` already documented; it is
> not a new audit, just the missing paper trail for one that already
> happened.

First Dreaming-focused audit cycle since the feature was originally closed
out in v1.20.0. Re-checked `claude_agents_sdk.py`'s Dreaming surface
(`create_dream`, `get_dream`, `list_dreams`, `cancel_dream`,
`archive_dream`) against a fresh fetch of the Managed Agents / Dreaming
docs and the release-notes overview.

## Finding 1 (🔴 P0, bug) — wrong request shape for `model`

`create_dream()` sent `model={"id": model}` instead of the documented
plain string `model=model`. No existing test asserted on the `model`
kwarg's shape, so this shipped in v1.20.0 and went unnoticed for 15
versions. Fixed, with a regression test that would have caught it
immediately.

## Finding 2 (🟠 P1) — supported-model set expanded

Dreaming's supported-model set expanded to include Claude Fable 5 and
Claude Sonnet 5 (per the July 10, 2026 release note) — confirmed real and
still current. This had previously been flagged and correctly deferred by
the v1.23.0 and v1.34.0 cycles as out of scope for per-model-module work.
Closed this cycle: added `DREAMING_SUPPORTED_MODELS` and
`validate_dreaming_model()`.

## Finding 3 (🟠 P1) — `archive_dream()` entirely missing

`create`/`get`/`list`/`cancel` all shipped together in v1.20.0, but
`archive_dream()` was never built. Added
`ManagedAgentsClient.archive_dream()`, `cmd_agent_dream_archive()`, and
the `--agent-dream-archive` CLI flag.

## Finding 4 (🟡 P2) — `cancel_dream()` unreachable from the CLI

`cancel_dream()` existed at the client layer since v1.20.0 but had zero
CLI wiring — the same "implemented but unreachable" pattern the project
has hit before with other flags. Added `cmd_agent_dream_cancel()` and
`--agent-dream-cancel`.

## Finding 5 (🟡 P2) — `get_dream()` dropped response fields

`get_dream()` dropped `usage`, `session_id`, and `archived_at` from the
response even though the documented polling pattern depends on `usage`.
Now surfaces all three.

## Also in this cycle

- `list_dreams()` pagination (`limit`/`page`, matching the documented
  signature) plus `--agent-dream-list-limit/-page/-include-archived`.
- `instructions` 4,096-char soft limit via
  `validate_dreaming_instructions()`.
- 19 new/changed tests in `tests/test_claude_agents_sdk.py` (92 documented
  at the time; actual collected count is 91 — a one-off counting slip in
  the original CHANGELOG entry, left as-is here since it doesn't affect
  behavior, noted for the record).

## Methodology note

Same dual-grep-verification and cross-file-update convention as prior
cycles. This cycle is also the one that surfaced the convention's own
failure mode: a cycle's code and tests can be complete and passing while
its documentation trail (this file, the version bump, the README
headline) silently doesn't happen. See `docs/48_upgrade_v1.36.0_mid_system_gate_fix.md`
for the fix and the process note on preventing a repeat.
