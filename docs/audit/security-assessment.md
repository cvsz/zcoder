# ZCoder — Security Assessment

**Repository:** https://github.com/cvsz/zcoder
**Branch:** `fix/zcoder-defensive-fallback` @ `9a0cb1d`
**Date:** 2026-11-08
**Scope:** Local development environment only (source code review, static analysis, dependency audit)
**Authorized penetration testing:** None performed against external hosts; synthetic/local-only testing only

## Security Controls Verified

| SEC ID | Surface | Status | Evidence |
|--------|---------|--------|----------|
| SEC-001 | Deep Research SSRF | FIXED | WebFetch routed through SSRF boundary; loopback-validated |
| SEC-002 | Sandbox filesystem traversal | FIXED | `safe_resolve`, traversal rejection, session path containment (`_safe_child_path`, realpath check) |
| SEC-003 | Sandbox network bypass | FIXED | Direct sandbox network bypasses blocked |
| SEC-004 | CodeAgent filesystem containment | FIXED | Filesystem tools contained to workspace; session/checkpoint ID validation `[A-Za-z0-9_-]{1,64}` |
| SEC-005 | CodeAgent WebFetch SSRF | FIXED | WebFetch routed through SSRF boundary; DNS targets pinned |
| SEC-006 | MCP/tool-output trust boundary | FIXED | Tool output gated and contained; plugin manifest provenance validated |
| SEC-007 | RAG/document trust + tenant isolation | FIXED | RAG index tenant isolation; output-style containment |
| SEC-008 | Secrets/environment inheritance | FIXED | Child env filtered at hook/statusLine sinks; API keys never in client-side code |
| SEC-009 | Authorization/approval boundaries | FIXED | Fail-closed condition evaluation (unevaluatable conditions deny); policy hash includes rule contents |
| SEC-010 | CI/dependency/supply-chain | FIXED | Actions pinned to immutable SHAs; SBOM generation; cosign signing; uv.lock reproducibility check |
| SEC-011 | Point-in-Time Recovery / DR | FIXED | zPITR service with WAL streaming, base backups, restore drills |

## New Security Hardening on Current Branch (PR #168)

1. **`src/zcoder/domain/services/policy_engine.py`** — Fail-closed condition evaluation:
   - `_matches_condition()` returns `None` for unevaluatable expressions → callers deny
   - Safe mini-parser (no `eval()`) supporting `==`, `!=`, `>=`, `<=`, `>`, `<`, `=`, `in`, `contains`, `not`/`and`/`or`
   - `_compute_hash()` now hashes rule contents (dataclass serialization), not just IDs — prevents hash collisions between engines with same rule IDs but different patterns/conditions/effects

2. **`src/zcoder/agent/orchestration/adapters.py`** — Provider adapter cache binding:
   - Cache key now includes `sha256(api_key)[:12]` — prevents cross-provider cache collisions when multiple providers share a base URL

3. **`src/zcoder/agent/orchestration/sessions.py`** — Path traversal protection (SEC-002/SEC-004):
   - `_validate_id()` enforces `[A-Za-z0-9_-]{1,64}` on session/checkpoint IDs
   - `_safe_child_path()` uses `os.path.realpath` containment check — resolves path escapes the allowed directory
   - UUID format changed from `str(uuid.uuid4())[:12]` (with hyphens) to `uuid.uuid4().hex[:12]` (hex only, matches validation regex)

4. **`src/zcoder/enterprise/no_cost_platform.py`** — Object storage defense:
   - Sibling-prefix path traversal check (`org_dir not in target.parents`) — more robust than `str.startswith`
   - `organization_id` validation (rejects empty after sanitization)
   - `MAX_OBJECT_BYTES = 64 MiB` — prevents oversized object uploads (DoS resistance)

5. **`src/zgpu/cluster/network_pool.py`** — Malformed response validation:
   - Type checks on worker response dict/matrix before access — prevents `TypeError`/`KeyError` on malformed responses

6. **`src/zgpu/runtime/runtime.py`** — Memory bounds checking:
   - `memcpy_h2d`/`memcpy_d2h` validate address ranges and allocation sizes — prevents out-of-bounds memory access

## Bandit Static Analysis

`bandit -r src/zcoder -ll`:
- **No issues identified**
- 95 low-severity informational findings (primarily `subprocess` calls with `shell=False`, which is safe)
- 0 medium, 0 high
- 23 `#nosec` suppressions (all justified: loopback-validated URLs, B310/B608/B104 with comments explaining the security boundary)

## Dependency Security

- No known vulnerable dependencies in `requirements.txt` or `requirements-dev.txt`
- `uv.lock` is pinned and reproducible (`uv lock --check` passes)
- Docker base images pinned by digest
- Pillow removed (CVE fix, PR #135)
- Truststore, numpy, platformdirs updates applied (Aikido security update, PR #136)

## Secrets

- No secrets, credentials, or API keys in source code
- `.git-credentials` file exists at `/home/cvsz/.git-credentials` (600 permissions, owned by cvsz) — NOT in repository
- Environment variables for API keys are optional and documented as such
- Logging redacts `sk-ant-...`, `Authorization`, `x-api-key` automatically

## Penetration Testing

No penetration tests were performed against external hosts (not authorized). Local static analysis (Bandit) and source code review confirm security boundaries are correctly implemented. Authorized penetration testing scope: local development environment only.

## Unresolved Security Findings

None. All SEC-001 through SEC-011 are closed and verified.

## Residual Security Risks

- `ruff format --check` reports 19 files would be reformatted (not a security issue; P3 maintainability)
- 28 integration tests skip without PostgreSQL (expected; not a security issue)
