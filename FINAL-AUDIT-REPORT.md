# ZCoder Enterprise Audit — Final Report

> **Latest checkpoint — 2026-11-09 (universal remediation round):** all
> remaining CodeQL findings remediated and locally re-verified at 0 (39 → 0,
> suite `python-security-and-quality`); the `Security Scan` CI workflow was
> repaired (previously failed at 0s on every run — invalid `uses:` step);
> gitleaks configuration rebuilt and full-history scan clean; full test suite
> passes with local PostgreSQL. Current authoritative reports:
> `docs/audit/FINAL-REPORT.md`, `docs/audit/SECURITY-REPORT.md`,
> `docs/audit/CODEQL-REMEDIATION.md`.

**Repository:** https://github.com/cvsz/zcoder (local: /home/cvsz/zcoder)
**Remote:** git@github.com:cvsz/zcoder.git (verified `cvsz/zcoder`)
**Report date:** Sun Nov 08 2026
**Policy:** Canonical zeaz.md + repository AGENTS.md (read before any change)

---

## 1. Repository and Baseline SHA

| Item | Value |
|---|---|
| Working tree | Clean before editing (no dirty/untracked user work) |
| Local branch | `codex/zcoder-full-audit-remediation-20261108-secfix` |
| origin/main SHA | `6ebbca53d64b1af6c36525a1539c3b77fdd7de7a` |
| HEAD before change | `6ce371d` (GPG-signed) |
| HEAD after change | `c8ba01751bd32b07a26a88dc7cc034061515b37a` (GPG-signed) |
| Git remote verified | Yes — `origin` = cvsz/zcoder |
| Python | 3.14.4 (project targets >=3.12) |

No pre-existing unrelated user modifications were touched. Only `tests/unit/test_cloudflare_rss_monitor.py` was changed (67 insertions).

---

## 2. Architecture Reviewed

Verified from source:
- `src/zcoder/` — domain, application, infrastructure, interfaces, agent, API, worker, services, enterprise, config, core
- CLI/TUI entrypoint `main.py` (src-layout compatibility launcher) + Click/Typer-style commands
- FastAPI web API (`zcoder.api.server`), Web uvicorn console (`webapp.backend.server`)
- zgpu GPU subsystem (packaged, dashboard assets excluded from tests)
- SQLite default / PostgreSQL (`zcoder_db`, role `zcoder`) via `scripts/local_postgres.py`
- Worker process + outbox + lease/fencing
- Local AI inference adapters (llama.cpp/Ollama/vLLM/OpenAI-compatible, loopback)
- TypeScript SDK `zcoder-sdk.ts`
- Dockerfile + docker-compose.yml

No circular-import or boundary violations surfaced by mypy/ruff. Public interfaces preserved.

---

## 3. PR Inventory — PR #177 (the live PR under this session)

PR #177 is the active PR and corresponds exactly to this branch.

| Field | Value |
|---|---|
| Number | 177 |
| URL | https://github.com/cvsz/zcoder/pull/177 |
| Title | fix: prevent feed URL redirect scheme escape in cloudflare RSS monitor (B310) |
| State | OPEN |
| Base | main `6ebbca53...` |
| Head | `c8ba0175...` (this branch) |
| Mergeable | MERGEABLE |
| Review decision | REVIEW_REQUIRED (no reviews yet — awaits Stage B `policedbc`) |
| Author | cvsz (GPG-signed) |
| CI | All checks SUCCESS (lint, security/bandit, CodeQL, dependency review, helm, release-gate, reproducibility, SDK, docker-build, tests 3.12/3.13) |

I did not retrieve the full paginated inventory of every historical PR in this session; prior audit documentation already exists under `docs/audit/` (PR-INVENTORY.md, all-pr-disposition.md, etc.) from earlier sessions. This session's verifiable work is scoped to PR #177's F-01 remediation.

---

## 4. PR #177 Security Fix — Independent Verification (F-01 / Bandit B310)

`scripts/cloudflare_rss_monitor.fetch_feed`:

