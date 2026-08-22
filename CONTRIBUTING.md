# Contributing

## Setup

```bash
git clone https://github.com/cvsz/zcoder.git
cd zcoder
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

The canonical implementation is under `src/zcoder/`. Historical top-level import names are compatibility aliases only; new internal code must use `zcoder.*` imports.

Read `GOVERNANCE.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `ARCHITECTURE.md`, and `exec-planning.md` before changing architecture, security boundaries, release workflows, or autonomous execution behavior.

## Before opening a PR

Run the repository checks through the Makefile:

```bash
make check
```

Or run the gates individually:

```bash
python -m ruff check .
python -m black --check .
python -m mypy src/zcoder webapp --ignore-missing-imports
python -m bandit -r src/zcoder webapp scripts -ll
python -m pytest --cov --cov-report=term-missing
```

CI runs lint/security checks, pytest with coverage on Python 3.10–3.12, package/import smoke tests, and Docker validation. Hosted checks also include CodeQL, Dependency Review, Release Gate, Helm, and SDK/TypeScript validation.

## Pull request discipline

Use `.github/PULL_REQUEST_TEMPLATE.md` and keep each pull request to one bounded, independently verifiable vertical slice.

- State the problem, scope, acceptance criteria, compatibility impact, and highest-risk assumption.
- Do not combine unrelated refactors with a security fix or production feature.
- Do not weaken tests, coverage thresholds, permissions, CodeQL, Dependency Review, release gates, or security checks.
- Security findings require source-to-sink reachability before remediation.
- Exact final head verification is required; any subsequent code/config/dependency/workflow change requires fresh hosted verification.
- Do not stack a new code slice on an unverified baseline.

## Architecture and dependency rules

Follow [`ARCHITECTURE.md`](ARCHITECTURE.md):

```text
interfaces + api -> services -> domain <- infrastructure
```

- `domain/` must not import concrete infrastructure, CLI/TUI, FastAPI, or web adapters.
- Infrastructure implements domain/application ports; it does not define business invariants.
- Provider-specific behavior stays within its provider integration boundary.
- CLI, SDK, TUI, web, and worker surfaces delegate to shared application code.
- Provider-neutral authentication and tool/permission boundaries must not be coupled to consumer subscription OAuth credentials.

## Test placement

Place tests by execution semantics:

- `tests/unit/` — isolated module/service/CLI behavior;
- `tests/integration/` — stores, identity, conformance, and adapter integration;
- `tests/e2e/` — restart/crash/fleet/enterprise/web scenarios;
- `tests/e2e/upgrade_suites/` — historical upgrade acceptance suites.

Tests must not make accidental real provider calls. Mock external HTTP/provider behavior unless the test is explicitly documented and gated as an authorized live integration test. Never use production data or attack third parties during security validation.

## Code conventions

- Network failures should use the typed errors in `zcoder.core.exceptions` so `zcoder.core.resilience` can classify retryability.
- New user/model-controlled paths must pass centralized security validation before filesystem access.
- Outbound network tools must validate the full source-to-sink path, including redirects and address classification where applicable.
- New structured logging uses `zcoder.config.logging.get_logger(__name__)`; never log secrets.
- New Claude/provider capability code belongs in the matching `zcoder.claude.*` package rather than creating another flat root module.
- Preserve backward compatibility shims only at explicit public boundaries; do not add new code to the shim layer.
- New MCP/hooks/plugins/subprocess integrations must document environment, secret, permission, and tenant trust boundaries.

## Documentation

`docs/README.md` defines the documentation taxonomy. Put new material in the matching directory (`architecture`, `security`, `compliance`, `operations`, `enterprise`, `guides`, `upgrades`, or `prompts`) rather than the `docs/` root.

Keep root community-health files current: `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `SUPPORT.md`, `GOVERNANCE.md`, `CODE_OF_CONDUCT.md`, `ARCHITECTURE.md`, and `exec-planning.md`.

Historical detailed release notes live under `docs/upgrades/`.

## Versioning and release evidence

`CHANGELOG.md` is the release history. Bump the version in `src/zcoder/main.py` and `pyproject.toml` together and verify the installed CLI before release:

```bash
python -m pip install -e .
zcoder --version
python main.py --version
```

Published release artifacts should retain checksums and provenance attestations. Final release evidence must refer to one exact release-candidate commit; changes after qualification invalidate that evidence and require re-verification.
