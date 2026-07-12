# Architecture

## Overview

zcoder is a single-process Python CLI that wraps the Anthropic Messages
API, plus a modular set of feature areas (one `claude_*.py` file per API
surface: files, batches, vision, RAG, agents, etc). `main.py` is the only
entrypoint; every feature is reachable as a CLI flag, there is no
long-running server component. Two of those modules —
`claude_admin_api.py` and `claude_compliance_api.py` — talk to
organization-level endpoints under different key types than the rest of
the CLI; see "Admin & Compliance APIs" below.

```
                         ┌─────────────┐
   CLI args ───────────► │   main.py   │  argparse dispatch, no business
                         │             │  logic of its own
                         └──────┬──────┘
                                │
              ┌─────────────────┼─────────────────────┐
              ▼                 ▼                      ▼
        ┌───────────┐   ┌──────────────┐      ┌────────────────┐
        │ coder.py  │   │ claude_*.py  │      │ projects.py /   │
        │ (core     │   │ (one file    │      │ artifacts.py /  │
        │  generate │   │  per API     │      │ personalities.py│
        │  call)    │   │  feature)    │      │ (local state)   │
        └─────┬─────┘   └──────┬───────┘      └────────┬────────┘
              │                │                        │
              └────────┬───────┴────────────────────────┘
                        ▼
              ┌───────────────────┐
              │  Cross-cutting     │
              │  infrastructure:   │
              │  resilience.py     │  retry + circuit breaker
              │  logging_config.py │  structured logs, redaction
              │  security.py       │  path/URL/input validation
              │  exceptions.py     │  typed error hierarchy
              └─────────┬──────────┘
                        ▼
              api.anthropic.com (HTTPS, urllib — no SDK
              dependency for the core path; the `anthropic`
              package is only required for the Managed
              Agents beta client)

              Most modules hit /v1/messages (or /v1/files,
              /v1/batches, ...) with a regular API key.
              claude_admin_api.py hits /v1/organizations/*
              and claude_compliance_api.py hits /v1/compliance/*
              — both need an Admin API key (sk-ant-admin01-...)
              or, for the Compliance module, a Compliance
              Access Key (sk-ant-api01-... with compliance
              scopes) instead of the regular API key everything
              else uses.
```

## Cross-cutting infrastructure

These four modules exist so every feature module gets the same behavior
for free instead of re-implementing it:

- **`exceptions.py`** — every deliberate error is an `AICoderError`
  subclass with a stable `error_code` and a `RETRYABLE` flag. This is the
  contract `resilience.retry()` reads to decide what to retry.
- **`resilience.py`** — `retry()` (exponential backoff with full jitter)
  and `CircuitBreaker` (fail-fast during an outage), plus
  `raise_for_http_error()` / `urlopen_json()` / `urlopen_text()`, shared
  helpers that translate a raw `urllib` HTTP/network exception into the
  `AICoderError` hierarchy `retry()` reads. Wired into every module that
  makes direct HTTP calls (`coder.py`, `claude_files.py`,
  `claude_tools.py`, `claude_code.py`, `claude_models.py`, and 15 others
  — one `CircuitBreaker` per module/downstream, since a GitHub outage
  shouldn't trip the breaker that guards Anthropic API calls, or vice
  versa). Two exceptions by design: `claude_batch.py` and
  `claude_rag.py` call through the `anthropic` SDK client, which retries
  internally, so there's nothing to wire. A handful of call sites that
  fetch an arbitrary caller-supplied URL rather than one fixed dependency
  (`claude_chrome.py`'s page fetch, `claude_research.py`'s source fetch,
  `claude_code.py`'s `WebFetch` tool, `claude_plugins.py`'s marketplace
  fetch) use `retry()` without a `CircuitBreaker`, since a breaker keyed
  on "this one dependency is down" doesn't mean anything when every call
  targets a different host.
- **`logging_config.py`** — one structured logger per module via
  `get_logger(__name__)`, a correlation ID set once per CLI invocation,
  and automatic secret redaction on every log record regardless of what
  gets passed to `logger.info(...)`.
- **`security.py`** — path traversal guards, name/URL/size validation.
  Anything that turns user input into a filesystem path or outbound
  request should go through here rather than string-concatenating paths
  directly.

## Admin & Compliance APIs — a deliberately separate contract

`claude_admin_api.py` and `claude_compliance_api.py` don't route through
`coder.py` or `resilience.py`. They're org-level surfaces, not model
calls, and each has its own documented retry contract (429 + retryable
5xx back off exponentially; 400/401/403/404/409 never retry) implemented
directly in the module rather than reusing `resilience.retry()` — the
two contracts happen to look similar but are specified independently in
Anthropic's docs, so keeping them separate avoids a false coupling if
one changes later.

Key model, since it's easy to get wrong and the failure mode is a 403,
not a crash:
- A regular API key (`sk-ant-api03-...`) — everything else in this CLI
  — cannot call either module.
- An **Admin API key** (`sk-ant-admin01-...`) unlocks all of
  `claude_admin_api.py`, plus *only* the Activity Feed endpoint
  (`--compliance-activities`) in `claude_compliance_api.py`.
- A **Compliance Access Key** (`sk-ant-api01-...`, created in claude.ai
  with specific scopes at creation time — scopes are immutable
  afterward) unlocks the rest of `claude_compliance_api.py`: reading or
  hard-deleting chats, files, and projects, plus directory endpoints.
  It cannot call `claude_admin_api.py`.

`claude_compliance_api.py`'s destructive operations (chat/file/project
hard-delete) are permanent with no recovery window, so every `cmd_*` that
deletes something is dry-run unless the caller passes `yes=True`
(`--compliance-yes` on the CLI) — the same opt-in-execution pattern
`claude_models.py` uses for `--upgrade-all`/`--upgrade-yes`, rather than
a new confirmation convention. Pagination in both modules only advances
its cursor after a page is *successfully* fetched, so a failed request
never silently skips data on retry.

## Why `generate()` still returns strings on error

`Coder.generate()` returns `"[ERROR] ..."` / `"[API ERROR 429] ..."` /
`"[REFUSED] ..."` strings rather than raising, even though the new
internals (`exceptions.py`) are exception-based. This preserves the
existing contract every call site in `main.py` and the `claude_*.py`
modules already depends on (`result = c.generate(...); print(result)`).
Internally, the network call raises typed exceptions so retry/circuit-
breaking/logging can key off `error_code` and `RETRYABLE`; they're caught
and converted back to the legacy string format at the boundary. A future
major version could flip this to raise-by-default with a
`generate(..., raise_on_error=True)` opt-in during the transition.

## State & persistence

All local state is flat JSON files under the user's home directory —
`~/.ai-coder-config.json` (config), `~/.ai-coder/` (projects, artifacts,
files registry, sessions). There is no database. This keeps the tool
zero-install beyond Python + `pip install -r requirements.txt`, at the
cost of no concurrent-writer safety — two CLI invocations writing to the
same project file at once can race. Not addressed in this pass; noted
here so it isn't rediscovered as a surprise.

## Packaging

Two ways to run this:
1. **From source**: `setup.sh`/`setup.bat` create a venv and `.env`.
2. **Standalone binary**: `build.sh`/`build.bat` + `ai-coder.spec` produce
   a PyInstaller single-file executable with no local Python required.
3. **Container**: `Dockerfile` (multi-stage, non-root, healthcheck) +
   `docker-compose.yml` for anything that wants to run this as a service
   dependency rather than a local CLI. See `docs/deployment.md`.
