# zcoder Architecture

## Status

This document describes the canonical repository and runtime architecture after execution of the restructuring plan in `Artifacts-zcoder.md` on 2026-08-14.

**Canonical Python implementation code lives under `src/zcoder/`.** Repository-root launchers and top-level modules under `src/` exist only for backward compatibility. New code must use the package namespace and the dependency rules below.

## Goals

The restructuring converts the former flat Python module layout into a package-oriented architecture that is easier to navigate, package, test, secure, and evolve without changing the v1.40.0 public CLI/import contracts in one flag day.

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
│   └── *.py                    # transitional legacy import aliases
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
│   ├── release_gate.py
│   └── migrate_src_layout.py
├── spec/
│   ├── ai-coder.spec
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

### `zcoder.domain`

Contains business models, domain services, invariants, and interfaces/ports. Current domains include engineering, intelligence, portfolio, product, residency, tenancy, and legacy job state.

Rules:

- domain modules do not import `infrastructure`, `interfaces`, `api`, FastAPI, Textual, or concrete database clients;
- repository/provider interfaces belong on the domain/application side;
- infrastructure implements those interfaces.

### `zcoder.services`

Coordinates application use cases such as generation, projects, artifacts, engineering orchestration, GitHub orchestration, maintenance intelligence, backup/restore, portfolio scheduling, skills, and release-gate behavior.

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

### `zcoder.interfaces` and `zcoder.api`

Presentation/adaptor layers own protocol translation only:

- terminal/TUI under `interfaces/cli`;
- SDK surface under `interfaces/sdk`;
- HTTP/public API under `api`;
- the separate `webapp/` FastAPI/static UI delegates into the same application modules.

## Runtime entry points

### Installed CLI

`pyproject.toml` installs both commands through the canonical package:

```text
zcoder   -> zcoder.main:main
ai-coder -> zcoder.main:main
```

### Source checkout compatibility

`python main.py` remains supported. Root `main.py` inserts `src/` and delegates to `zcoder.main`; it contains no business implementation.

Historical imports such as `import coder`, `import config`, and `import claude_models` remain available through thin aliases under `src/`. These aliases bind callers to the same canonical module objects so monkeypatching and module-level state do not split between old and new names.

New internal imports must use `zcoder.*`. Compatibility aliases may be removed only in a future breaking/deprecation cycle after downstream users have migrated.

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

`zcoder.core.exceptions` defines typed error semantics. `zcoder.core.resilience` owns retry/backoff, HTTP error translation, and circuit breakers. `zcoder.config.logging` centralizes structured logging, correlation IDs, and secret redaction. `zcoder.core.security` owns path, URL, input, and size validation.

Circuit breakers must be scoped to stable downstream dependencies. Calls to arbitrary user-selected hosts may use bounded retry but must not share a breaker whose state could block unrelated hosts.

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

## Documentation architecture

`docs/README.md` is the documentation index. New documents go into the taxonomy instead of accumulating in `docs/` root:

- architecture, security, compliance, operations/runbooks, enterprise, guides, upgrades, prompts.

Historical upgrade and prompt files are preserved byte-for-byte under their taxonomy directories. Root project entry documents remain stable.

## Build, packaging, and release

Python packaging uses PEP 517/setuptools with a `src` layout. Package data includes the Anthropic conformance manifest required at runtime.

Canonical setup/build scripts live under `scripts/` and explicitly change to the repository root before operating. Setup performs an editable package install. Standalone builds use `spec/ai-coder.spec`, which includes `src` in PyInstaller analysis and packages the conformance YAML.

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
8. Any removal of legacy import/launcher compatibility requires an explicit deprecation plan and release note.
