# zcoder Architecture

## Status

This document describes the canonical repository and runtime architecture after execution of the restructuring plan in `Artifacts-zcoder.md` on 2026-08-14.

**Canonical Python implementation code lives under `src/zcoder/`.** Root `main.py` exists only as a source-checkout launcher. New code must use the package namespace and the dependency rules below.

## Goals

The restructuring converts the former flat Python module layout into a package-oriented architecture that is easier to navigate, package, test, secure, and evolve. The migration is complete: all code imports through `zcoder.*`, and the transitional flat modules have been removed.

The design combines Clean Architecture boundaries with pragmatic domain-driven grouping:

```text
Interfaces / API
       |
       v
Application services
       |
       v
     Domain  <----- Infrastructure adapters
       ^
       |
Provider-specific integrations
```

Dependencies point toward domain/application abstractions. Domain code does not import presentation frameworks or concrete infrastructure.

## Repository layout

```text
zcoder/
├── src/
│   ├── zcoder/                 # canonical Python package
│   │   ├── main.py
│   │   ├── config/
│   │   ├── core/
│   │   ├── domain/
│   │   ├── claude/
│   │   ├── services/
│   │   ├── infrastructure/
│   │   ├── api/
│   │   ├── interfaces/
│   │   ├── enterprise/
│   │   └── worker/
├── tests/
│   ├── conftest.py
│   ├── unit/
│   ├── integration/
│   └── e2e/
│       └── upgrade_suites/
├── webapp/
│   ├── backend/
│   └── frontend/
├── docs/
│   ├── architecture/
│   ├── security/
│   ├── compliance/
│   ├── operations/
│   │   └── runbooks/
│   ├── enterprise/
│   ├── guides/
│   ├── upgrades/
│   └── prompts/
├── scripts/
│   ├── build.sh / build.bat
│   ├── setup.sh / setup.bat
│   └── release_gate.py
├── spec/
│   ├── zcoder.spec
│   └── anthropic-conformance.yaml
├── deploy/
├── ARCHITECTURE.md
├── README.md
├── SECURITY.md
├── QUICKSTART.md
└── pyproject.toml
```

The repository-level `README.md`, `SECURITY.md`, `QUICKSTART.md`, and this `ARCHITECTURE.md` intentionally remain at the root because they are conventional project entry points. Canonical build/setup implementation is in `scripts/`; root `build.*` and `setup.*` are compatibility launchers.

## Package boundaries

### `zcoder.config`

Owns user/runtime settings, production configuration, and logging configuration. Configuration code may depend on core utilities but must not contain business workflows.

### `zcoder.core`

Contains cross-cutting primitives: typed exceptions, retry/circuit-breaker behavior, health checks, security validation, and shared utilities. Core code must remain presentation-agnostic.

Shared utilities in `zcoder.core.utils` are the canonical home for provider-agnostic helpers that both application services and infrastructure adapters need — for example `sanitize_dsn()`, which strips query parameters that `psycopg2` cannot parse (`?schema=public` from Prisma-style DSNs) so a connection string written for other tooling does not crash every PostgreSQL connection. Core-level placement keeps the services → infrastructure dependency rule intact: `zcoder.services` may import core utilities but must never import concrete infrastructure adapters.

### `zcoder.domain`

Contains business models, domain services, invariants, and interfaces/ports. Current domains include engineering, intelligence, portfolio, product, residency, tenancy, and legacy job state.

Rules:

- domain modules do not import `infrastructure`, `interfaces`, `api`, FastAPI, Textual, or concrete database clients;
- repository/provider interfaces belong on the domain/application side;
- infrastructure implements those interfaces.

### `zcoder.services`

Coordinates application use cases such as generation, projects, artifacts, engineering orchestration, GitHub orchestration, maintenance intelligence, backup/restore, portfolio scheduling, skills, and release-gate behavior. The GitHub orchestration service accesses the GitHub REST API through a port/adapter seam: `GitHubProviderProtocol` defines the interface on the service side and `GitHubProvider` implements it over `zcoder.core.resilience.safe_urlopen()` (HTTP(S)-only boundary), so tests substitute `FakeGitHubProvider` without network access.

Services translate domain capabilities into workflows but do not own UI rendering.

### `zcoder.claude`

Anthropic/Claude-specific behavior is grouped by responsibility rather than one large flat prefix namespace:

