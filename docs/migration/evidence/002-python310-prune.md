# Evidence 002 — Python 3.10 prune

**Claim:** `requires-python` is `>=3.10` and `uv.lock` no longer carries `python_full_version < '3.10'` markers.

**Reproduction:**
```
grep requires-python pyproject.toml  # >=3.10
grep target-version pyproject.toml  # py310 (ruff:91, black:113)
grep python_version pyproject.toml  # 3.10 (mypy:116)
grep -c "python_full_version < '3.10'" uv.lock  # 0 (was >40 before 2ec89ce)
grep -c 'version = "0.49.3"' uv.lock  # 0 (starlette py39 pin dropped)
grep -c 'version = "1.6.0"' uv.lock  # starlette py310 only
cat .github/workflows/ci.yml | grep python-version  # ["3.10","3.11","3.12"]
```

**Hosted verification:**
- `uv lock --upgrade-package starlette --upgrade-package uvicorn` on `2ec89ce` regenerates without `<3.10` markers
- CI matrix `3.10/3.11/3.12` green (3.9 removed) — run `32583958xxx` lineage
- `src/zcoder/core/health.py:70` `sys.version_info >= (3,10)` `ok`

**Rationale:** `pytest 9.1.1`, `black 26.5.1`, `starlette 1.6.0`, `python-dotenv 1.2.3` all `Requires: Python >=3.10` per PyPI; retaining 3.9 broke `CI / test (3.9)` with `pip install` failures.

**Rollback:** `pyproject.toml:10` `>=3.10 -> >=3.9` + `uv lock` regenerates dual markers (re-introduces 3.9 failures).