- **Initial URL parsing:** `urlparse(url)`; scheme must be `https`, else return `None` + warn (before any network call).
- **Scheme validation:** Non-https schemes (http, ftp, file, empty, malformed) rejected up front.
- **Redirect handling:** `urlopen` follows HTTP redirects; the fix re-validates the **final** URL.
- **Final response URL validation:** `resp.geturl()` parsed; if scheme != `https`, return `None` + warn, **before** `resp.read()`.
- **Validation before reading bytes:** Confirmed by test — `read()` is not invoked when the final URL leaves https.
- **Unsupported schemes rejected:** ftp:// and file:// final URLs rejected.
- **HTTP redirects do not bypass HTTPS:** https→http rejected.
- **file:// redirects cannot access local files:** https→file:// rejected.
- **ftp:// cannot bypass policy:** https→ftp:// rejected (new test).
- **Malformed URL:** scheme-less/empty initial URLs rejected by the up-front scheme check.
- **Redirect loops / network errors / timeouts:** caught by `except (URLError, HTTPError, ET.ParseError, OSError)`, return `None`, no crash, no secret leakage in warnings.
- **Response resource cleanup:** `with urlopen(...) as resp` context manager.
- **Exception handling:** network/parse errors logged as warnings (no secrets), return `None`.
- **XXE:** `defusedxml.ElementTree` used for parsing.

**Fix verdict:** VERIFIED CORRECT. The fix matches the PR description and is covered by tests.

---

## 5. Regression Tests Added (PR #177 / F-01)

Added 6 deterministic local tests (no live URLs) to `tests/unit/test_cloudflare_rss_monitor.py`:

1. `test_fetch_feed_rejects_https_to_ftp_redirect` — https→ftp:// rejected; read() not called
2. `test_fetch_feed_rejects_initial_non_https_schemes` — http/ftp/file/empty/malformed rejected up front
3. `test_fetch_feed_read_only_after_https_validation` — read() not invoked on scheme escape
4. `test_fetch_feed_network_error_is_handled` — URLError → None
5. `test_fetch_feed_timeout_is_handled` — TimeoutError → None
6. `test_fetch_feed_redirect_loop_is_handled` — redirect-exhaustion URLError → None

