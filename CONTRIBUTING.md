# Contributing

## Setup

```bash
git clone <repo>
cd zcoder
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

The canonical implementation is under `src/zcoder/`. Historical top-level import names are compatibility aliases only; new internal code must use `zcoder.*` imports.

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

CI (`.github/workflows/ci.yml`) runs lint/security checks, pytest with coverage on Python 3.9–3.12, package/import smoke tests, and a Docker build smoke test.

## Architecture and dependency rules

Follow [`ARCHITECTURE.md`](ARCHITECTURE.md):

```text
interfaces + api -> services -> domain <- infrastructure
```

- `domain/` must not import concrete infrastructure, CLI/TUI, FastAPI, or web adapters.
- Infrastructure implements domain/application ports; it does not define business invariants.
- Provider-specific behavior stays within its provider integration boundary.
- CLI, SDK, TUI, web, and worker surfaces delegate to shared application code.

## Test placement

Place tests by execution semantics:

- `tests/unit/` — isolated module/service/CLI behavior;
- `tests/integration/` — stores, identity, conformance, and adapter integration;
- `tests/e2e/` — restart/crash/fleet/enterprise/web scenarios;
- `tests/e2e/upgrade_suites/` — historical upgrade acceptance suites.

Tests must not make accidental real provider calls. Mock external HTTP/provider behavior unless the test is explicitly documented and gated as a live integration test.

## Code conventions

- Network failures should use the typed errors in `zcoder.core.exceptions` so `zcoder.core.resilience` can classify retryability.
- New user-controlled paths/names must go through `zcoder.core.security` validation before filesystem or outbound-request use.
- New structured logging uses `zcoder.config.logging.get_logger(__name__)`; never log secrets.
- New Claude/provider capability code belongs in the matching `zcoder.claude.*` package rather than creating another flat root module.
- Preserve backward compatibility shims only at explicit public boundaries; do not add new code to the shim layer.

## Documentation

`docs/README.md` defines the documentation taxonomy. Put new material in the matching directory (`architecture`, `security`, `compliance`, `operations`, `enterprise`, `guides`, `upgrades`, or `prompts`) rather than the `docs/` root.

Historical detailed release notes live under `docs/upgrades/`.

## Versioning

`CHANGELOG.md` is the release history. Bump the version in `src/zcoder/main.py` and `pyproject.toml` together and verify the installed CLI before release:

```bash
python -m pip install -e .
zcoder --version
python main.py --version
```
