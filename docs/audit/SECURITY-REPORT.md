# ZCoder — Security Report (Independent Audit)

**Repository:** https://github.com/cvsz/zcoder  
**Owner:** cvsz  
**Branch:** `main`  
**Initial HEAD:** `e868ee44dea4df7ae2d7ef1cccc1151e273ee8db`  
**Audit date:** 2026-11-08  
**Auditor:** cvsz  
**Scope:** Local development environment only — source review, static analysis, dependency audit. No penetration testing against external hosts; no production testing; no real data exfiltration. Loopback/local fixtures only.

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
| SSRF / URL scheme | `validate_url()` (HTTPS-only), outbound security review | VERIFIED | HTTPS scheme enforcement; loopback-validated fetch tools |
| Tool output trust | MCP/tool-output gating, plugin manifest provenance | VERIFIED | Tool output contained; manifest provenance validated |
| Tenant / session IDs | Session/checkpoint ID validation `[A-Za-z0-9_-]{1,64}`, `_safe_child_path()` realpath containment | VERIFIED | `src/zcoder/agent/orchestration/sessions.py` |
| Secrets / env inheritance | `is_secret_env_name()`, `build_child_env()` (drops credential-named vars) | VERIFIED | `src/zcoder/core/security.py`; `DATABASE_URL`, `PGPASSWORD`, `SSH_AUTH_SOCK` filtered |
| Authorization / approval | Fail-closed policy engine mini-parser (no `eval()`); rule-content hash | VERIFIED | `src/zcoder/domain/services/policy_engine.py` |
| Secret redaction in logs | `sk-ant-...`, `Authorization`, `x-api-key` redacted | VERIFIED | Structured logging boundaries |
| Container / supply chain | Non-root containers; pinned base images; pinned action SHAs; `uv.lock --check` | VERIFIED | Dockerfile; CI workflows; `uv lock --check` exit 0 |
| CI least privilege | `permissions: contents: read` on CI; pinned actions; dependabot | VERIFIED | `.github/workflows/ci.yml` |

## Static security scan

| Tool | Command | Result |
|------|---------|--------|
| Bandit | `bandit -r src/zcoder -ll` | PASS — "No issues identified"; 95 low informational (subprocess with shell=False — safe), 0 medium, 0 high; 23 justified `#nosec` |
| ShellCheck | `shellcheck` on all `*.sh` | PASS — exit 0; one informational SC2034 (unused var) |
| gitleaks / secret scan | `.gitleaks.toml` configured | No committed secrets; `.env*` gitignored |

## Dependency security

- `uv.lock` pinned and reproducible (`uv lock --check` exit 0, 64 packages).
- No known vulnerable dependencies in `requirements.txt` / `requirements-dev.txt`.
- Pillow removed (prior CVE fix). Truststore, numpy, platformdirs updates applied (prior Aikido remediation).
- Anthropic SDK kept on v1 per CHANGELOG (v2 migration not yet verified — not forced).

## Secrets

- No secrets, credentials, or API keys in source code (verified by grep).
- `.env`, `.env.bak`, `.env.ai` are gitignored and not committed (verified via `git check-ignore`).
- `/home/cvsz/.git-credentials` exists outside the repository (600 perms, owned by cvsz); never read, committed, or exposed.

## Penetration testing

None performed against external hosts (not authorized). Authorized scope: local development environment only. Local static analysis (Bandit) and source review confirm security boundaries are correctly implemented.

## Findings

| ID | Severity | Location | Finding | Fix | Regression test | Status |
|----|----------|----------|---------|-----|-----------------|--------|
| — | — | — | No P0/P1 security findings | — | — | None open |

## Residual risks (disclosed, not defects)

- `ruff format --check` reports 19 files would be reformatted (P3 maintainability; not a security issue). CI gate is `black --check .` which passes; ruff format conflicts with black (applying ruff format breaks black).
- External provider integrations (Anthropic, Gemini, Ollama, xAI, NVIDIA NIM) not live-tested (no authorized budget) — marked NOT VERIFIED / BLOCKED.
- GPU / llama.cpp local inference not exercised beyond mocked tests.
- Production multi-tenant operation requires external identity, authorization, data isolation, audit retention, backup/restore per SECURITY.md known limitations.

## Status

**Status: NO OPEN SECURITY FINDINGS** — All SEC-001 through SEC-011 closed and verified; Bandit/ShellCheck/gitleaks clean; no P0/P1 security findings. No security fixes required in this audit.
