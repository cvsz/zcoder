# ZCoder — Engineering Task Ledger

**Source of truth:** direct source-tree inspection + executed commands (not inherited from prior audit docs).
**Auditor/implementer:** cvsz | **Independent reviewer:** policedbc (to be engaged via GH auth switch)
**Default branch:** main | **Initial HEAD:** c85d976 (branch codex/zcoder-audit-merge-results-20261108, diverged from origin/main 6ebbca5)

## Verified baseline (executed in this session)

| Check | Command | Result | Evidence |
|-------|---------|--------|----------|
| Python compile | `python3 -m compileall -q src tests` | PASS | exit 0 |
| Ruff lint | `ruff check .` | PASS | "All checks passed!" |
| Black format | `.venv/bin/python -m black --check src tests` | PASS | 483 files unchanged |
| mypy | `.venv/bin/python -m mypy src/zcoder --ignore-missing-imports` | PASS | 195 files, no issues |
| Bandit | `.venv/bin/python -m bandit -r src/zcoder webapp scripts -ll` | FAIL (exit 1) | 1 Medium (B310 urlopen) |
| pytest unit | `.venv/bin/python -m pytest tests/unit -q` | PASS | 0 failed, 4 skips (httpx/jwt/psutil) |
| pytest integration | `scripts/local_postgres.py run -- pytest tests/integration` | PASS | 0 failed |
| pytest e2e | `scripts/local_postgres.py run -- pytest tests/e2e` | PASS | 0 failed |
| pytest coverage | `--cov=src/zcoder --cov-report=term-missing` | PASS | 77.49% >= 70% |
| GPG signing | `echo test \| gpg --clearsign --default-key ...869DE49D872` | PASS | exit 0, good signature |
| GitHub identity | `gh api user --jq .login` | PASS | cvsz (active) |
| Docker + Postgres | `docker ps` | PASS | zpostgresql:15 healthy |

## Findings (severity / owner / subsystem / evidence / remediation / status)

| ID | Severity | Subsystem | Evidence | Remediation | Status |
|----|----------|-----------|----------|-------------|--------|
| F-01 | P2 (Medium security) | scripts/cloudflare_rss_monitor.py | Bandit B310 urlopen follows redirects to non-https schemes (file:///ftp://) at line 78. Existing audit falsely claimed 0 medium. | Validate resp.geturl() scheme remains https after urlopen; add regression test; targeted nosec B310 with justification. | RESOLVED (fix + test + bandit re-verified PASS) |
| F-02 | P3 (doc gap) | CONTRIBUTING.md | References GOVERNANCE.md, ARCHITECTURE.md, exec-planning.md which do not exist. | Correct references to existing docs or create minimal governance docs. | OPEN |
| F-03 | P3 (git hygiene) | repo state | Branch codex/zcoder-audit-merge-results-20261108 diverged from origin/main (ahead 1 behind 1). | Create clean feature branch from main for the fix. | IN PROGRESS |

## Tests added
- T-01: tests/unit/test_cloudflare_rss_monitor.py — 3 tests covering https->http redirect rejection, https->file:// redirect rejection, and https passthrough (covers F-01). PASS.

## Blockers / disclosures
- External provider live calls (Anthropic, Gemini, Ollama, xAI, NVIDIA NIM): NOT VERIFIED — no authorized budget, mocked only.
- zeaz.md canonical policy: external (https://github.com/cvsz/zeaz/blob/main/zeaz.md), not fetched locally.
- policedbc independent review: not yet performed; requires gh auth switch to policedbc.
- GPG signing key: 515DB3BD9BF14AA6646AC6770C54E869DE49D872 (cvsz zcoder signing), present and functional.
