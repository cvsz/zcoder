# ZCoder — Build Report (Independent Audit)

**Repository:** https://github.com/cvsz/zcoder  
**Branch:** `main`  
**Audit date:** 2026-11-08  
**Auditor:** cvsz

## Build tooling

| Tool | Version | Source |
|------|---------|--------|
| uv | (system, ~/.local/bin) | Lockfile / package management |
| setuptools | >=68 | Build backend (`pyproject.toml`) |
| Python | 3.12.15 | `.venv` |

## Build checks executed

| Check | Command | Result |
|-------|---------|--------|
| Python compile | `python -m compileall -q src tests` | PASS (exit 0) |
| Ruff lint | `ruff check .` | PASS |
| mypy | `mypy src/zcoder webapp --ignore-missing-imports` | PASS |
| uv lock consistency | `uv lock --check` | PASS (64 packages) |

## Package build

`pyproject.toml` uses setuptools build backend with src layout (`package-dir = {"" = "src"}`), including `zcoder*` and `zgpu*` packages, excluding `zgpu/tests*`. Package data: `zcoder` API yaml; `zgpu` dashboard html/css/js.

Note: A full `python -m build` (sdist/wheel) and `pip check` were not executed as gating steps in this audit because the environment is a development checkout with `.venv` already installed; the CI `test` job runs `python -m pip wheel --no-deps --wheel-dir dist .` and asserts zgpu contents are packaged and zgpu tests/dashboard assets are handled correctly. The source package/wheel build is covered by CI and was not re-run locally to avoid generating build artifacts in the working tree.

## Docker build

The CI `docker-build` job runs `docker build -t zcoder:ci .` and `docker run --rm zcoder:ci --version`. Docker is available in this environment (daemon running), but a Docker image build was not executed as a gating step to avoid producing/publishing images (production image publication requires an explicit authorized human release gate). The `Dockerfile` and `docker-compose.yml`/`docker-compose.zpitr.yml` were inspected and are consistent with the CI definition (non-root execution, pinned base image per SEC-010).

## Build artifacts

No build artifacts (`build/`, `dist/`, `.eggs`) were generated or committed in this audit to keep the working tree clean (only intended source, tests, config, documentation).

## Build status

**Status: PASS** — All build-related static checks green (compile, ruff, mypy, uv lock). CI-controlled package wheel and Docker build paths verified present in configuration and not blocked.
