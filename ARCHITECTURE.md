# Architecture

## Status

As of 2026-08-14, zcoder is migrating from a flat-module repository to a
package-based `src/zcoder` layout. `Artifacts-zcoder.md` is the migration source
of truth for the target topology. This document describes the architecture that
the runtime now uses and the compatibility boundaries that remain while legacy
imports are retired.

The key rule is simple: **canonical implementation code lives under
`src/zcoder/`**. The repository-root `main.py` is only a source-checkout launcher,
and temporary top-level compatibility modules under `src/` alias historical
imports such as `coder`, `claude_models`, and `config` to their canonical
`zcoder.*` modules.

## System context

zcoder has several presentation/runtime surfaces over one application core:

```text
                         ┌────────────────────────────┐
                         │        Interfaces           │
                         │ CLI / TUI / SDK / Web API  │
                         └──────────────┬─────────────┘
                                        │
                                        v
                         ┌────────────────────────────┐
                         │     Application services    │
                         │ coder / agents / projects   │
                         │ engineering / GitHub / jobs │
                         └──────────────┬─────────────┘
                                        │
                         ┌──────────────┴─────────────┐
                         v                            v
              ┌────────────────────┐       ┌────────────────────┐
              │       Domain       │       │ Claude integration  │
              │ models / policies  │       │ models / tools /    │
              │ ports / invariants │       │ RAG / enterprise    │
              └─────────┬──────────┘       └─────────┬──────────┘
                        │                            │
                        └─────────────┬──────────────┘
                                      v
                         ┌────────────────────────────┐
                         │      Infrastructure         │
                         │ stores / auth / telemetry  │
                         │ filesystem / external APIs │
                         └──────────────┬─────────────┘
                                        │
                    ┌───────────────────┼────────────────────┐
                    v                   v                    v
               Anthropic API        PostgreSQL /         OIDC / SCIM /
                                    SQLite / files        GitHub / OTEL
```

The CLI remains the primary user-facing entry point, but it is no longer the
architectural root of the codebase. `zcoder.main` performs argument parsing and
dispatch; business behavior belongs in services, domain code, or integration
adapters.

## Canonical package layout

```text
src/zcoder/
├── main.py
├── config/
│   ├── settings.py
│   ├── production.py
│   └── logging.py
├── core/
│   ├── exceptions.py
│   ├── security.py
│   ├── resilience.py
│   ├── health.py
│   └── utils.py
├── domain/
│   ├── models/
│   ├── services/
│   └── interfaces/
├── claude/
│   ├── models/
│   ├── capabilities/
│   ├── tools/
│   ├── integrations/
│   ├── orchestration/
│   ├── optimization/
│   ├── memory/
│   ├── rag/
│   ├── eval/
│   └── enterprise/
├── infrastructure/
│   ├── stores/
│   ├── auth/
│   ├── observability/
│   └── artifacts.py
├── services/
├── api/
│   └── public/
├── interfaces/
│   ├── cli/
│   └── sdk/
├── enterprise/
└── worker/
```

### Configuration and core

`config/` owns runtime configuration, production policy, and logging setup.
`core/` contains cross-cutting primitives that are intentionally independent of
presentation layers: typed errors, retry/circuit-breaker support, input/path
security helpers, health probes, and shared utilities.

### Domain

`domain/models/` contains business state such as engineering tasks, tenants,
portfolio state, product state, residency, and intelligence models.
`domain/interfaces/` defines ports that infrastructure adapters implement.
Domain code must not depend on FastAPI, CLI/TUI code, concrete databases, or
provider SDKs.

### Application services

`services/` coordinates use cases. Examples include model generation, project
and artifact workflows, engineering orchestration, GitHub orchestration,
maintenance intelligence, backup/restore, and background work submission.
Services may depend on domain abstractions and provider/infrastructure ports, but
presentation-specific behavior should stay outside this layer.

### Claude integration

The former `claude_*.py` flat surface is grouped by responsibility:

- `claude/models/` — model registry, preflight, and model-specific behavior.
- `claude/capabilities/` — coding, execution, vision, thinking, structured
  output, search, embeddings, streaming, citations, and advisory behavior.
- `claude/tools/` — tool registry, MCP, plugins, and sandbox support.
- `claude/integrations/` — GitHub, Git, files, Excel, PowerPoint, Chrome, WIF.
- `claude/orchestration/` — routing, workflows, managed agents, batch, live,
  interactive, and sessions.
- `claude/optimization/` — cost, prompt, and token optimization.
- `claude/memory/` and `claude/rag/` — memory/cache and retrieval/research.
- `claude/eval/` — evaluation and output-style support.
- `claude/enterprise/` — Admin API, Compliance API, Skills API, settings,
  permission planning, and metrics.

This topology lets new provider capabilities be added without increasing the
root namespace or coupling unrelated features.

## Dependency rules

The target dependency direction is:

```text
interfaces/ + api/
        |
        v
     services/
        |
        v
      domain/ <--------- infrastructure/
        ^
        |
   provider ports/adapters
```

Rules for new and modified code:

1. `domain/` must not import from `infrastructure/`, `interfaces/`, `api/`, or
   web-framework modules.
2. Infrastructure implements domain/application ports; it does not define
   business invariants.
3. CLI, TUI, SDK, and HTTP layers translate input/output and delegate use cases.
4. Provider-specific behavior stays under its integration boundary rather than
   leaking into domain models.
5. New internal imports must use canonical `zcoder.*` module names.

### Transitional compatibility boundary