Pre-existing 3 tests retained (https→http, https→file://, https passthrough). **Total: 9 tests, all passing.**

---

## 6. Validation Executed — Exact Results

| Gate | Command | Result |
|---|---|---|
| Lint | `python -m ruff check .` | PASS (exit 0) |
| Format | `python -m black --check .` | PASS (501 files unchanged) |
| Types | `python -m mypy src/zcoder webapp --ignore-missing-imports` | PASS (no issues, 197 files) |
| Security | `python -m bandit -r src/zcoder webapp scripts -ll` | PASS (exit 0; High 0 at -ll) |
| Unit | `python -m pytest tests/unit` | 1678 passed (36.96s) |
| Integration (PG) | `python scripts/local_postgres.py run -- pytest tests/integration` | PASS |
| E2E (PG) | `python scripts/local_postgres.py run -- pytest tests/e2e` | 130 passed |
| Full suite + coverage | `local_postgres.py run -- pytest --cov` | 1900 passed, **78% coverage** (threshold 70) |
| Import | `python -c "import zcoder; print(zcoder.__version__)"` | works (see note below) |
| CLI | `python main.py --help / --version / --health-check` | supported flags present |
| Docker Compose | `docker compose config --quiet` | PASS (exit 0) |
| GPG commit | `git verify-commit HEAD` | Good signature, cvsz signing key |
| GH identity | `gh api user --jq .login` | `cvsz` (active) |

Coverage note: run without the PostgreSQL helper showed 74%; with the helper (all PG-backed tests running) it is **78%**, above the `fail_under = 70` threshold. Coverage threshold was NOT lowered.

---

## 7. Identity & Signing Evidence (Stage A — cvsz)

- `gh auth status`: logged in to github.com as **cvsz** (active), token scopes include repo/workflow/admin.
- `gh api user --jq .login` → `cvsz`. Identity verified.
- GPG secret keys present; `user.signingkey` = `515DB3BD9BF14AA6646AC6770C54E869DE49D872` → `cvsz (zcoder signing) <seaza@msn.com>`; `commit.gpgsign = true`.
- All commits on the branch (`dcdf1df`, `dfef42c`, `6ce371d`, `c8ba017`) verify: `git verify-commit HEAD` → Good signature from cvsz signing key.
- `.git-credentials` was NOT read, printed, or copied (per policy).

---

## 8. Branch / PR Status

- `git push -u origin HEAD` succeeded → branch now at `c8ba017` on origin.
- PR #177 head updated to `c8ba017`; mergeable MERGEABLE; state OPEN.
- **NOT merged.** Stage B (independent `policedbc` review) and Stage C (cvsz guarded merge) remain pending. Per policy I do not self-approve or self-merge.

---

## 9. Blocked / Not-Available Gates (honest, not faked)

| Gate | Status | Reason |
|---|---|---|
| `gitleaks detect` | BLOCKED | `gitleaks` binary not installed in this environment |
| `actionlint` | BLOCKED | `actionlint` binary not installed |
| pip-audit | NOT RUN in this session | available but not re-run here; dependency-review CI check passed on PR |
| Windows Authenticode / installer | BLOCKED | Linux host; no Windows tooling/pwsh. `make cert-generate/sign/verify` are no-op notes on this platform |
| Independent Stage B review (policedbc) | BLOCKED | Must be performed by the `policedbc` identity; I am cvsz and must not self-approve |
| Merge (Stage C) | BLOCKED | Pending Stage B approval + required checks |

Per policy: a missing tool/service is BLOCKED, never PASS. No credential or secret was introduced.

---

## 10. Findings & Notes

**Version discrepancy (environment artifact, not a source defect):** `pyproject.toml` and README declare version `1.60.0`, but the currently installed editable dist metadata reports `1.41.5` (`importlib.metadata.version("zcoder")`). The source `src/zcoder.egg-info/PKG-INFO` says `1.60.0`. This is a stale editable-install metadata artifact; no code change required. Reinstalling the editable package would align the reported version. Documented as residual note — not a P0/P1.

No P0/P1 security findings were introduced or left unverified in the PR #177 scope. The F-01 B310 fix is verified and tested.

---

## 11. Fixes Implemented

One fix, in PR #177 branch:
- `tests/unit/test_cloudflare_rss_monitor.py`: added 6 deterministic regression tests for redirect-scheme hardening (ftp://, malformed/non-https initial URL, read-before-validation, network error, timeout, redirect loop). No source change was needed — the source fix (`dcdf1df`) was already correct and verified.

---

## 12. Remaining Risks

- PR #177 requires independent Stage B review by `policedbc` before merge (REVIEW_REQUIRED).
- `gitleaks` and `actionlint` could not be executed (tools absent); supply-chain/secret-scan evidence for this change rests on CI bandit/dependency-review which passed.
- Version metadata mismatch between installed dist (`1.41.5`) and source (`1.60.0`).
- No production deployment, release tag, or package publish was performed (not authorized).

---

## 13. Final Verdict

**PASS_WITH_RESIDUAL_RISKS** for the implementation/validation work:
- All executable checks (ruff, black, mypy, bandit, unit/integration/e2e, coverage, docker compose, GPG, identity) PASS.
- PR #177 F-01 security fix verified and regression-tested; CI green; mergeable.

**Overall release readiness is BLOCKED** pending:
1. Independent Stage B review and approval by `policedbc` on PR #177 (exact head `c8ba017`).
2. Installation/execution of `gitleaks` and `actionlint` (or equivalent) to complete supply-chain scanning.
3. Stage C cvsz guarded merge after approval + required checks.

No merge, release, or publish was performed. The branch is preserved and reviewable at `c8ba017`.
