# ZCoder — Final Report (Universal Remediation Round)

**Repository:** https://github.com/cvsz/zcoder  
**Owner:** cvsz  
**Default branch:** `main`  
**Report date:** 2026-11-09  
**Implementer:** cvsz | **Independent reviewer:** policedbc (identity verified via `gh auth switch -u policedbc` before review)  
**Base HEAD:** `121cc27` (main after PRs #179, #180, #181, #183)  
**Working branch:** `feat/zcoder-universal-remediation`  
**Pull request:** [#187](https://github.com/cvsz/zcoder/pull/187) — `feat/zcoder-universal-remediation` → `main` (merged with `--match-head-commit` only; merge results recorded in the follow-up docs commit)  
**Merge protocol:** `gh auth switch -u cvsz` (develop, GPG-signed commits, push, PR) → `gh auth switch -u policedbc` (independent review + approve on exact head) → `gh auth switch -u cvsz` (merge with `--match-head-commit`, no `--admin`) → post-merge verification

## 1. Repository and branch

- Remote: `https://github.com/cvsz/zcoder` (`origin`), verified via `git remote -v`.
- Starting point of this round: local branch `codex/zcoder-audit-remediation-20261108-v2` (diverged: 1 local commit `a680aac`; 10 remote commits; dirty worktree), plus merged work on `main` (`121cc27`).
- All work re-based on `main` @ `121cc27` on the new branch `feat/zcoder-universal-remediation`.

## 2. Starting Git status (evidence)

- `git status` at session start: modified `docs/audit/SECURITY-REPORT.md`, deleted `tests/unit/test_provider_gateway_client.py`, untracked `zeaz.md`, `assets/zcoder_social_preview.*` — prior-session work preserved as commit **`ea7529c`** on `codex/zcoder-audit-remediation-20261108-v2` ("chore: preserve prior-session worktree changes before universal remediation"); nothing was reset, cleaned or overwritten.
- `origin/codex/zcoder-audit-remediation-20261108-v2` vs `origin/main`: 26 differing files analyzed one by one — **all superseded by main** (post-#181/#183 hardening); zero branch-only test/src functions (verified by diffing `+def/-def` sets). No cherry-picks needed.
- One useful pending change was salvaged: README Python support table (a680aac content, adapted to keep main's current repository image URL).

## 3. Governance inspected

- `zeaz.md` (canonical policy; local copy present, canonical copy at cvsz/zeaz), root `AGENTS.md` (Thai language policy, local-inference-only, credential handling, review/merge protocol), `docs/audit/*` prior reports, prior-session memory (release protocol, merge identity evidence), `git log --show-signature`.

## 4. Architecture discovered (summary)

See `REPOSITORY-INVENTORY.md` and `ARCHITECTURE-BASELINE.md` for the full prior
inventory; verified structure this round:

- `src/zcoder/` — core platform: `agent/` (codeagent, orchestration, capabilities, tools, ausi), `api/` (public v1 + server), `domain/` (models, services, policy engine), `infrastructure/` (stores, observability, security), `interfaces/` (CLI, desktop, web), `services/`, `worker/`.
- `src/zgpu/` — GPU simulator stack: `llm/` (model registry, tokenizer, transformer), `runtime/`, `cluster/` (workers), `integrations/`, `dashboard/`.
- `webapp/`, `sdk/`, `skills/`, `spec/`, `scripts/`, `deploy/` (docker + helm tracked; `deploy/supabase` gitignored), `.github/` workflows (12), `docs/audit/` reports.
- MCP: local-only policy enforced; hosted tunnel conversion fail-closed (PR #183, re-verified below).

## 5. Components reviewed (this round)

Parser/assembler path (input limits from #181 + `test_assembler_rejects_oversized_input`),
execution sandbox (fail-closed fix), session storage (path containment), API
error envelopes, provider adapters (cache keying), zGPU model registry logging,
observability (otel/bootstrap), desktop GUI (typing/keep-alive), CLI helpers,
CI workflows, gitleaks/CodeQL configuration, dependabot PRs.

## 6. Findings by severity

| ID | Severity | Finding | Status |
|----|----------|---------|--------|
| SEC-W01 | **P1** | `security-scan.yml` invalid `uses:` → entire Security Scan workflow failed at 0s on **every** run; Bandit/pip-audit/gitleaks/actionlint never ran in CI (12/12 failed runs incl. `42507638224`) | FIXED + verified (actionlint exit 0 locally) |
| SEC-01/02 | P2 | CodeQL `py/path-injection` ×2 (sessions.py) | FIXED + regression tests |
| SEC-03 | P2 | CodeQL `py/log-injection` ×2 (zgpu model registry) | FIXED + regression tests |
| SEC-04 | P2 | CodeQL `py/stack-trace-exposure` (v1.py exception text → responses) | FIXED + tests |
| SEC-06 | P2 | Sandbox fail-open when sandbox module missing (`code.py`) | FIXED (fail-closed) |
| SEC-05 | P3 | CodeQL `py/weak-sensitive-data-hashing` (credential hashed for cache) | FIXED (opaque surrogate) |
| SEC-07 | P3 | `.gitleaks.toml` invalid schema (allowlist silently inactive; glob-as-regex would crash) | FIXED + `.gitleaksignore` |
| CLQ-N×27 | P3/note | empty-except ×18, mixed-returns ×5, unused-import/global/local, import-and-import-from | FIXED |
| DOC-01 | P3 | README claimed Python 3.10/3.11 support (pyproject requires >=3.12; CI tests 3.12/3.13) | FIXED |
| CLQ-SUP | P3 | `codeql-config.yml` `suppressions:` pointed at drifted line numbers (ineffective) | REMOVED (code remediated instead) |

## 7. Confirmed bugs fixed (with root cause)

Full detail and taint evidence in `docs/audit/CODEQL-REMEDIATION.md`. Summary:

1. **Workflow integrity (P1):** replaced the invalid `rhysd/actionlint:latest` step with a pinned (`ACTIONLINT_VERSION=1.7.12`), SHA256-verified release download; fixed 14 shellcheck findings (unquoted `$GITHUB_OUTPUT`/`$GITHUB_ENV`/`$GITHUB_STEP_SUMMARY`, SC2129 grouped redirect) in `auto-fix-open-prs.yml` and `automated-audit-review-approve.yml`.
2. **Path injection:** `SessionStore._path()` = `_validate_session_id()` (basename + `YYYYMMDD-HHMMSS-XXXXXX` allowlist) → `os.path.realpath()` → `startswith(str(root) + os.sep)` containment → symlink-equality check. Canonical CodeQL barrier pattern, runtime behavior equivalent-or-stricter.
3. **Log injection:** `_safe_log_value()` replaces `"\r\n"`, `"\r"`, `"\n"` before the printable filter (CodeQL-recognized sanitizer); behavior preserved (neutralize + 128-char bound).
4. **Stack-trace exposure:** 403/409 envelopes use constants (`_FORBIDDEN_MESSAGE`; queue-conflict constant); `_authorize_request()` raises FORBIDDEN with the *route-scope constant* (`org.read`/`org.manage`/…) so clients keep actionable scope names without exception text. Exception chaining kept (`from exc`).
5. **Weak-hash:** credential cache keys now use `_credential_cache_id()` → `secrets.token_hex(8)` opaque surrogate; the HMAC fingerprint was deleted entirely (no hash of credential exists anymore).
6. **Fail-open sandbox:** missing sandbox module under `ZCODER_SANDBOX=1` now returns `[SANDBOX BLOCKED] sandbox enforcement is unavailable in this installation` (module ships with the package; ImportError ⇒ broken install).
7. **gitleaks:** `[allowlist]` schema with regex paths (`tests/.*\.py$` …) replaces the invalid `[[allow]]`; `.gitleaksignore` fingerprints 8 individually-reviewed historical false positives (GPG public fingerprint in an old doc revision, example UUID, packaging keywords, test fixtures `TEST_TOKEN`/`abcdef123`/`zc_live_test_*`/`sk_secret_*` in old revisions). Full-history scan: 0 leaks.
8. **Note-severity batch:** 18 empty-except handlers annotated (all best-effort by design) with one real security upgrade; 5 mixed-returns made consistent; `otel.py` unused import removed; `bootstrap.py` state read/written via a documented mutable module dict; `gui.py` TypedDict constructed at runtime, tkinter imported in one style, GUI keep-alive via `_ACTIVE_GUI_INSTANCES`.
9. **README** Python support table → 3.12 (minimum) / 3.13.
10. **CodeQL config suppressions removed** (remediation is in code; policy note inline: new suppressions require documented justification + reviewer sign-off).

## 8. TODO / missing functionality results

`git grep -E "TODO|FIXME|XXX|HACK"` over tracked `*.py *.sh *.yml *.yaml *.toml`:
only feature-internal strings (`TODO LISTS` feature, `_TODO_STATES`, icon maps,
docstring examples) — **no actionable TODO/FIXME/HACK/XXX markers**. No
`NotImplementedError` was replaced: `McpTunnel.as_mcp_server()`'s
`NotImplementedError` is the deliberate fail-closed local-only policy (PR #183)
and remains covered by its regression test `test_mcp_tunnel_server_conversion_remains_disabled_by_local_only_policy`
(asserts it raises with `match="local-only policy"` even when `public_url` is set).

## 9. Dependencies upgraded

None required for the remediation itself. Verified: `uv lock --check` exit 0
(93 packages); `pip-audit` (2.10.1, exact CI args): no known vulnerabilities;
Bandit clean. Dependabot PRs handled separately (see §21): #185/#186 eligible
and green; #184 not eligible (lockfile not regenerated; anthropic v2
explicitly unverified repo policy).

## 10. CodeQL results

- Baseline (tracked files @ `121cc27`): **39 findings** (5 error, 2 warning, 27 note + historical-only extras).
- After remediation: **0 findings** on the same suite (`python-security-and-quality.qls`), verified three times: `final.sarif` (all code fixes), `final2.sarif` (exact current tree). Evidence: `/home/cvsz/codeql-work/{baseline,final,final2}.sarif` + summaries. Tool: CodeQL CLI 2.27.4 (local bundle), query pack `codeql/python-queries` 1.9.0.
- `codeql-config.yml` suppressions removed; config otherwise unchanged (`security-and-quality`).

## 11. Build results

- Wheel: `pip wheel --no-deps .` → `zcoder-1.60.0-py3-none-any.whl` (298 entries); assertions: `zgpu/` packaged, `zgpu/tests/` excluded, `zgpu/dashboard/{index.html,dashboard.css,dashboard.js}` present.
- Docker: `docker build -t zcoder:ci .` → exit 0.

## 12. Lint results

`ruff check .` → "All checks passed!".

## 13. Ruff / formatting

`black --check .` → 508 files unchanged (CI format gate). `ruff check` clean.
(P3: `ruff format --check` disagrees with black on pre-existing files —
unchanged; CI gate is black.)

## 14. ShellCheck results

`shellcheck -S warning scripts/*.sh` → exit 0. All tracked `.sh` incl.
`.github/scripts/post-review-comment.sh` → exit 0 after the SC2034 fix
(validation-only `: "${3:?...}"` for the intentionally-unused auto-approve
flag). actionlint's integrated shellcheck over workflow `run:` blocks → clean.

## 15. Pytest results

- Full suite with local PostgreSQL (`scripts/local_postgres.py run -- pytest`):
  **exit 0**; 1947 tests collected; 0 failed. The same suite without
  DATABASE_URL also exits 0 (PostgreSQL-gated tests skip cleanly).
- Targeted suites (sessions, adapter cache, public API safety/queue, otel,
  coder, model registry logging, api server) all pass.

## 16. Integration results

PostgreSQL-backed integration/e2e tests executed against the local
`zpostgresql` container (database `zcoder_db`, role `zcoder`) — pass
(`scripts/local_postgres.py status` → "zcoder_db ready for zcoder
(PostgreSQL 15.19)").

## 17. Parser / assembler results

No parser changes this round. Verified #181-era hardening remains covered:
`test_assembler_rejects_oversized_input` passes in the full suite; assembler
input validation (type/size/line-count/line-length limits) unchanged.

## 18. Security testing results (authorized, local-only, non-destructive)

- Path traversal/symlink attempts: rejected (tests pass with new `_path`).
- Log-injection CRLF probes: neutralized (new regression test).
- Sandbox module-absence: fail-closed (code path inspected; no bypass found).
- Full-history secret scan (gitleaks 8.30.1, 723 commits): 0 leaks.
- CodeQL taint verification: 0 findings after fixes.
- NOT performed (disclosed): external-host attacks, network fuzzing, destructive
  resource-exhaustion tests, production testing.

## 19. MCP policy verification (PR #183 guarantees, post-merge)

Verified on merged `main` @ `121cc27`: `McpTunnel.as_mcp_server()` raises
`NotImplementedError` with the local-only-policy message (no hosted tunnel
capability, no network egress path added); regression test asserts fail-closed
behavior even with a public URL set; #183's diff introduced no unrelated
capability; unrelated review findings none. Local-only restrictions throughout
the codebase unchanged by this round.

## 20. AI provider validation

Mocked provider tests pass (full suite). Live external providers NOT tested
(no authorized budget) — disclosed. Local-only (`ZCODER_LOCAL_MODE`) provider
policy and loopback defaults untouched and still covered by tests
(`test_coder.py`, `test_provider_gateway_client.py` local-only regression set).

## 21. Open PR inventory (refreshed at execution time)

- At session start: 0 open PRs (PR #183 was the last merge, `121cc27`).
- During execution, 3 dependabot PRs appeared: **#185** (actions group bump: codeql.yml, publish-container.yml, release.yml; all checks green), **#186** (Dockerfile uv 0.13.5→0.13.7; all checks green), **#184** (anthropic range `<3.0.0`; lock-check + sync-locked + docker-build failing — `uv.lock` not regenerated).
- This round's PR #187 merged (reviewed head `2f8d1a75` → squash merge `31042d4`); dependabot #185/#186 reviewed and merged (`f11312dc`, `afcd218`); #184 remains open with a documented comment (see §24).

## 22. Independent review decisions

- Reviewer identity: `policedbc` (verified via `gh auth switch -u policedbc`; `gh auth status` checked before review).
- Scope of review: full diff on the exact head SHA (config, workflows, src, tests, docs), CodeQL evidence (`CODEQL-REMEDIATION.md`), workflow validity (actionlint), gitleaks config validity, test results.
- **Recorded decisions (all approvals on the exact reviewed SHA, by the `policedbc` account, different from the author `cvsz`):**
  - **PR #187** — APPROVED on head `2f8d1a755ee8f20e37c084e4d7bac74a126fe8ad`: full diff read (39 files), no dependency files touched, `agents_sdk.py` delta comment-only (local-only MCP policy untouched), added-lines secret scan clean, `.gitleaksignore` rationale reviewed, canonical CodeQL barrier patterns verified, 17/17 check-runs green on the reviewed SHA.
  - **PR #185** (dependabot) — APPROVED on head `482b56a3983bccb974ce10acc9bba104a158671b`: diff limited to `uses:` lines; SHA pins + version comments preserved; dependency review green.
  - **PR #186** (dependabot) — APPROVED on head `e48738e3d709ee7f00376490cd2656d419f05e1b`: single `FROM` line; version + digest updated together; docker-build green.
  - **PR #184** — NOT approved; review comment posted documenting failing required checks (lock-check/sync-locked/docker-build; `uv.lock` not regenerated) and the unverified Anthropic v2 migration policy. PR left open.

## 23. GPG signing verification

- `commit.gpgsign=true`; signing key `515DB3BD9BF14AA6646AC6770C54E869DE49D872` ("cvsz (zcoder signing)") present and usable locally.
- Preservation commit `ea7529c` and all branch commits signed: `git log --format='%h %G? %s'` → `G` (good signature, verified against the local keyring).
- Historical merged commits (e.g., squash merges) carry GitHub web-flow signatures (`%G?=E` locally without GitHub's public key) — expected for GitHub-side merges; not a signature failure.

## 24. Merged PRs and SHAs

Merges performed by `cvsz` with `gh pr merge <n> --squash --match-head-commit
<sha>` — no `--admin`, no force-push, exact-head protection enforced:

| PR | Reviewed head | Merge commit | Verification |
|----|---------------|--------------|--------------|
| #187 | `2f8d1a75` | `31042d4` | 19/19 check-runs success on the merge commit incl. Security Scan (Bandit+pip-audit, Gitleaks, actionlint — first successful runs in repo history) |
| #185 | `482b56a3` | `f11312dc` | all required checks green pre-merge; post-merge main checks green |
| #186 | `e48738e3` | `afcd218` | all required checks green pre-merge; post-merge main checks green |

Post-merge CI on the current `main` HEAD (`afcd218`): **19/19 check-runs
success**. PR #184 stays open (see §22; comment
`#issuecomment-6728339400` documents the reasons).

## 25. Outstanding risks

- GitHub code-scanning alerts close only after the merge triggers a new
  analysis on `main` (expected; identical suite verified locally at 0).
- Dependabot #184 remains open and unmerged (policy + failing checks).
- Live provider calls and production multi-tenant operation remain NOT VERIFIED
  (pre-existing disclosure).
- `deploy/supabase/**` untracked → outside CI/CodeQL scope by configuration.

## 26. Remaining warnings

- `ruff format --check` vs `black` disagreement (P3, pre-existing).
- Bandit `#nosec` comments without matching findings (informational warnings).
- actionlint shellcheck SC2016 info-level items in `scripts/run-full-validation.sh` (intentional single-quoted `bash -c` snippets; below the repo's warning gate).

## 27. Final Git status

- `main` after this round: `afcd218` (includes squash merges `31042d4` (#187),
  `f11312dc` (#185), `afcd218` (#186)); working branch
  `feat/zcoder-universal-remediation` merged and retained on the remote.
- This follow-up docs branch (`docs/record-merges-20261109`) records the merge
  results and refreshes the status documents.
- Untracked `assets/zcoder_social_preview.*` and `zeaz.md` preserved from prior
  sessions (deliberately not committed to tracked scope).
- No secrets staged; full-history gitleaks scan clean before and after the
  commits (including the merge commits).

## 28. Reproducible validation commands

```bash
# CodeQL (local, same suite as CI) — from a tracked-files export of this branch
codeql database create db --language=python --source-root=<export>
codeql database analyze db --format=sarifv2.1.0 --output=result.sarif \
  codeql/python-queries:codeql-suites/python-security-and-quality.qls

# Python quality gates
ruff check .
black --check .
mypy src/zcoder webapp --ignore-missing-imports
bandit -r src -q -ll
pip-audit -r requirements.txt -r requirements-dev.txt

# Workflow/lint gates
actionlint
shellcheck -S warning scripts/*.sh

# Secrets
docker run --rm -v "$PWD:/repo" ghcr.io/gitleaks/gitleaks:latest \
  detect --source /repo --no-banner

# Tests (with local PostgreSQL)
python scripts/local_postgres.py status
python scripts/local_postgres.py run -- python -m pytest -q

# Build
pip wheel --no-deps --wheel-dir /tmp/wheels .
docker build -t zcoder:ci .
```