- `models/` — registry, preflight, and model-specific behavior;
- `capabilities/` — code, execution, vision, thinking, structured output, search, embeddings, streaming, citations, advisor;
- `tools/` — tool registry, MCP, plugins, sandbox;
- `integrations/` — GitHub, Git, files, Excel, PowerPoint, Chrome, WIF;
- `orchestration/` — routing, workflows, managed agents, batch, live, interactive sessions;
- `optimization/` — cost, prompt, and token optimization;
- `memory/` and `rag/` — memory/cache and retrieval/research;
- `eval/` — evaluation and output styles;
- `enterprise/` — Admin API, Compliance API, Skills API, settings, permissions, metrics.

Provider-specific policy must not leak into domain models unless it represents a provider-neutral business concept.

### `zcoder.infrastructure`

Contains concrete persistence, authentication, observability, and artifact adapters:

- PostgreSQL and SQLite stores;
- OIDC and SCIM integration;
- OpenTelemetry integration;
- filesystem/artifact implementations.

Infrastructure may depend on domain/application ports. The inverse dependency is prohibited.

PostgreSQL adapters follow these persistence conventions:

- every `psycopg2`/`psycopg` entry point (pool creation and direct connects in `services/backup_restore.py`) routes the DSN through `zcoder.core.utils.sanitize_dsn()` before use;
- schema DDL is idempotent (`CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS`), indexes cover every WHERE/JOIN/ORDER BY access pattern (queue status+creation time, lease expiry, foreign-key sides, checkpoint lookup by attempt), and write paths use `INSERT ... ON CONFLICT` so worker retries cannot crash on duplicate keys;
- tenant isolation is explicit per store: `enterprise_postgres.py` enforces multi-tenant RLS with `FORCE ROW LEVEL SECURITY` plus per-table policies keyed on `current_setting('app.current_org')`, while the single-tenant engineering store (`postgres_engineering.py`) deliberately has no RLS statements — enabling RLS without policies would silently deny all rows to any non-owner role.

### `zcoder.interfaces` and `zcoder.api`

Presentation/adaptor layers own protocol translation only:

- terminal/TUI under `interfaces/cli`;
- SDK surface under `interfaces/sdk`;
- HTTP/public API under `api`;
- the separate `webapp/` FastAPI/static UI delegates into the same application modules.

## Runtime entry points

### Installed CLI

`pyproject.toml` installs the canonical command through the package:

```text
zcoder   -> zcoder.main:main
```

### Source checkout compatibility

`python main.py` remains supported. Root `main.py` inserts `src/` and delegates to `zcoder.main`; it contains no business implementation. Tests asserting launcher parity import root `main.py` directly.

The former flat modules under `src/` (`coder`, `config`, `claude_models`, ...) were removed in this cycle: every import across the repository now uses the canonical `zcoder.*` namespace, and `pyproject.toml` no longer ships `py-modules` shims. Any code still importing a flat name is importing stale or external code.

### Container

The container executes `python -m zcoder.main` with `/app/src` on `PYTHONPATH`. Health probes use the same package entry point so container behavior cannot accidentally depend on deleted root implementation files.

### Web application

`webapp.backend.server` is a thin FastAPI adapter. `webapp/__init__.py` makes `src/` available for source-checkout execution; installed environments resolve the package normally.

### Background workers

Worker process behavior is under `zcoder.worker`. Application services coordinate jobs; worker code owns process execution/lifecycle concerns.

## Persistence and state

zcoder supports multiple persistence scopes rather than a single storage model:

- local CLI/project/session state can use user-home files;
- engineering workflows can use SQLite for local durable execution;
- production/enterprise flows can use PostgreSQL-backed stores;
- web session state that is explicitly process-local remains ephemeral unless a durable adapter is selected.

Domain/application code must depend on storage interfaces rather than selecting a concrete backend by import side effect.

## Reliability and security

`zcoder.core.exceptions` defines typed error semantics. `zcoder.core.resilience` owns retry/backoff, HTTP error translation, and circuit breakers. `zcoder.config.logging` centralizes structured logging, correlation IDs, and secret redaction. `zcoder.core.security` owns path, URL, input, and size validation, plus secrets/environment inheritance isolation: `is_secret_env_name()` classifies credential-bearing environment variable names and `build_child_env()` constructs a filtered environment for subprocesses — used by the Bash/run_python tools (`capabilities/code.py`, `tools/registry.py`), hook execution (`capabilities/code.py`, `enterprise/hooks_perms.py`), the status-line command (`enterprise/settings.py`), and backup/restore (`services/backup_restore.py`).

Circuit breakers must be scoped to stable downstream dependencies. Calls to arbitrary user-selected hosts may use bounded retry but must not share a breaker whose state could block unrelated hosts.

### Offline / local mode

