# Evidence 001 — src-layout canonical

**Claim:** Repository is fully `src/zcoder` canonical; 104 transitional flat modules + shim deleted; all imports `zcoder.*`.

**Reproduction:**
```
git diff --stat 46ad61d7..2a8adcf | grep -E "flat|shim"
# 104 deletions
grep -r "from zcoder\." src --include="*.py" | wc -l  # >300
grep -r "import zcoder" src --include="*.py" | head
ls src/*.py 2>&1  # ls: cannot access 'src/*.py' — no flat modules
cat pyproject.toml | grep -A2 "\[tool.setuptools.packages.find\]"
# where = ["src"], include = ["zcoder*"]
```

**Hosted verification:**
- `2ec89ce` lint `ruff` + `black` green (target `py310`)
- `src/zcoder/core/health.py:70` import `zcoder.core.security.safe_resolve` via canonical path — no cycle
- Architecture test `tests/unit/test_arch_domain_direction.py` green

**Rollback:** `git checkout 46ad61d7 -- src/*.py` restores flat layout (invalidates evidence).
