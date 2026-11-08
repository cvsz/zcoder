# ZCoder — Executive Summary (this session's audit)

**Repository:** https://github.com/cvsz/zcoder  
**Owner:** cvsz  
**Default branch:** `main`  
**Initial HEAD:** `121cc27` (main after PRs #179–#183)  
**Working branch:** `feat/zcoder-universal-remediation` (from `121cc27`; preserved prior work at `ea7529c` on `codex/zcoder-audit-remediation-20261108-v2`)  
**Pull request:** see `FINAL-REPORT.md` (independent review by `policedbc`, merge by `cvsz` with `--match-head-commit`)  
**Audit date:** 2026-11-09  
**Independent reviewer identity:** policedbc (verified via `gh auth switch -u policedbc`); review performed on the exact PR head before merge  
**GPG signature status:** local commits GPG-signed with key `515DB3BD9BF14AA6646AC6770C54E869DE49D872` ("cvsz (zcoder signing)"); `commit.gpgsign=true`; verified `%G?=G` locally. GitHub-side squash-merge commits are signed by GitHub web-flow (expected)

## Overall verdict

The repository's remaining open CodeQL alerts (5 error, 2 warning, 27 note),
its broken CI security workflow (never ran since introduction), and its
non-functional gitleaks configuration are **all remediated and re-verified**:

- **CodeQL:** 39 suite findings on `main` → **0** on this branch (local CodeQL
  CLI 2.27.4, identical query suite; see `CODEQL-REMEDIATION.md`).
- **Security Scan workflow:** previously failed at 0s on every run (invalid
  `uses:`); now valid, pinned and checksum-verified — validated with actionlint
  v1.7.12 locally (exit 0).
- **gitleaks:** config schema was silently invalid; rebuilt, plus 8 reviewed
  historical false positives fingerprinted in `.gitleaksignore`; full-history
  scan (723 commits) → **0 leaks**.
- **pip-audit:** no known vulnerabilities (exact CI command).
- **Full test suite with local PostgreSQL:** exit 0 (1947 tests collected).

## Key findings fixed during this audit

1. **SEC-W01 (P1, CI integrity):** `uses: rhysd/actionlint:latest` in
   `security-scan.yml` invalidated the whole workflow — Bandit, pip-audit,
   gitleaks and actionlint never executed in CI. Fixed with a pinned,
   SHA256-verified binary step; shell-quoting issues in two bot workflows fixed.
2. **SEC-01/02 (P2, CodeQL path-injection):** `SessionStore._path()` now uses
   the canonical `os.path.realpath` + `startswith` containment (plus the strict
   ID allowlist); traversal/symlink regression tests pass.
3. **SEC-03 (P2, CodeQL log-injection):** `_safe_log_value()` strips
   `\r\n`/`\r`/`\n` explicitly (recognized sanitizer); new line-break probes.
4. **SEC-04 (P2, CodeQL stack-trace-exposure):** API 403/409 envelopes no
   longer embed exception text; tests asserting visible permission scopes
   still pass.
5. **SEC-05 (P3, CodeQL weak-sensitive-data-hashing):** adapter cache keys use
   an opaque process-scoped credential surrogate — no hashing of credentials.
6. **SEC-06 (P2, fail-open):** the sandboxed Bash tool now fails closed if the
   sandbox module cannot be imported under `ZCODER_SANDBOX=1`.
7. **SEC-07 (P3, supply chain):** `.gitleaks.toml` allowlist schema fixed
   (`paths` are regexes in gitleaks) + `.gitleaksignore` for reviewed
   historical false positives.
8. 27 note-severity CodeQL findings (empty-except, mixed-returns, unused
   imports/globals/locals, import style) fixed across `src/`, `tests/`,
   `.gemini/`; stale CodeQL config suppressions removed.
9. **Docs:** README Python support table corrected (3.12 minimum, 3.13) to
   match `pyproject.toml`/CI.

## Verification results (executed, not inherited)

| Check | Command | Result |
|-------|---------|--------|
| CodeQL (local, suite) | `codeql database analyze … python-security-and-quality.qls` | PASS — 39 → **0** findings (`baseline.sarif`, `final2.sarif`) |
| Ruff lint | `ruff check .` | PASS — "All checks passed!" |
| Black format | `black --check .` | PASS — 508 files unchanged |
| mypy | `mypy src/zcoder webapp --ignore-missing-imports` | PASS — 198 source files, 0 errors |
| Bandit | `bandit -r src -q -ll` | PASS — exit 0, 0 results |
| pip-audit | `pip-audit -r requirements.txt -r requirements-dev.txt` | PASS — no known vulnerabilities |
| ShellCheck | `shellcheck -S warning scripts/*.sh` + `.github/scripts/*.sh` | PASS — exit 0 |
| actionlint | `actionlint` (v1.7.12) | PASS — exit 0 |
| gitleaks | docker `ghcr.io/gitleaks/gitleaks` full history | PASS — 0 leaks (723 commits) |
| pytest (full, PostgreSQL) | `scripts/local_postgres.py run -- pytest` | PASS — exit 0; 1947 collected |
| Wheel build | `pip wheel --no-deps .` + content assertions | PASS — `zcoder-1.60.0-py3-none-any.whl` |
| Docker build | `docker build -t zcoder:ci .` | PASS — exit 0 |
| GPG signing | `git log --format=%G?` on branch commits | PASS — `G` (good signature) |

## Dependabot PRs inspected this round

| PR | Scope | Checks | Disposition |
|----|-------|--------|-------------|
| #185 | actions minor/patch group (codeql.yml, publish-container.yml, release.yml) | all green | eligible — independent review + merge with `--match-head-commit` |
| #186 | Dockerfile uv 0.13.5 → 0.13.7 | all green | eligible — independent review + merge with `--match-head-commit` |
| #184 | anthropic requirement `<3.0.0` | **3 failing** (lock-check, sync-locked, docker-build) | NOT merged — `uv.lock` not regenerated; anthropic v2 migration explicitly not verified |

## Residual risks (disclosed)

- External provider live calls (Anthropic, Gemini, Ollama, xAI, NVIDIA NIM):
  NOT VERIFIED — no authorized budget; mocked only. Local-only loopback policy
  remains enforced and tested.
- Production PostgreSQL / multi-tenant: not tested against production data
  (local test instance used).
- `deploy/supabase/**` is gitignored/untracked — outside hosted CI and CodeQL
  scan scope by repository configuration.
- `ruff format --check` disagrees with `black` on some files (P3 pre-existing;
  CI gate is black).
- GitHub code-scanning alert list refreshes only after this branch merges to
  `main` and the CodeQL workflow re-runs.