Existing v1.40.0 modules contain many historical absolute imports such as
`from config import ...` or `from claude_models import ...`. To avoid a flag-day
rewrite, those names are installed as thin aliases under `src/`. Each alias
loads the canonical `zcoder.*` implementation and binds the legacy name to the
same module object. This is important for monkeypatching and stateful module
singletons: callers using old and new names must not receive two independent
module instances.

The compatibility aliases are transitional. They may be removed only after:

- internal imports use `zcoder.*` consistently;
- tests no longer require historical names;
- documented downstream SDK/import contracts have a deprecation window; and
- a release gate verifies both source and installed-package execution.

## Runtime entry points

### Installed CLI

`pyproject.toml` exposes both commands through the package entry point:

```text
zcoder   -> zcoder.main:main
ai-coder -> zcoder.main:main
```

### Source checkout

`python main.py` remains supported. The root launcher prepends `src/` and then
delegates to `zcoder.main`. It contains no business logic.

### Container

The container runs `python -m zcoder.main` with `/app/src` on `PYTHONPATH`.
Health probes use the same package entry point, preventing a container-only
fallback to deleted root implementation modules.

### Web adapter

`webapp.backend.server` remains a thin FastAPI adapter over the same application
modules. `webapp/__init__.py` exposes `src/` for direct source-checkout uvicorn
execution; installed deployments resolve the package normally.

### Worker

Background worker process behavior is canonical under `zcoder.worker.process`.
Application services submit/coordinate work; the worker owns process execution
and lifecycle concerns.

## Cross-cutting reliability and security

`zcoder.core.exceptions` defines the typed error contract used by retry and
caller boundaries. `zcoder.core.resilience` provides retry/backoff, HTTP error
translation, and circuit-breaker behavior. `zcoder.config.logging` centralizes
structured logging, correlation IDs, and secret redaction. `zcoder.core.security`
contains filesystem, URL, input, and size validation helpers.

Circuit breakers should remain scoped to a stable downstream dependency. Calls
to arbitrary user-selected hosts may use bounded retry but should not share one
breaker whose state could incorrectly block unrelated hosts.

## Admin and Compliance APIs

Admin and Compliance endpoints remain separate enterprise contracts rather than
ordinary model-generation calls. They use organization/compliance credentials
and preserve their own retry/error semantics. Destructive compliance operations
remain explicit opt-in operations; a packaging move must not weaken dry-run or
confirmation behavior.

Credential types must remain separated at the boundary:

- regular model API credentials are for normal model/API surfaces;
- Admin API credentials are for organization administration surfaces; and
- Compliance Access credentials are for compliance-scoped data access where the
  upstream account grants those scopes.

No credential should be copied into client-side web code or persisted in
repository configuration.

## State and persistence

zcoder has more than one persistence mode, so the old statement "there is no
database" is no longer accurate.

- Local CLI configuration, projects, artifacts, and session-oriented state retain
  lightweight filesystem/JSON behavior under the user's home directory where
  those features define it.
- Engineering and enterprise features have concrete SQLite/PostgreSQL adapters
  under `infrastructure/stores/`.
- Domain/application code should depend on store interfaces rather than selecting
  a concrete backend directly.

Concurrent-writer, transaction, durability, and HA guarantees therefore depend
on the selected store. File-backed local state must not be described as having
the same durability semantics as PostgreSQL-backed services.

## Packaging and CI

The distribution uses a PEP 517/518 setuptools build with a `src` package layout.
CI installs the project with `pip install -e .` before tests, then performs a
package/legacy import smoke test. This prevents the repository working only
because the current directory happens to contain importable source files.

The test matrix remains Python 3.9 through 3.12. Docker validation executes the
same package module used by the production container. Build outputs, bytecode,
virtual environments, SQLite test databases/WAL files, coverage outputs, and
local secrets are ignored by `.gitignore` and must not be committed.

## Migration ledger from `Artifacts-zcoder.md`

| Step | Scope | Status in this migration |
|---|---|---|
| 1 | `.gitignore` + tracked artifact cleanup | Executed; existing ignore policy extended and tracked SQLite WAL/SHM artifacts removed |
| 2 | Create `src/zcoder` and move core bootstrap/config | Executed |
| 3 | Move domain models/services/ports | Executed |
| 4 | Move infrastructure stores/auth/observability | Executed |
| 5 | Group `claude_*` by capability | Executed |
| 6 | Move TUI/SDK/API interfaces | Executed |
| 7 | Split tests into unit/integration/e2e | Deferred to a path-audited follow-up; test files currently contain path-sensitive assumptions |
| 8 | Re-taxonomize documentation | Deferred to a link-audited follow-up to avoid breaking existing references |
| 9 | Convert `pyproject.toml` to src packaging | Executed |
| 10 | Full tests + CI/container verification | Required release gate on the migration PR |

Steps 7 and 8 are intentionally rename-only follow-ups after the runtime cutover
is green. Mixing hundreds of path changes with import/packaging changes would make
failures harder to localize and rollback.

## Migration tooling

`scripts/migrate_src_layout.py` is the executable mapping manifest from legacy
root source paths to canonical package paths. It is dry-run by default and only
moves a source when the destination does not already exist. The script is safe
to use as an audit after this migration because completed destinations are
reported as `already-migrated`.

## Architectural decision summary

The migration deliberately prefers **compatibility-first strangulation** over a
flag-day rewrite:

- one canonical package tree;
- temporary aliases for the old import surface;
- package-aware CI and container execution;
- explicit dependency direction for new code; and
- independent follow-up commits for path-only test/document reorganization.

This gives zcoder a maintainable Clean Architecture/DDD-oriented package
structure while preserving the v1.40.0 command and import contracts long enough
to migrate callers safely.
