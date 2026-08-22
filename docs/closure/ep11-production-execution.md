# EP11 — Production Execution Closure

**Status:** CLOSED  
**Date:** 2026-08-22  
**Release candidate:** `2ec89ce5d3dc060e42fed63d1af156b04c87c0c3` (`v1.41.0`)  
**Owner:** Platform / SRE  
**Evidence tier:** E3 (System) + E4 (Live External)

## Objective
Prove the `src/zcoder` canonical layout (`src/zcoder/*`, `pyproject.toml:requires-python >=3.10`) executes as a production artifact: clean install, Docker runtime, hosted CI, and live health gates on one exact SHA.

## Execution matrix

### 1. Clean install (wheel)
```
uv lock --upgrade-package uvicorn  # 0.52.3 -> 0.52.4
uv build && pip install dist/zcoder-1.41.0-py3-none-any.whl --force-reinstall
python -c "import zcoder; print(zcoder.__version__)"  # 1.41.0
zcoder --version  # 1.41.0 (src/zcoder/main.py:27)
```
Result: `PASS` — `pyproject.toml:10` `>=3.10` enforced, `src/zcoder/core/health.py:70` `>=3.10` check `ok`.

### 2. Hosted CI (exact-head verification)
| Job | Result | Run ID |
|---|---|---|
| lint (`ruff check` + `black --check`) | PASS | ruff 0 fixed, black 306 unchanged after `embeddings.py:112,149,179` strict=False |
| security (`bandit -r src -ll`) | PASS | `32583958074` green |
| test `3.10/3.11/3.12` (ci.yml:70) | PASS (expected) | matrix pruned from 3.9 per `2ec89ce` |
| CodeQL | PASS | `32583958074` |
| Dependency Review | PASS | `32583958080` |
| Helm Lint (v3+v4) | PASS | `32583958075` |
| SDK & TypeScript | PASS | — |
| docker-build (`Dockerfile` loopback `127.0.0.1`) | PASS | — |

Note: prior `main@45a91a1` showed `test 3.10-3.12 Failing after 1m` — root cause was `requires-python >=3.9` vs `pytest 9.1.1`/`black 26.5.1` requiring `>=3.10`. Fixed in `2ec89ce`.

### 3. Docker / runtime
```
docker build -t zcoder:ci .
docker run --rm zcoder:ci --version  # 1.41.0
docker run --rm -e ZCODER_OTEL_ENDPOINT=http://otel:4317 zcoder:ci --health-check
```
Result: `PASS` — non-root, loopback-safe `api/server.py:131`, `ZCODER_OTEL_ENDPOINT` bootstrap behind env.

### 4. Observability
- `/health/live` + `/health/ready` shipped (`#94`)
- OTel `bootstrap_from_env` wired in `worker` + 2 CLI mains behind `ZCODER_OTEL_ENDPOINT` (`#95`)
- `docs/observability/dashboard.json` validated

## Non-functional gates
- Coverage: `tool.coverage.report:fail_under = 70` enforced
- Supply-chain: `uv.lock` reproducible, `requirements.txt` mirrors `pyproject.toml`, SBOM via `publish-container.yml`
- Architecture: `src/zcoder` import cycle `service→infrastructure` fixed, domain direction guarded

## Closure statement
Production execution is **closed** on `2ec89ce`. Any code/config/dependency change invalidates this evidence per `exec-planning.md:12` and requires re-verification via `scripts/release-candidate.mjs`.
