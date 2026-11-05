# v1.10.2 — Model lineup refresh

No new modules. This release fixes model *identifiers*, not features:
several modules had drifted to speculative/duplicate model IDs
(`claude-sonnet-4-6`, `claude-opus-4-6`, `claude-opus-4-7`,
`claude-haiku-4-5` without its date suffix) that don't correspond to
real, callable model strings, plus duplicate dict keys in a couple of
pricing tables (later duplicate keys silently won, so the earlier
entries were dead code).

## What changed

Normalized every model ID reference across the codebase to the
current lineup:

| Old (removed) | New (canonical) |
|---|---|
| `claude-sonnet-4-6`, `claude-sonnet-4-5` | `claude-sonnet-5` |
| `claude-opus-4-6`, `claude-opus-4-7`, `claude-opus-4-5` | `claude-opus-4-8` |
| `claude-haiku-4-5` (no date) | `claude-haiku-4-5-20251001` |
| `claude-fable-5` | unchanged |
| `claude-mythos-5` | unchanged |

Files touched: `claude_models.py` (offline fallback list — deduped
from 7 entries with 3 near-identical Opus rows down to 5 real ones),
`claude_cost_optimizer.py` and `claude_metrics.py` (pricing tables —
same dedup, `claude_metrics.py` also gained a `claude-mythos-5` row it
was missing), `claude_tokens.py` (cost-estimate table — filled in the
previously-absent Fable 5 / Mythos 5 rows), `main.py` (`--model`
default and `_model()` fallback), and every `claude_*.py` module that
hardcoded a default model in a constructor.

Also added, in `claude_fable5.py`, `claude_mythos5.py`, and
`--list-models`'s offline output: a note that Fable 5 / Mythos 5
access was suspended 2026-06-12 → 2026-06-30 for US export-control
compliance and restored 2026-07-01
(https://www.anthropic.com/news/fable-mythos-access). This CLI has no
way to detect that suspension window itself (it isn't visible in API
error codes retroactively) — the note exists so a 403 encountered
*during* that window doesn't get misread as a permanent access
problem in bug reports written after the fact.

## What was NOT changed

- `claude-mythos-5`'s access-gating behavior (`MythosAccessError` on
  403/404) — still correct, unrelated to the ID cleanup.
- Actual USD pricing figures — these were already flagged as "ballpark
  only, verify against platform.claude.com/docs" in every table that
  has them, and this release didn't have a way to re-verify live
  pricing, so the numbers are carried over unchanged.
- The Mythos-tier *chat* model info in this doc set is scoped to what
  the API-facing modules need (Fable 5 / Mythos 5). This CLI has no
  module for the not-yet-public `Claude Mythos Preview`
  (Project Glasswing) since it isn't reachable via the standard
  Messages API this CLI wraps.

## Verification

- `python3 -c "import ast,glob; [ast.parse(open(f).read()) for f in glob.glob('*.py')]"` —
  all modules still parse after the regex-based ID substitution.
- Grepped for every old ID pattern post-edit; zero remaining matches
  outside of this changelog and the historical `docs/` write-ups that
  describe what used to be there.
- Manually re-viewed every table that had 2+ occurrences of the same
  old ID (i.e. was at risk of the regex creating a duplicate key) and
  hand-deduped it, rather than trusting the mechanical pass alone.
