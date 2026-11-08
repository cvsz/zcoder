# ZCoder — Dependency Report (Independent Audit)

**Repository:** https://github.com/cvsz/zcoder  
**Branch:** `main`  
**Audit date:** 2026-11-08  
**Auditor:** cvsz  
**Lockfile:** `uv.lock` (64 packages resolved; `uv lock --check` exit 0)

## Dependency management approach

- Python package management via `uv` with deterministic `uv.lock`.
- `requires-python = ">=3.12"`; Ruff/Black/mypy target Python 3.12.
- Upgrades performed in controlled batches only (security patches first, then compatible patch/minor; major upgrades after migration analysis).
- No blind upgrades to latest; no downgrades of secure dependencies without documented compatibility analysis.

## Direct dependencies (`pyproject.toml`)

| Dependency | Version constraint | Purpose | Notes |
|------------|-------------------|---------|-------|
| python-dotenv | >=1.2.2 | Local env loading | |
| Pillow | >=13.0.0 (py>=3.11) | Image handling | Re-added after prior CVE removal; pin reviewed |
| textual | >=0.80.0 | TUI framework | |
| fastapi | >=0.141.1 | Web API (web extra) | |
| uvicorn | >=0.23.0 | ASGI server (web extra) | |
| starlette | >=1.3.1 | ASGI toolkit (web extra) | |
| pandas | >=2.0.0 | Excel (excel extra) | |
| openpyxl | >=3.1.0 | Excel (excel extra) | |
| python-pptx | >=0.6.23 (py>=3.11) | PPTX (pptx extra) | |
| anthropic | >=1.2.0,<2.0.0 | Anthropic provider (anthropic extra) | Kept on v1 per CHANGELOG |
| psycopg2-binary | >=2.9.9 | PostgreSQL driver (postgres/dev) | |

## Development dependencies (`[dependency-groups] dev` + `[project.optional-dependencies] dev`)

| Dependency | Version | Purpose |
|------------|---------|---------|
| pytest | >=9.0.3 | Test framework |
| pytest-cov | >=5.0.0 | Coverage |
| pytest-asyncio | >=0.24.0 | Async test support |
| psycopg2-binary | >=2.9.9 | PostgreSQL for tests |
| ruff | >=0.6.0 | Lint/format |
| black | >=24.0.0 | Formatter (CI gate) |
| mypy | >=2.3.1,<3.0.0 | Type checking |
| types-PyYAML | >=6.0.12.20250915 | YAML stubs |
| bandit | >=1.7.9 | Security scan |

## Dependency security

- No known vulnerable dependencies in `requirements.txt` or `requirements-dev.txt`.
- `uv.lock` is pinned and reproducible (`uv lock --check` passes).
- Prior remediation: Pillow CVE fix; truststore, numpy, platformdirs updates (Aikido).
- Anthropic SDK intentionally kept on v1 (v2 migration not yet verified — not forced).

## GitHub Actions / Docker / build tool versions

Pinned to immutable full-length commit SHAs in `.github/workflows/` (per SECURITY.md SEC-010). Dependabot keeps pins current with version-tag comments.

- Docker base images pinned (per SEC-010).
- Helm charts linted in CI (`helm-lint.yml`).

## Upgrades performed in this audit

None. `uv lock --check` passes and all dependency gates green; no controlled batch upgrade was required or performed.

## Known version drift (disclosed, not defects)

Some direct dependencies have newer upstream versions available (e.g., ruff, fastapi). These were NOT upgraded because `uv lock --check` passes and the CHANGELOG requires keeping Anthropic on v1 until a v2 migration is verified. Documented as a P3 observation; no forced upgrades.
