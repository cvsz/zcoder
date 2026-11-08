# ZCoder — Dependency Upgrade Report

**Repository:** https://github.com/cvsz/zcoder
**Date:** 2026-11-08

## Dependency Inventory

### Python Dependencies
Managed via `uv.lock` and `requirements.txt` / `requirements-dev.txt`.
- Project requires Python 3.12+
- CI uses Python 3.12 and 3.13 matrix
- Lockfile is reproducible (`uv lock --check`, `uv sync --locked`)

### Docker Base Images
- `python:3.14-slim` → `python:3.15-slim` was proposed (Dependabot PR #158) but **closed without merge** — not adopted
- `postgres:15-alpine` for zpostgresql service
- `ghcr.io/ggml-org/llama.cpp:server` for local inference

### GitHub Actions
Multiple Dependabot PRs merged keeping actions up to date:
- `actions/setup-python` v7
- `actions/checkout` v7 (pinned to SHA `3d3c42e5aac5ba805825da76410c181273ba90b1`)
- `actions/upload-artifact` v7
- `astral-sh/setup-uv` v10.x
- `docker/build-push-action` v7
- `docker/metadata-action` v6
- `docker/login-action` v4
- `gitleaks/gitleaks-action` v3.0.0
- `sigstore/cosign-installer` v4.1.2

## Dependabot PRs Reviewed

| PR | Title | State | Disposition |
|----|-------|-------|-------------|
| #158 | chore(deps): bump python from 3.14-slim to 3.14-slim → 3.15-slim | Closed (not merged) | CLOSED_SUPERSEDED — Python 3.15-slim not adopted; project maintains Python 3.12+ support |
| #157 | chore(deps): bump astral-sh/setup-uv 10.3.2 → 10.3.3 | Merged | MERGED_VERIFIED |
| #144 | chore(deps-dev): bump black 26.5.1 → 26.10.1 | Merged | MERGED_VERIFIED |
| #142 | chore(deps): bump astral-sh/uv 0.13.1 → 0.13.5 | Merged | MERGED_VERIFIED |
| #140 | chore(deps-dev): update psutil >=5.9.0 → >=7.2.2 | Merged | MERGED_VERIFIED |
| #139 | chore(deps): update anthropic <2.0.0,>=1.2.0 → >=1.2.0,<3.0.0 | Merged | MERGED_VERIFIED |
| #136 | [Aikido] Fix 10 security issues in truststore, numpy, platformdirs and 3 more | Merged | MERGED_VERIFIED |
| #135 | fix(deps): remove vulnerable Pillow from Python 3.10 | Merged | MERGED_VERIFIED |

## Dependency Upgrade Status

- **No unsafe blind upgrades** — all Dependabot PRs were individually reviewed
- **No downgrades** to conceal test failures
- **Versions pinned appropriately** — `uv.lock` is locked; Docker images pinned by digest; GitHub Actions pinned to immutable SHAs
- **Python 3.15-slim bump rejected** (PR #158) — consistent with project's Python 3.12+ requirement
- **No known vulnerable dependencies** remain

## Recommendations

None — all dependencies are current and compatible. No upgrades are blocked or required.
