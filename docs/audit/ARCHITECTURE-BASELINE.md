# ZCoder — Architecture Baseline (Independent Audit)

**Repository:** https://github.com/cvsz/zcoder  
**Branch:** `main`  
**Initial HEAD:** `e868ee44dea4df7ae2d7ef1cccc1151e273ee8db`  
**Audit date:** 2026-11-08  
**Auditor:** cvsz  
**Reference policy:** Clean Architecture per `CONTRIBUTING.md` ("interfaces + api -> services -> domain <- infrastructure"); ZEAZ canonical policy (https://github.com/cvsz/zeaz/blob/main/zeaz.md); local `AGENTS.md`.

## Dependency direction (verified by inspection)

The codebase observes the Clean Architecture boundary:

```
interfaces + api  -->  services  -->  domain  <--  infrastructure
```

- `src/zcoder/domain/` (models, services, interfaces) does **not** import concrete infrastructure, CLI/TUI, FastAPI, or web adapters.
- Infrastructure (`src/zcoder/infrastructure/`, `src/zcoder/services/`) implements domain/application ports; it does not define business invariants.
- Provider-specific behavior stays within its provider integration boundary (`src/zcoder/agent/integrations/`, `src/zcoder/api/`).
- CLI, SDK, TUI, web, and worker surfaces delegate to shared application code (`src/zcoder/services/`, `src/zcoder/core/`).
- Provider-neutral authentication and tool/permission boundaries are not coupled to consumer OAuth credentials.

## Circular import check

- `python -m compileall -q src tests` passes (exit 0) — no import-time cycles preventing compilation.
- mypy `src/zcoder webapp --ignore-missing-imports` passes (no issues in 197 source files).
- No import-cycle findings surfaced by compile or type check.

## Duplicate / competing implementations

Reviewed. No duplicate competing implementations of core security surfaces found:
- Centralized path containment is in `src/zcoder/core/security.py` (`safe_resolve`, `read_text_prefix`, `contains_secret`, `build_child_env`, `validate_url`, `validate_name`); callers delegate to it rather than re-implementing ad hoc checks.
- Provider adapters live under `src/zcoder/agent/orchestration/adapters.py` and `src/zcoder/agent/integrations/`.
- Historical top-level import names are compatibility aliases only; new internal code uses `zcoder.*` imports.

## Unbounded work / resource consumption

Reviewed; bounded controls present:
- `MAX_FILE_SIZE_BYTES` (25 MB default) and bounded text-read prefix (`read_text_prefix`, 1 MiB default) prevent unbounded memory reads.
- `MAX_OBJECT_BYTES = 64 MiB` object-storage cap (enterprise no-cost platform).
- Bounded retries with explicit timeouts in `core/resilience.py`; retryability classified via typed errors in `core/exceptions.py`.
- File descriptor/subprocess lifecycle: subprocess calls use explicit `argv` (no implicit `shell=True`), timeouts where applicable, `capture_output=True`.
- Session/checkpoint IDs validated (`[A-Za-z0-9_-]{1,64}`); `_safe_child_path()` uses `os.path.realpath` containment.

## Timeouts and cancellation

- Explicit timeouts on subprocess and outbound-network calls where applicable (`timeout=30` in git integration, `timeout_seconds` in provider adapters, `timeout=self.timeout_seconds` in `urllib.request.urlopen`).
- `asyncio_mode = "auto"` in pytest; async correctness covered by `pytest-asyncio`.

## Configuration and secrets

- `python-dotenv` for local env loading.
- `.env`, `.env.bak`, `.env.ai` are gitignored (verified via `git check-ignore`); not committed.
- Credentials injected via environment; no secrets in source code (verified by grep for secret-like patterns and bandit secret rules).
- `config.json` is empty (0 bytes) at root.

## Auditable privileged operations

- Release gate (`src/zcoder/services/release_gate.py`), upgrade lease/fence services, maintenance campaign worker, backup/restore — all with explicit approval/lease boundaries and subprocess env isolation.

## Reproducible builds / dependency management

- `uv.lock` pinned; `uv lock --check` passes (exit 0, 64 packages resolved).
- Docker base images pinned (per SECURITY.md SEC-010).
- GitHub Actions `uses:` refs pinned to immutable full-length commit SHAs.
- `requires-python = ">=3.12"`; Ruff/Black/mypy target Python 3.12.

## Observations

- zGPU component (`src/zgpu/`) is a large bundled acceleration layer with its own tests under `src/zgpu/tests/`; these are **not** included in pytest `testpaths = ["tests"]`, so `make test`/CI `pytest` does not run them. They pass when run directly. Documented as observation GZ-01 (no change made pending confirmation of intent).
- `ruff format --check` reports 19 files would be reformatted, but CI gate is `black --check .` (passes). ruff format and black disagree on line-wrapping for 19 files; applying ruff format breaks black. Documented as P3 RF-01 (no change made to avoid breaking the CI black gate).

## Architecture status

**Status: IMPLEMENTED / BOUNDARIES RESPECTED** — Clean Architecture dependency direction observed, no circular imports, no duplicate competing security implementations, bounded resource consumption, explicit timeouts, reproducible dependency management. No new circular dependencies or duplicate implementations introduced in this audit.
