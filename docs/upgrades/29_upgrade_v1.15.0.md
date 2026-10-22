# v1.15.0 upgrade notes — ROADMAP.md gap-audit implementation

This release implements the five buildable gaps from `ROADMAP.md` Part 2.
Nothing here changes default behavior — every new capability is opt-in via
a new flag.

## P0 — Server-side `fallbacks` param

`provider-specific module`'s `Fable5Client` already had a client-side manual
fallback (`call_with_fallback()`: on a refusal, make a second HTTP call to
`self.fallback_model`). That's a real, documented pattern, but it costs an
extra round trip. The `fallbacks` request parameter lets the platform do
the same retry server-side, in the same round trip:

```bash
zcoder --fable5 "risky prompt" \
  --fable5-fallback-chain provider model ID
```

`call_with_fallback()` now branches on whether `fallback_chain` is set:
if so, it just reads back which model in the chain answered; if not, it
falls through to the original manual retry path unchanged.

## P1 — Context editing in the agent loop

The roadmap's audit claimed `context_management`/`clear_tool_uses`
appeared nowhere in the codebase. That was wrong: `provider-specific module`
already has a complete `build_context_management()` (clear_tool_uses,
clear_thinking, and compact edit types, with the right beta headers). The
real gap, found while implementing this, was narrower: `provider-specific module`'s
`--code-agent` loop never called it.

```bash
zcoder --code-agent -p "long multi-file refactor" \
  --agent-context-editing
```

This is complementary to the existing Compaction support in the same
loop: Compaction *summarizes* the conversation once it nears the context
limit; `clear_tool_uses` *drops* stale tool_result content once the
conversation crosses a smaller token trigger, keeping the most recent N
tool uses intact. Using both together on a long `--code-agent` session
means most of the pruning happens cheaply via clearing, well before
Compaction's summarization would ever need to kick in — worked example:

```python
from provider-specific identifier import CodeAgent, CodeSession
from provider-specific identifier import build_context_management

agent = CodeAgent(api_key=key, model="provider model ID")
session = CodeSession(cwd=".", model="provider model ID")

cm = build_context_management(
    clear_tool_uses=True,
    clear_tool_uses_trigger_tokens=30000,
    compact=True,
    compact_trigger_tokens=150000,
)
result = agent.query(prompt="...", session=session, context_management=cm)
```

## P1 — Agent Skills API (`skill_id`)

New module `provider-specific module`. This is a *different* feature from
`provider-specific module`'s `SkillsRegistry`, which reads
`.provider/skills/<name>/SKILL.md` off the caller's local filesystem. The
platform Skills API instead references pre-built or custom skills by
`skill_id` inside a Messages request's code-execution container:

```bash
zcoder --skills-list
zcoder --skills-info pptx
```

```python
from provider-specific identifier import SkillsApiClient

client = SkillsApiClient(api_key=key)
data = client.call_with_skills(
    "Build a 5-slide deck summarizing this data.",
    skills=["pptx"],
)
```

Routing `provider-specific module` / `provider-specific module` through this instead of
their existing hand-rolled pandas/openpyxl and python-pptx implementation
is a deliberate follow-up (`--excel-native` / `--pptx-native`), not part
of this release — the current implementation keeps working as-is and as
the fallback for accounts without Skills access.

## P2 — Usage and Cost API + API key management

New module `provider-specific module`, combining both since they share the
same Admin API key requirement:

```bash
zcoder --usage-report --admin-api-key sk-ant-admin-...
zcoder --admin-list-keys --admin-api-key sk-ant-admin-...
zcoder --admin-revoke-key key_abc123 --admin-api-key sk-ant-admin-...
```

`--admin-create-key` does not call an endpoint — PROVIDER_CREDENTIAL_OR_CONFIG doesn't
document one. API keys are created through the Console UI, where the
secret is shown exactly once; that's a deliberate security boundary, not
a documentation gap, so this flag explains that instead of faking a
response or silently failing.

`provider-specific module` is unchanged and still does local, estimate
-based cost tracking from token counts — useful for routing decisions
inside a single CLI session. `--usage-report` is the real, org-level,
historical number PROVIDER_CREDENTIAL_OR_CONFIG actually bills against; the two are
cross-linked in each module's docstring.

## P2 — Compliance API

Left as a documented gap. Per the roadmap's own recommendation, this is
an enterprise compliance/audit-log surface with no concrete use case for
a personal/small-team coding CLI yet — building against a guessed shape
risks building the wrong thing. Revisit only on an actual request.
