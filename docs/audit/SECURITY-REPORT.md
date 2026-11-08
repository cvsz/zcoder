# ZCoder — Security Report (Independent Audit)

**Repository:** https://github.com/cvsz/zcoder  
**Owner:** cvsz  
**Branch:** `main`  
**Initial HEAD (first audit round):** `e868ee44dea4df7ae2d7ef1cccc1151e273ee8db`  
**Current HEAD reviewed:** `121cc27` (main after PRs #179–#183)  
**Latest update:** 2026-11-09 — universal remediation round (`feat/zcoder-universal-remediation`)  
**Auditor:** cvsz  
**Scope:** Local development environment only — source review, static analysis, dependency audit, local CodeQL verification. No penetration testing against external hosts; no production testing. Loopback/local fixtures only.

## Threat model considered

- Unauthenticated internet attacker
- Authenticated low-privilege tenant / malicious tenant
- Malicious prompt/model output
- Compromised dependency
- Malicious plugin/tool / MCP server
- Compromised CI workflow
- Untrusted uploaded file
- Compromised provider
- Accidental operator misuse

## Security controls verified (independent re-check)

| Control | Surface | Status | Evidence |
|---------|---------|--------|----------|
| Path containment | `zcoder.core.security.safe_resolve()`, `read_text_prefix`, `validate_name` | VERIFIED | `realpath`-based containment, sibling-prefix rejection, binary/FIFO refusal, 25 MB size cap, NUL-byte refusal |
| Session path containment | `SessionStore._path()` | VERIFIED (remediated) | `os.path.realpath` + `startswith` guard + `_validate_session_id` allowlist; symlink/traversal regression tests pass (CodeQL `py/path-injection` closed, see `CODEQL-REMEDIATION.md`) |
| SSRF / URL scheme | `validate_url()` (HTTPS-only), outbound security review | VERIFIED | HTTPS scheme enforcement; loopback-validated fetch tools |
| Tool output trust | MCP/tool-output gating, plugin manifest provenance | VERIFIED | Tool output contained; manifest provenance validated |
| Tenant / session IDs | Session/checkpoint ID validation `[A-Za-z0-9_-]{1,64}`, `_safe_child_path()` realpath containment | VERIFIED | `src/zcoder/agent/orchestration/sessions.py` |
| API error envelopes | `api/public/v1.py`, `api/server.py` | VERIFIED (remediated) | Authorization/queue errors return constant messages; no exception text in HTTP responses; `X-Request-Id` bounded to printable ≤128 chars |
| Secrets / env inheritance | `is_secret_env_name()`, `build_child_env()` (drops credential-named vars) | VERIFIED | `src/zcoder/core/security.py`; `DATABASE_URL`, `PGPASSWORD`, `SSH_AUTH_SOCK` filtered |
| Sandboxed Bash tool | `ZCODER_SANDBOX=1` path in `agent/capabilities/code.py` | VERIFIED (remediated, fail-closed) | If the sandbox module cannot be imported, execution now returns `[SANDBOX BLOCKED]` instead of running unsandboxed |
| Authorization / approval | Fail-closed policy engine mini-parser (no `eval()`); rule-content hash | VERIFIED | `src/zcoder/domain/services/policy_engine.py` |
| Secret redaction in logs | `sk-ant-...`, `Authorization`, `x-api-key` redacted; log fields sanitized | VERIFIED | `_safe_log_value` strips CR/LF explicitly (CodeQL `py/log-injection` closed) |
| Provider adapter cache | `agent/orchestration/adapters.py` | VERIFIED (remediated) | Cache keys use an opaque per-process credential surrogate; no hash of credentials exists (CodeQL `py/weak-sensitive-data-hashing` closed) |
| Hosted MCP tunnel conversion | `agent/orchestration/agents_sdk.py` `McpTunnel.as_mcp_server()` | VERIFIED (fail-closed, PR #183) | Raises `NotImplementedError` under local-only policy even when a public URL is set; regression test `test_mcp_tunnel_server_conversion_remains_disabled_by_local_only_policy` |
| Container / supply chain | Non-root containers; pinned base images; pinned action SHAs; `uv lock --check` | VERIFIED | Dockerfile; CI workflows; `uv lock --check` exit 0 (93 packages) |
| CI least privilege | `permissions: contents: read` on CI; pinned actions; dependabot | VERIFIED | `.github/workflows/ci.yml` |

## Static security scan

| Tool | Command | Result |
|------|---------|--------|
| Bandit | `bandit -r src -q -ll` (exact CI command) | PASS — exit 0, 0 results |
| ShellCheck | `shellcheck -S warning scripts/*.sh` (repo gate) + `.github/scripts/*.sh` | PASS — exit 0 after SC2034 fix in `post-review-comment.sh` |
| actionlint | local actionlint v1.7.12 on all workflows | PASS — exit 0 (was: **every Security Scan CI run failed at 0s**, see workflow integrity below) |
| gitleaks | `gitleaks detect` full history (v8.30.1, docker `ghcr.io/gitleaks/gitleaks`) | PASS — 0 leaks after fixing `.gitleaks.toml` schema + adding `.gitleaksignore` (8 historical false positives reviewed individually; none were secrets) |
| pip-audit | `pip-audit -r requirements.txt -r requirements-dev.txt` (v2.10.1, exact CI command) | PASS — "No known vulnerabilities found" |
| CodeQL | local CLI 2.27.4, suite `python-security-and-quality` | PASS — **39 → 0 findings** on tracked files (full analysis in `CODEQL-REMEDIATION.md`) |

## CI workflow integrity (finding fixed this round)

The `Security Scan` workflow (`.github/workflows/security-scan.yml`) contained
`uses: rhysd/actionlint:latest` — an invalid action reference that made GitHub
reject the entire workflow file ("workflow file issue"), so **every run since
the workflow was introduced failed in ~0s** and none of Bandit / pip-audit /
gitleaks / actionlint ever executed in CI (evidence: 12/12 failed runs incl.
run `42507638224`).

Fixes: actionlint is now invoked as a pinned, SHA256-verified release binary
step; shell-quoting findings in the two bot workflows were fixed; the local
actionlint run reproduces the CI behavior and passes.

## Dependency security

- `uv.lock` pinned and reproducible (`uv lock --check` exit 0, 93 packages).
- `pip-audit` over `requirements.txt` + `requirements-dev.txt`: no known vulnerabilities.
- Dependabot PRs #185 (actions minor/patch group) and #186 (uv image 0.13.5 → 0.13.7) verified green, independently reviewed by `policedbc` and merged (`f11312dc`, `afcd218`) — see `FINAL-REPORT.md` §22/§24. PR #184 (anthropic range `<3.0.0`) is **not mergeable as-is**: its required lock-check/sync-locked/docker-build checks fail because `uv.lock` was not regenerated; the Anthropic v2 migration is also explicitly not verified in this repository, so the range widening is not accepted yet (PR left open with a documented comment).

## Secrets

- No secrets, credentials, or API keys in source code or git history (gitleaks full-history scan clean after review of 8 historical false positives; fingerprints documented in `.gitleaksignore`).
- `.env`, `.env.bak`, `.env.ai` are gitignored and not committed (verified via `git check-ignore`).
- `/home/cvsz/.git-credentials` exists outside the repository (600 perms, owned by cvsz); never read, committed, or exposed.

## Penetration testing

Authorized, non-destructive, local-only testing performed this round:

1. **Path traversal & symlink escape** — `tests/unit/codeagent/test_sessions_memory.py` (traversal IDs rejected; symlink target rejected).
2. **Log injection (CRLF forging)** — new `test_model_registry_log_values_never_contain_line_breaks` with `\r\n`/`\n`/`\r` probes.
3. **Sandbox bypass via missing module** — code path now fails closed; no test overrides vary this behavior.
4. **Secret scanning over full git history** — gitleaks v8.30.1, 723 commits, 0 leaks after review.
5. **Taint-flow verification** — CodeQL SARIF code flows inspected for every finding class (result: 0).

NOT performed (disclosed): attacks against external hosts, network fuzzing,
production systems, or destructive resource-exhaustion tests against running
services.

## Findings

| ID | Severity | Location | Finding | Fix | Regression test | Status |
|----|----------|----------|---------|-----|-----------------|--------|
| SEC-W01 | P1 (CI integrity) | `.github/workflows/security-scan.yml` | Invalid `uses:` reference made the whole workflow fail at 0s on every run; no security scanning happened in CI | Pinned, checksum-verified actionlint step; quoting fixes | actionlint local run exit 0; CI on PR | FIXED |
| SEC-01/02 | P2 (CodeQL) | `agent/codeagent/sessions.py` | `py/path-injection` ×2 (custom validation not recognized; taint from HTTP handler) | `realpath` + `startswith` containment using canonical barrier patterns | `test_sessions_memory.py` | FIXED |
| SEC-03 | P2 (CodeQL) | `zgpu/llm/model_registry.py` | `py/log-injection` ×2 | Explicit `\r\n`/`\r`/`\n` replacement before printable filter | `test_model_registry_logging.py` (extended) | FIXED |
| SEC-04 | P2 (CodeQL) | `api/public/v1.py` | `py/stack-trace-exposure` (exception text in 403/409 envelopes) | Constant messages; route-scope-built FORBIDDEN message | `test_public_api_safety.py`, `test_public_api_queue.py` | FIXED |
| SEC-05 | P3 (CodeQL) | `agent/orchestration/adapters.py` | `py/weak-sensitive-data-hashing` (fast hash of credential) | Opaque per-process credential surrogate; no hashing | `test_provider_adapter_cache.py` | FIXED |
| SEC-06 | P2 (hygiene) | `agent/capabilities/code.py` | Sandbox silently skipped when module missing (fail-open) | Fail closed with `[SANDBOX BLOCKED]` | covered by sandbox paths | FIXED |
| SEC-07 | P3 (supply chain) | `.gitleaks.toml` | Allowlist used invalid schema (`[[allow]]`; glob `paths` are regexes) — silently non-functional | `[allowlist]` with regex paths; `.gitleaksignore` for 8 reviewed historical FPs | gitleaks full-history scan → 0 | FIXED |
| — | — | — | No P0 findings | — | — | None open |

## Residual risks (disclosed, not defects)

- `ruff format --check` reports files that would be reformatted (P3 maintainability; not a security issue). CI gate is `black --check .` (508 files clean); ruff format conflicts with black.
- External provider integrations (Anthropic, Gemini, Ollama, xAI, NVIDIA NIM) not live-tested (no authorized budget) — marked NOT VERIFIED / BLOCKED. Local loopback policy remains enforced and tested.
- GPU / llama.cpp local inference not exercised beyond mocked tests this round.
- `deploy/supabase/**` is gitignored/untracked in this repository: it is not covered by hosted CI or by CodeQL scanning. Local ad-hoc scans found only conservative/classifier issues there (clear-text-logging false positives around a URL without credentials); out of repository scope, unchanged.
- Production multi-tenant operation requires external identity, authorization, data isolation, audit retention, backup/restore per SECURITY.md known limitations.

## Status

**Status: NO OPEN SECURITY FINDINGS in tracked repository scope.** All CodeQL
alerts (5 error, 2 warning, 27 note) remediated and locally re-verified at 0
suite findings; CI security workflow repaired and validated; gitleaks and
pip-audit clean; Bandit/ShellCheck/actionlint clean. Independent review by
`policedbc` and merge verification recorded in `FINAL-REPORT.md`.
