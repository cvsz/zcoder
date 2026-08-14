# v1.33.0 — Dedicated deep-detail modules: Claude Opus 5, Sonnet 5, Haiku 4.5

Requested as "deep upgrade Opus 5, and separate each [current-tier]
model out in detail." Starting point: `claude_fable5.py` and
`claude_mythos5.py` are the project's only per-model modules — every
current-tier model (Opus 5, Sonnet 5, Haiku 4.5) lives only as one row
in `claude_models.MODEL_CATALOG`, the same shallow
`{display_name, context_window, price_in, price_out, thinking,
effort_default, notes}` shape every row gets. That's an adequate index
but it can't express anything that needs to be *executable logic*
rather than prose in a `notes` string — which turned out to matter most
for Opus 5 specifically.

## Finding 1 — Opus 5's breaking change was documentation, not enforcement

`MODEL_CATALOG["claude-opus-5"]["notes"]` already said the right thing:
*"disabling thinking (thinking.type='disabled') is only allowed at
effort high or below."* But nothing in the codebase checked this before
sending a request — a caller combining `--opus5-effort xhigh` with
thinking disabled would just burn a request on a guaranteed HTTP 400.

**Fix:** `claude_opus5.py` (new) adds `validate_effort_thinking(effort,
disable_thinking)`, called inside `Opus5Client.call()` before any HTTP
request is built. `OPUS5_THINKING_DISABLE_ALLOWED = {"low", "medium",
"high"}` is the actual allow-list; `xhigh`/`max` + disabled raises
`ValueError` client-side. Also added `OPUS5_EFFORT_BUDGETS` with an
`xhigh` rung — `claude_models.EFFORT_BUDGETS` (used by
`AdaptiveThinkingCoder`) only has `low`/`medium`/`high`/`max` and
predates Opus 5, so it's still missing this rung; `claude_opus5.py`
does not blend into that shared table, to avoid quietly reintroducing
the gap.

Also flagged, not fixed (can't be fixed locally, only confirmed):
`claude_models.INFERENCE_GEO_SUPPORTED` was last checked 2026-07-02,
three weeks before Opus 5 existed, and doesn't list `claude-opus-5`.
`validate_inference_geo()` treats this as *unconfirmed* rather than
assuming either a yes or a no, and `--opus5-geo` prints that warning
rather than silently allowing or silently blocking the request.

## Finding 2 — Sonnet 5's promo pricing was a date a human has to remember, not a comparison the code makes

`MODEL_CATALOG["claude-sonnet-5"]["notes"]`: *"Introductory pricing
$2/$10 per MTok through 2026-08-31."* The catalog's own
`price_in`/`price_out` fields are the **standard** $3/$15 rate — any
cost estimate built directly off those two fields silently uses the
wrong number for every request made before 2026-08-31.

**Fix:** `claude_sonnet5.py` (new) adds `current_pricing(as_of=None)`,
an actual `date` comparison against `PROMO_END_DATE = date(2026, 8,
31)` (inclusive), and `estimate_cost_usd()` / `--sonnet5-cost IN,OUT`
built on top of it. Also surfaces two API-parameter facts that are easy
to get backwards for this specific model: Sonnet 5 is the one
current-tier model that does **not** support `service_tier`/Priority
Tier (grouped with the Mythos-class models in
`SERVICE_TIER_UNSUPPORTED`, not with the other Opus/Sonnet rows), while
it **does** support `inference_geo` (grouped with the Opus rows
instead). `validate_service_tier()` warns rather than silently sending
a parameter this model will reject.

## Finding 3 — Haiku 4.5 is the only current model on extended (not adaptive) thinking, and nothing enforced the distinction

Every other current-tier model in this project uses adaptive thinking.
Haiku 4.5 is `"thinking": "extended"` in the catalog — meaning a caller
must supply an explicit `budget_tokens` and there is no
model-decides-depth fallback. Any code path that builds a `thinking`
block by checking only "does this model support thinking" without also
checking "which *kind*" would send Haiku 4.5 a request shaped for
adaptive thinking, which it doesn't accept.

**Fix:** `claude_haiku45.py` (new) centralizes this in
`build_thinking_param(budget_tokens)` — the one function that decides
the request shape for this model. It always returns `{"type":
"enabled", "budget_tokens": N}` (raising `ValueError` below the
documented 1024-token floor) and never `{"type": "adaptive"}`. Also
resolves the dateless alias `claude-haiku-4-5` → the full
`claude-haiku-4-5-20251001` ID (`resolve_model_id()`), and flags the
two features this model doesn't have: fast mode
(`FAST_MODE_SUPPORTED` is Opus-only) and `inference_geo` data residency
(absent from `INFERENCE_GEO_SUPPORTED`).

## Wiring

All three modules follow the existing `claude_fable5.py` /
`claude_mythos5.py` conventions exactly: a `_call`/`_post` pair with the
project's shared `retry`/`CircuitBreaker` decorator, a `cmd_*_info()`
that prints a capability table, a `cmd_*_call()` that prints the
response text, and validation functions that return `None` (safe) or a
message string (not safe) rather than raising where the caller might
reasonably want to just display a warning instead of aborting.

`main.py` gained three new argument groups ("Claude Opus 5", "Claude
Sonnet 5", "Claude Haiku 4.5", each marked "deep model-specific
support") wired into the existing info-command and call-command
dispatch blocks alongside `--fable5-info`/`--fable5` and
`--mythos5-info`/`--mythos5`.

New flags:
```
--opus5-info  --opus5 PROMPT  --opus5-effort LEVEL
--opus5-disable-thinking  --opus5-fast  --opus5-geo

--sonnet5-info  --sonnet5 PROMPT  --sonnet5-geo  --sonnet5-cost IN,OUT

--haiku45-info  --haiku45 PROMPT  --haiku45-thinking-budget N
```

## Tests

30 new tests across `tests/test_claude_opus5.py` (9),
`tests/test_claude_sonnet5.py` (9), and `tests/test_claude_haiku45.py`
(12) — concentrated on the validation logic in each module (the
effort/thinking breaking-change guard, the pricing cliff-edge date
comparison, the extended-vs-adaptive thinking shape) rather than
re-testing the shared `_call`/`_post` plumbing already covered by
`test_claude_fable5.py`. Full existing suite (`pytest`, excluding the
pre-existing `fastapi`-dependent `test_webapp_server.py`, which has
nothing to do with this change) still passes with no regressions.

## Deliberately out of scope this cycle

- **Mythos-class models unaffected.** `claude_fable5.py` /
  `claude_mythos5.py` already had this level of detail; this cycle only
  closed the gap for the three current-tier models that didn't.
- **`claude_models.EFFORT_BUDGETS` was not patched to add `xhigh`.**
  `claude_opus5.py` defines its own authoritative `OPUS5_EFFORT_BUDGETS`
  instead, since `EFFORT_BUDGETS` is shared by `AdaptiveThinkingCoder`
  for every model and changing its shape has a wider blast radius than
  this cycle's scope — flagged here rather than silently left alone.
- **`--upgrade-all` was not extended to target Sonnet 5 or Haiku 4.5.**
  `UPGRADE_TARGETS` still only offers `fable5`/`opus` (meaning
  `claude-opus-4-8`); adding Opus 5, Sonnet 5, or Haiku 4.5 as rewrite
  targets is a product decision (which model *should* old references be
  upgraded to) rather than something implied by "separate each model in
  detail," so it was left alone.
