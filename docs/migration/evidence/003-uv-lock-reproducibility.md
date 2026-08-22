# Evidence 003 — uv.lock reproducibility

**Claim:** `uv.lock` is reproducible and in sync with `pyproject.toml` version `1.41.0`.

**Reproduction:**
```
uv lock --check  # exit 0
grep 'version = "1.41.0"' pyproject.toml
grep 'version = "0.52.4"' uv.lock | head  # uvicorn bump from 0.52.3
diff <(uv lock --dry-run 2>&1) <(cat uv.lock)  # no diff
```

**Hosted verification:**
- `reproducibility.yml` job `32583958080` green on `316ba22` and `2ec89ce`
- `publish-container.yml` SBOM `anchore/sbom-action` green
- `release_gate.py` → `ProductionReleaseGate` lock-sync check `PASS`

**Delta from `45a91a1`:**
- `uvicorn 0.52.3 -> 0.52.4` (patch)
- Drop `pillow 11.3.0 / starlette 0.49.3 / black 25.11.0 / pytest 8.4.2 / python-dotenv 1.2.1` dual entries for `<3.10` — now single `12.3.0 / 1.6.0 / 26.5.1 / 9.1.1 / 1.2.3` for `>=3.10` (1184 lines removed, 198 added)

**Rollback:** `git checkout 45a91a1 -- uv.lock` restores dual markers (re-introduces 3.9).