`ZCODER_LOCAL_MODE=1` (or `true`/`yes`) switches generation, git, live-streaming, and prompt-optimization call sites to deterministic offline synthesis with no network I/O. Missing API keys are a hard error outside local mode (`[ERROR] No API key configured...`); inside local mode `zcoder.main._api_key` returns a placeholder key so the CLI still reaches command handlers.

Fallback paths must synthesize the response for the current call only. They must not mutate the process environment (e.g. set `ZCODER_LOCAL_MODE` globally on a network error), because that silently flips every later API call in the same process to offline mode. Offline branches must remain pure functions of their inputs so tests can exercise them without touching real credentials.

Secrets must not be committed, logged, returned to browser clients, or embedded in generated artifacts. `.env` and local state/build products are ignored by version control.

## Admin and Compliance API boundary

Admin and Compliance APIs remain distinct enterprise contracts. They are not ordinary model-generation calls and may require different credential classes and retry/error semantics. Destructive compliance operations retain explicit confirmation/dry-run boundaries.

Regular model credentials, Admin API credentials, and compliance-scoped credentials must not be treated as interchangeable.

## Testing architecture

Tests are grouped by execution semantics:

- `tests/unit/` — isolated module/service behavior and CLI wiring;
- `tests/integration/` — persistence, identity, source-of-truth and external-adapter integration behavior;
- `tests/e2e/` — restart/crash/fleet/enterprise/web product scenarios;
- `tests/e2e/upgrade_suites/` — historical upgrade acceptance suites.

`tests/conftest.py` remains at the suite root so fixtures apply to all categories. CI discovers the complete `tests/` tree and installs the package in editable mode before running tests.

Test isolation rules:

- live infrastructure tests (PostgreSQL-dependent) guard the whole module with `pytest.mark.skipif(not _pg_available(), ...)` and probe the DSN with a short `connect_timeout` before running;
- tests that need environment variables (`ZCODER_LOCAL_MODE`, fake API keys) set them per-test and restore the previous values afterwards — module-level environment mutation pollutes every later test in the same process and is prohibited;
- `tests/conftest.py` deletes `ANTHROPIC_API_KEY` per test so a developer's real shell key cannot cause accidental network calls.

## Documentation architecture

`docs/README.md` is the documentation index. New documents go into the taxonomy instead of accumulating in `docs/` root:

- architecture, security, compliance, operations/runbooks, enterprise, guides, upgrades, prompts.

Historical upgrade and prompt files are preserved byte-for-byte under their taxonomy directories. Root project entry documents remain stable.

## Build, packaging, and release

Python packaging uses PEP 517/setuptools with a `src` layout. Package data includes the Anthropic conformance manifest required at runtime.

Canonical setup/build scripts live under `scripts/` and explicitly change to the repository root before operating. Setup performs an editable package install. Standalone builds use `spec/zcoder.spec`, which includes `src` in PyInstaller analysis and packages the conformance YAML.

Generated bytecode, virtual environments, distribution/build directories, package metadata, coverage caches, and SQLite WAL/SHM files are excluded from version control. Previously tracked WAL/SHM files were removed during migration.

## Migration ledger

Execution of `Artifacts-zcoder.md` is complete at the repository-structure level:

| Step | Result |
|---|---|
| 1. `.gitignore` and generated-artifact cleanup | Complete |
| 2. `src/zcoder` bootstrap and config/core move | Complete |
| 3. Domain model organization | Complete |
| 4. Infrastructure organization | Complete |
| 5. Claude integration subpackages | Complete |
| 6. Interface/API organization | Complete |
| 7. Unit/integration/e2e test taxonomy | Complete |
| 8. Documentation taxonomy | Complete |
| 9. `pyproject.toml` src-layout packaging | Complete |
| 10. CI/CD verification | Repository gates configured; hosted execution externally blocked by GitHub Actions billing/spending state |

The GitHub Actions blocker is external to the source tree: hosted jobs are rejected before checkout/runner startup. It must not be interpreted as a lint, security, test, or Docker regression. Once account billing/Actions spending is restored, the existing workflow is the authoritative hosted validation gate.

## Change rules

For future changes:

1. Put implementation code under `src/zcoder`, never back at repository root.
2. Use canonical `zcoder.*` imports for new internal code.
3. Preserve domain dependency direction.
4. Place tests in the category matching their execution semantics.
5. Place docs in the taxonomy defined above.
6. Do not commit generated build/database/cache artifacts.
7. Keep CLI, container, web, SDK, and worker surfaces delegating to shared application code rather than duplicating behavior.
8. Any future removal of launcher compatibility (root `main.py`) requires an explicit deprecation plan and release note.
