# zcoder Production Readiness & Execution Planning

**Document Status:** ACTIVE // CANONICAL EXECUTION PLAN  
**Current Baseline:** `main@98204b66bdb24866de4219718b3ba600e48877cd`  
**Last Updated:** 2026-08-20  
**Scope:** Drive `cvsz/zcoder` from the verified Clean Architecture baseline to enterprise-grade-ready, production-grade-ready final release while preserving Upgrade-20/24 bounded execution, provider-neutral model routing, security gates, test/coverage thresholds, exact-head hosted verification, and rollback-safe delivery.

---

## 1. Executive State

The repository has completed the Upgrade-01..25 foundation, durable engineering runtime, bounded continuous engineering loop, canonical `src/zcoder` migration, service/infrastructure architecture hardening, and the first six confirmed AI-agent security remediation slices (SEC-001..006, SEC-OUTPUT).

The active program now has three coordinated tracks:

1. **Security closure first** — validate and remediate remaining source-to-sink attack surfaces before stacking feature work on affected runtime boundaries.
2. **Claude-Code-like provider-neutral parity** — complete terminal/agent UX, permissions, tools, hooks, skills, MCP, subagents/teams, plugins, sessions, remote/headless workflows, and provider routing without using Claude Free/Pro consumer OAuth credentials.
3. **Enterprise production qualification** — complete fleet wiring, auditability, multi-tenancy, observability, supply-chain evidence, backup/restore/rollback, deployment health, and exact-release-candidate qualification.

Implementation is not completion. A slice is complete only when its exact PR head is green across all applicable hosted gates and has no unresolved blocker. A feature being present does not make the repository production-ready until security, durability, operational, and release evidence are green on the same exact release candidate.

---

## 2. Non-Negotiable Execution Rules

1. **Upgrade-20/24 bounded execution:** one bounded vertical slice at a time; no recursive autonomous stacking on an unverified baseline.
2. **Exact-head verification:** merge only the exact head SHA that passed hosted verification.
3. **No gate weakening:** never lower coverage, skip/xfail security regressions, relax permissions, suppress CodeQL/Dependency Review findings to obtain green status, or weaken Release Gate/Helm/SDK checks.
4. **Security source-to-sink rule:** validate reachability before calling a hypothesis a finding; patch only confirmed findings.
5. **Smallest secure architectural change:** reuse centralized security/domain primitives instead of duplicating validators or introducing compatibility hacks.
6. **Provider-neutral authentication:** do not depend on Claude Free/Pro consumer OAuth tokens. Support explicit provider API keys, enterprise gateways, and local/free runtimes where available.
7. **No third-party/production attacks:** security validation stays within repository tests, controlled fixtures, localhost/private test resources, and non-production resources.
8. **Fail closed:** permission, filesystem, network, tenant, approval, and identity boundaries must deny ambiguous or unsafe operations.
9. **No unsafe broad rewrites:** if a connector mutation would rewrite a large source file beyond the bounded diff, reset rather than carry a risky replacement.
10. **Docs are evidence:** update this file and release evidence only after state is actually verified; never mark pending work complete.
11. **No hidden paid fallback:** offline/local/no-cost modes must not silently route to paid providers.
12. **Release candidate immutability:** final qualification evidence must point to one exact release-candidate SHA; any code/config/dependency change invalidates that evidence and requires re-verification.

---

## 3. Current Verified Architecture Baseline

- Canonical implementation lives under `src/zcoder/`.
- Domain/application dependency direction is guarded by architecture tests.
- Upgrade-20 remains task-level engineering authority; Upgrade-24 owns bounded queue policy; durable continuous engineering composes persistence, leases, fencing, and runtime around them.
- SQLite/PostgreSQL durable engineering state, cross-process run leases, fencing, restart/idempotency, and maintenance orchestration are implemented.
- CI supports Python 3.9, 3.10, 3.11, and 3.12 plus Ruff, Black, Bandit/security, Docker, CodeQL, Dependency Review, Helm, Release Gate, and SDK/TypeScript validation.
- Local/offline/no-cost operation remains a first-class path; paid-provider fallback must never be implicit.
- CodeAgent filesystem access now uses the centralized canonical containment primitive for `Read`, `Write`, `Edit`, `Glob`, `Grep`, and `LS`.
- API server default bind is loopback-safe (`127.0.0.1`) while preserving explicit operator override through configuration.

---

## 4. Security Attack-Surface Coverage Matrix

| ID | Surface | State | Completion Evidence / Next Gate |
|---|---|---|---|
| SEC-001 | Deep Research / outbound SSRF | FIXED / MERGED | Existing SSRF protections and regressions merged |
| SEC-002 | Sandbox filesystem traversal | FIXED / MERGED | Filesystem boundary protections merged |
| SEC-003 | Sandbox direct network bypass | FIXED / MERGED | Interpreter and `/dev/tcp`/`/dev/udp` bypass regressions merged |
| SEC-OUTPUT | Sensitive provider/runtime error disclosure | FIXED / MERGED | Stable client errors + server-side logging merged |
| **SEC-004** | **CodeAgent Read/Write/Edit/Glob/Grep/LS workspace escape** | **FIXED / VERIFIED / MERGED** | PR #48 exact head `14842197ddedbcffe912f42033ce962974d00e0e`; squash merge `9e85e2362d38f898bf9ee388cddb63e358d4a5ba` |
| **SEC-005** | **CodeAgent WebFetch SSRF** | **FIXED / VERIFIED / MERGED** | PRs #60 + #61; exact merged head `815a10c53f925ecf615b8c8a15bdc4329a6cffca`; all 20 hosted checks green |
| SEC-006 | MCP/tool-output trust boundary | FIXED / VERIFIED / MERGED | PR #64; exact merged head `4cb9c141dc55c8cd6165645fb2f3abef387dc9c6`; all 20 hosted checks green |
| SEC-007 | RAG/document trust + tenant isolation | QUEUED | Validate cross-tenant retrieval, document-triggered actions, tenant-scoped indexes/caches |
| SEC-008 | Secrets/environment inheritance | QUEUED | Validate subprocess/hooks/MCP env propagation, secret redaction, child-process inheritance |
| SEC-009 | Authorization/approval boundaries | QUEUED | Validate deny/ask/allow precedence, approval replay/expiry, mutating actions, audit identity |
| SEC-010 | CI/dependency/supply-chain | QUEUED | Review workflow permissions, action pinning, provenance, SBOM, dependency pinning, artifact integrity |

### 4.1 SEC-004 Closure Evidence

Confirmed pre-fix path:

```text
model-controlled tool input
  -> CodeAgent._execute_tool()
  -> non-interactive askPermission auto-approval for Read/Glob/Grep/LS
  -> CodeAgent._run_tool()
  -> model-controlled filesystem path
  -> local filesystem read/enumeration/write/edit outside session.cwd
```

Merged remediation:

- `Read`, `Write`, `Edit`, `Glob`, `Grep`, and `LS` pass through `zcoder.core.security.safe_resolve()`;
- relative traversal, absolute escapes, and symlink escapes are rejected;
- Glob/Grep path-like traversal patterns are rejected before enumeration;
- mutation tests prove Write/Edit do not alter files outside the workspace;
- normal in-workspace behavior remains covered;
- non-interactive permission behavior still routes through containment.

Exact hosted verification for PR #48 head `14842197ddedbcffe912f42033ce962974d00e0e`:

- CI run `32278816677` — success;
- CodeQL run `32278816719` — success;
- Dependency Review run `32278816785` — success;
- Release Gate run `32278816690` — success;
- Helm Lint run `32278816768` — success;
- SDK & TypeScript run `32278816704` — success;
- Python 3.9 / 3.10 / 3.11 / 3.12, Ruff, Black, Bandit/security, and Docker jobs — success;
- unresolved review threads — none.

### 4.2 SEC-005 Closure Evidence

Confirmed pre-fix path:

```text
model-controlled tool input
  -> CodeAgent._execute_tool() (WebFetch branch)
  -> CodeAgent._webfetch_retrying()
  -> urllib.request.Request(url)
  -> safe_urlopen()  (scheme-only check)
  -> urllib.request.urlopen   -- follows up to 10 unvalidated redirects
  -> loopback / private / link-local / cloud-metadata / userinfo-confusion sink
```

Confirmed reachability (validated before remediation): WebFetch is auto-approved in
non-interactive `askPermission` mode (read-only preset), so a model-controlled URL
could direct the agent to `http://127.0.0.1:8080/...`, `http://169.254.169.254/...`
(cloud metadata), `http://[::1]/...`, `http://10.0.0.1/...`, or reach any of those
via a redirect from a public URL. Response bodies were read unbounded.

Merged remediation (PRs #60 + #61):

- `WebFetch` now routes through `zcoder.core.outbound_security.safe_external_urlopen`
  — the same centralized boundary SEC-001 Deep Research uses;
- non-public IP literals and DNS answers rejected (loopback, private, link-local,
  multicast, unspecified, reserved, IPv4-mapped IPv6, cloud-metadata ranges);
- userinfo hostname-confusion forms rejected;
- every redirect hop re-validated via `_ExternalRedirectHandler` (`max_redirections=5`);
- environment proxy discovery disabled (`ProxyHandler({})`) so inherited/attacker
  proxy settings cannot silently move the connection onto a private network;
- response body bounded to 1 MiB (`WEBFETCH_MAX_RESPONSE_BYTES`) before decode.

Exact hosted verification for merged head `815a10c53f925ecf615b8c8a15bdc4329a6cffca`:

- CI Python 3.9 `96389430697` / 3.10 `96389430474` / 3.11 `96389430504` / 3.12 `96389430510` — success;
- lint `96389430155` — success; Ruff/Black clean;
- security + Bandit/pip-audit `96389430598` / `96389430652` — success;
- CodeQL `96389431198` — success;
- Dependency Review `96389430529` — success;
- Gitleaks secret scan `96389430529` — success;
- Helm v3 `96389431372` / v4 `96389431098` — success;
- Release Gate `96389430460` — success;
- Validate TypeScript SDK & Types `96389430893` — success;
- docker-build `96389860141`, build-and-push `96389430757`, deploy `96389589866` — success;
- unresolved review threads — none.

Known residual limitation (documented in `outbound_security.py`): DNS-rebinding TOCTOU
between validation and connect remains a production network-egress responsibility;
userspace validation cannot pin the connection socket to the validated address.

---

## 5. Active Bounded Execution Queue

### Slice A — SEC-004 CodeAgent Filesystem Containment — **COMPLETE / MERGED**

**PR:** #48  
**Verified Head:** `14842197ddedbcffe912f42033ce962974d00e0e`  
**Merge Commit:** `9e85e2362d38f898bf9ee388cddb63e358d4a5ba`

Tasks:

- [x] Revalidate source-to-sink reachability.
- [x] Route `Read`, `Write`, `Edit`, `Glob`, `Grep`, and `LS` through centralized containment.
- [x] Add traversal, absolute, symlink, enumeration, mutation, normal-behavior, and non-interactive permission regressions.
- [x] Ruff + Black green.
- [x] Bandit/security green.
- [x] Python 3.9–3.12 green.
- [x] Docker green.
- [x] CodeQL + Dependency Review + Release Gate + Helm + SDK/TypeScript green.
- [x] No unresolved review blocker.
- [x] Exact-head squash merge complete.

### Slice B — SEC-005 CodeAgent WebFetch SSRF — **COMPLETE / MERGED**

Analysis performed before any remediation (do-not-assume-a-finding discipline):

- [x] Identified all `WebFetch`/URL-fetch source entry points and actual network sinks — `CodeAgent._run_tool()` WebFetch branch -> `_webfetch_retrying()` -> `safe_urlopen()` -> `urllib.request.urlopen`; server-side `web_fetch` tools (`search.py`, `agents_sdk.py` presets) are executed by Anthropic infra, not locally, and are out of scope for local SSRF.
- [x] Verified scheme restrictions and URL canonicalization — scheme-only check pre-fix; centralized boundary enforces http/https only.
- [x] Verified hostname resolution and IP classification before connection — pre-fix none; boundary rejects non-public literals and DNS answers (loopback, RFC1918/private, link-local incl. `169.254.169.254`, multicast, unspecified, reserved, IPv4-mapped IPv6).
- [x] Loopback, private, link-local, multicast, unspecified, reserved, and cloud-metadata destinations blocked (SEC-002-style regression set).
- [x] Every redirect hop re-validated — `_ExternalRedirectHandler` with `max_redirections=5`.
- [x] DNS resolution re-validation — resolution is checked for every validation and redirect hop; connection socket pinning is a documented network-egress responsibility (TOCTOU rebinding residual).
- [x] IPv4 and IPv6 handling verified, including IPv4-mapped IPv6 forms (`::ffff:127.0.0.1` rejected).
- [x] Redirect count, response size, timeout, and decompression/resource amplification bounded — `max_redirections=5`, `WEBFETCH_MAX_RESPONSE_BYTES=1 MiB`, 15s timeout.
- [x] Proxy/environment settings cannot silently bypass destination policy — `ProxyHandler({})` disables env proxy discovery for the external opener.
- [x] Regression tests added only after reachability was confirmed — PRs #60 + #61.
- [x] One bounded PR pair merged for the smallest architectural remediation.

**PRs:** #60 + #61  
**Verified Head (exact merged SHA):** `815a10c53f925ecf615b8c8a15bdc4329a6cffca`  
**Merged:** #60 at `056be7c` (tests), #61 at `815a10c` (remediation) — all 20 hosted checks green on the exact merged head.

Stop rule satisfied: SEC-005 verification is green on the exact merged head; Slice C may begin.

### Slice C — MCP / Tool-Output Trust Boundary — **COMPLETE / MERGED**

Validated every path where untrusted MCP/tool output can cross into Bash, filesystem mutation, network actions, prompts with elevated tool authority, or structured action dispatch without an explicit trust/approval transition. Confirmed findings, each validated for reachability before remediation:

- **Tool-agent loop (`cmd_tool_agent` → `run_agent`):** executed every model tool call with no permission gate and no filesystem containment — `run_python` reached `subprocess` with model-chosen code, `write_file` wrote to arbitrary paths; tool results (MCP/web/plugin content) fed the loop. Fixed: fail-closed approval mirroring CodeAgent semantics (`_approve`: read-only auto-approved, mutating/exec denied without approval, `bypassPermissions`/planMode/dontAsk honored, `can_use_tool` callback authoritative) + `read_file`/`write_file`/`list_files` through centralized `safe_resolve` containment.
- **Browsing agent (`cmd_browse`):** fetched model/page-derived navigation URLs through `safe_urlopen` (scheme-only) — the same SSRF surface SEC-005 closed for WebFetch. Fixed: browse fetch routes through `safe_external_urlopen`.
- **Compliance file download:** server-supplied Content-Disposition filename written directly to disk; absolute/traversal components could place the download anywhere. Fixed: `_safe_download_filename` sanitizes to a bare basename with `file_id` fallback.

Inherent-design note (not a finding): tool results are re-fed to a model retaining tool authority; the boundary is enforced at tool-execution gates, which this slice strengthens.

**PR:** #64  
**Verified Head:** `34524a9` (all 18 PR checks green)  
**Merge Commit:** `4cb9c141dc55c8cd6165645fb2f3abef387dc9c6` (all 20 merged-head checks green)  
**Next slice:** Slice D — Permission & Approval Parity/Hardening

### Slice D — Permission & Approval Parity/Hardening — **COMPLETE / MERGED**

Mapped every permission/approval decision point (`CodeAgent._execute_tool`, `HooksEngine`, tool-agent `_approve`, hooks/perms engines) and validated precedence against the plan's contract. Confirmed findings, each validated by reachability:

- **`acceptEdits` auto-approved ALL tool calls** — including `Bash` — despite the documented contract "auto-approve file edits; ask for other tool calls". Reachable via `--code-agent-permission acceptEdits` and as the default for custom/plugin slash commands running the `code` preset (includes Bash). Fixed: `acceptEdits` auto-approves only `Write`/`Edit`/`MultiEdit`/`NotebookEdit` + read-only tools; everything else drops into the `askPermission` path (non-interactive fail-closed).
- **PreToolUse hooks failed open** — timeout/exception/exit≠2 silently allowed the tool call; an ambiguous hook decision was treated as consent. Fixed: `PreToolUse` fires `fail_closed`; timeout/error/unrecognized exit code block the call. PostToolUse/Notification keep warn-and-continue (non-decision events).
- **Denied calls recorded as approved** — every denial path used the `add_tool_call` default `approved=True`, mislabeling denials as approvals. Fixed: every denial path records `approved=False` with its reason.

Verified already-correct: hook deny runs first and cannot be overridden by `bypassPermissions`; `dontAsk`/planMode deny everything (fail-closed); `can_use_tool` callback authoritative.

**PR:** #65  
**Verified Head:** `68ff355` (all 17 PR checks green)  
**Merge Commit:** `95d8582c9943b28b2c280a16d6e6d3d0a42fabd6` (all 19 merged-head checks green)  
**Next slice:** Slice E (cont.) — remaining items: sessions/resume/checkpoints, skills & slash-command lifecycle, hooks lifecycle, MCP transports/trust, subagents/teams, plugins/marketplaces, built-in tool parity, IDE/web/remote/CI, observability/audit/tenancy (SEC-007 RAG/document trust + tenant isolation remains the next security hypothesis)

### Slice E — Claude-Code-like Provider-Neutral Feature Parity

#### Slice E.1 — Provider-Neutral Routing (item 11: provider-neutral routing, explicit API keys/gateways, local/free runtimes) — **COMPLETE / MERGED**

The multi-agent router (`zcoder/claude/orchestration/router.py`) was hardcoded to
Anthropic (`ENDPOINT` + `x-api-key`). Added a provider abstraction
(`zcoder/claude/orchestration/providers.py`) so routing is gateway-agnostic:

- **provider precedence:** `--provider` > `ZCODER_PROVIDER` env > `ZCODER_LOCAL_MODE=1` > `anthropic`
- **api_key precedence:** `--api-key` > provider-specific env (`ANTHROPIC_API_KEY`, `GEMINI_API_KEY`/`GOOGLE_API_KEY`, `XAI_API_KEY`) > `""`
- **base_url precedence:** `--base-url` > `ZCODER_BASE_URL` > `OLLAMA_BASE_URL` > provider default

Providers: `anthropic` (`x-api-key`), `gemini` (`x-goog-api-key`, model in path,
`contents`/`systemInstruction` translation), `xai` (`Bearer`, OpenAI-compat),
`ollama` (`http://localhost:11434`, no auth), `local` (no network, stub). Every
base URL is scheme-checked (http/https only) via `safe_urlopen` semantics; explicit
gateways are operator-configured so local/private addresses are intentionally allowed
for `ollama`/`local`, while remote gateways remain operator trust (consistent with the
outbound-security boundary: `safe_urlopen` for gateways vs `safe_external_urlopen` for
model-chosen URLs). Router `classify`/`route_and_call`/parallel fan-out thread
provider/base_url through the adapter and normalize provider responses to the existing
Anthropic-shaped contract. CLI adds `--provider` (choices) and `--base-url`.
Regressions: `tests/unit/test_router_provider_parity.py` (28 tests: endpoint/auth/
payload/parse per provider, precedence, scheme rejection, local stub, parallel/error).

- **PR:** #66
- **Verified Head:** `62e6414` (all 18 PR checks green; CodeQL cleared after URL-cleanup fix)
- **Merge Commit:** `f46317f7aaf742cf00d0433e29c4e7349dc64e93` (all 19 merged-head checks green)

#### Slice E.2 — Scoped CLAUDE.md Memory + Trust Boundary (item 3) — **COMPLETE / MERGED**

`MemoryManager` previously read cwd `.claude/CLAUDE.md` / `CLAUDE.md` and
`~/.claude/CLAUDE.md` with no scoping hierarchy, no containment, and no trust
delimitation, injecting raw text into the system prompt. Reworked into a scoped
hierarchy that doubles as SEC-007 document-trust progress:

- **Precedence floor → ceiling:** enterprise (managed policy baseline) → user →
  project (walk-up discovery from the workspace).
- **Containment:** every discovered file is resolved via `safe_resolve` against
  its own directory, so a `.claude/CLAUDE.md` symlink escape (e.g. → `/etc/shadow`)
  is rejected — fail-closed (SEC-004/SEC-007 alignment).
- **Size cap:** 256 KiB/file to prevent prompt-bombing.
- **Trust boundary:** `combined()` wraps loaded files in a clearly-delimited
  `<loaded_memory context="untrusted-project-and-user-files">` block so the model
  distinguishes them from system policy; security gates remain code-enforced
  (fail-closed) and cannot be disabled by loaded memory.
- **Opt-out:** `--no-project-memory` disables auto-loading (loads only the user
  memory file); wired through `cmd_code_agent` / `cmd_code_subagent` / `query`.
- **Backward-compatible** `read_project` / `read_user` / `append_*` retained.
- Regressions: `tests/unit/test_project_memory.py` (9 tests: precedence, walk-up
  discovery, containment rejection, missing-file handling, size cap, delimited
  render, opt-out, backward compat).

- **PR:** #67
- **Verified Head:** `7b18ef1` (all 18 PR checks green)
- **Merge Commit:** `7fa8e659336c7b98700a1e83642dd5ca1298c750` (all 19 merged-head checks green)

#### Slice E.3 — Skills Loader Containment (item 4, security hardening) — **COMPLETE / MERGED**

The local skills loader (`SkillsRegistry.load()`) read every
`.claude/skills/<n>/SKILL.md` (and plugin skill files) with no containment and
no size cap, then surfaced the file's first line as the `/skills` description —
a malicious `.claude/skills/evil/SKILL.md` symlink to `/etc/shadow` leaked
secret contents into the listing (info-leak, SEC-004/SEC-007). Hardened with
the same trust boundary applied to memory (E.2):

- **Containment:** every SKILL.md is read only after `safe_resolve` proves it
  stays within its owning directory (custom → `skills_dir`; plugin →
  `plugin_dir`), so symlink/path escapes are rejected (fail-closed).
- **Size cap:** 256 KiB per skill file (`check_file_size`).
- **Name validation:** skill names containing `/` or `..` are rejected.
- `load_plugin_skills` now also returns `plugin_dir` so plugin-skill containment
  has a correct base.
- Latent bug caught in review: `check_file_size` returns `None` on success
  (raises only on oversize); the loader now calls it bare rather than
  `if not check_file_size(...)`.

- **PR:** #68
- **Verified Head:** `ed7fb08` (all 18 PR checks green, incl. test 3.9)
- **Merge Commit:** `98204b66bdb24866de4219718b3ba600e48877cd` (all 19 merged-head checks green)
- Note: full *skills & slash-command lifecycle* UX (item 4) remains a follow-up;
  this slice closes the security gap in the loader. Agent (`.claude/agents`) and
  custom-command loaders share the pre-hardening pattern and need identical
  containment (item 7 / commands follow-up).

#### Remaining Slice E items (future bounded PRs)

Progress only in bounded PRs through:

1. terminal/headless/streaming/JSON UX;
2. sessions, resume, checkpoints, rewind, branchable conversations;
3. ~~CLAUDE.md-compatible memory plus scoped rules/config hierarchy~~ — **DONE (Slice E.2)**;
4. skills and slash-command lifecycle — **loader security hardening DONE (Slice E.3); full lifecycle/UX remains**;
5. hooks lifecycle and policy-safe event model;
6. MCP transports, discovery, resource/tool trust policy;
7. subagents and agent teams with bounded budgets/permissions (incl. agent/`.claude/agents` loader containment);
8. plugins/marketplaces with provenance and permission manifests;
9. complete built-in tool parity with security boundaries;
10. IDE/web/remote/CI workflows;
11. ~~provider-neutral routing, explicit API keys/gateways, local/free runtimes~~ — **DONE (Slice E.1)**;
12. observability, audit, tenancy, quotas, deployment, upgrade/migration, disaster recovery.

Reference priority for parity research:

```text
official Claude Code documentation
  -> public anthropics/claude-code repository
  -> vetted third-party reverse-engineering/design references
  -> zcoder gap analysis
  -> one bounded implementation PR
```

Third-party reverse-engineering references are design aids only. Do not copy proprietary source, private protocols, authentication secrets, or consumer-subscription credential behavior.

### Slice F — Production Fleet Wiring

After security-critical agent boundaries are green:

- provider-backed GitHub adapter construction;
- durable SQLite/PostgreSQL multi-process/fleet runtime wiring;
- worker/service entrypoints for scheduled maintenance campaigns;
- crash-resume/fencing/lease integration tests across processes;
- explicit repository mutation approvals;
- OTel metrics/logs/traces and operational dashboards;
- readiness/liveness/startup health contracts;
- backup/restore, rollback, migration rehearsal, and disaster-recovery evidence;
- tenant quotas, admission control, backpressure, and bounded concurrency.

### Slice G — Supply-Chain & Release Engineering

- pin third-party GitHub Actions to immutable commits where policy requires;
- generate and retain SBOM/provenance for release artifacts;
- verify wheel/container/chart checksums and artifact signing policy;
- dependency review plus lock/pin strategy for reproducible builds;
- least-privilege workflow tokens and environment protections;
- secret-free build logs and release metadata;
- release rollback and compromised-artifact revocation procedure.

---

## 6. Enterprise Final Release Qualification Matrix

Final Release may be declared only when every applicable release-blocking row is green on one exact release-candidate SHA.

| Gate | Requirement | Current Program State |
|---|---|---|
| Python | 3.9 / 3.10 / 3.11 / 3.12 all green | Continuous per PR; must be green on final RC |
| Coverage | Existing threshold preserved or increased | Enforced; final RC evidence required |
| Lint/Format | Ruff + Black green | Enforced |
| Security | Bandit/security green; confirmed findings closed | SEC-007/008/010 remain to review; SEC-009 covered by Slice D |
| Code scanning | CodeQL green with no unresolved introduced alert | Enforced |
| Dependencies | Dependency Review green; no unaccepted high/critical release blocker | Enforced; reproducibility review pending |
| Containers | Docker build/version/health smoke green | Enforced; runtime hardening evidence pending |
| Helm | Lint/template checks green | Enforced; deployment rehearsal pending |
| SDK | TypeScript/SDK compatibility checks green | Enforced; parity completion pending |
| Release Gate | Production release audit green | Enforced |
| Architecture | Dependency direction/cycle guards green | Enforced |
| AuthN/AuthZ | Provider-neutral auth, RBAC/approval ceilings, no consumer OAuth dependency | Slice D merged at `95d8582` (approval/deny precedence, fail-closed hooks, audit flags); RBAC/provider-auth parity pending |
| Tenancy | Tenant/data isolation regressions green | Deep review pending |
| Network | SSRF/redirect/private-network/DNS-rebinding boundaries verified | SEC-005 verified at `815a10c`; DNS-rebinding egress residual documented |
| Filesystem | Workspace/sandbox containment verified | SEC-002 + SEC-004 merged; final RC recheck required |
| MCP/Tools | Untrusted output cannot silently gain elevated side effects | SEC-006 verified at `4cb9c14`; memory-agent approval parity noted as follow-up |
| Secrets | Redaction + environment/process inheritance policy verified | Review pending |
| Observability | Structured logs, metrics, tracing, security/audit events verified | Production evidence pending |
| Durability | restart/idempotency/lease/fencing/crash recovery verified | Implemented baseline; fleet E2E evidence pending |
| Performance | bounded latency/memory/concurrency/backpressure targets documented and tested | Qualification pending |
| Packaging | clean wheel/install + container/chart artifacts + checksums/SBOM/provenance | Supply-chain slice pending |
| Operations | health/readiness, config validation, backup/restore, rollback, DR rehearsal | Qualification pending |
| Documentation | README/architecture/security/runbooks/upgrade/release evidence current | Continuous; final RC evidence required |

### 6.1 Final Release Hard Stops

Do not declare **Enterprise Final Release Complete** while any of these remain true:

- a confirmed high/critical security finding is unremediated;
- SEC-007 document/tenant isolation paths are not verified;
- MCP/tool-output trust transition is not verified;
- approval/authorization replay and mutation semantics are not verified;
- cross-tenant data/tool paths are not verified;
- MCP/tool-output trust transition is not verified;
- final release candidate lacks one complete hosted verification set;
- artifacts lack required integrity/provenance/SBOM evidence;
- backup/restore/rollback/DR procedures are untested;
- production observability and audit trails are not demonstrated;
- release documentation points to a different SHA than the qualified artifacts.

---

## 7. Completion Evidence Ledger

### Slice D — Permission & Approval Parity/Hardening (SEC-009)

- PR: #65
- verified head: `68ff355` (all 17 PR checks green)
- merge commit: `95d8582c9943b28b2c280a16d6e6d3d0a42fabd6`
- CI: `96418268169` (3.9) / `96418268050` (3.10) / `96418267899` (3.11) / `96418268103` (3.12) — success
- lint: `96418268213` — success
- security / Bandit & pip-audit: `96418268147` / `96418268341` — success
- CodeQL / Analyze Python Code Security: `96418268288` — success
- Dependency Review / Gitleaks: `96418268208` — success
- Helm v3 `96418268398` / v4 `96418268126` — success
- Release Gate: `96418267995` — success
- SDK & TypeScript: `96418268534` — success
- docker-build `96418664875`, build-and-push `96418268137`, deploy `96418371583` — success
- review threads: none unresolved
- security result: acceptEdits now approves edits+reads only (Bash/other tools ask, non-interactive fail-closed); PreToolUse hooks fail closed on timeout/error/unknown exit; denial audit records approved=False
- compatibility/rollback note: deny-first precedence unchanged; interactive approval prompts unchanged; only acceptEdits auto-approval scope narrowed (behavior change intended by documented contract)
- next security hypothesis: SEC-007 RAG/document trust + tenant isolation

### Slice E.1 — Provider-Neutral Routing (item 11)

- PR: #66
- verified head: `62e6414` (all 18 PR checks green)
- merge commit: `f46317f7aaf742cf00d0433e29c4e7349dc64e93`
- CI: `96442793554` (3.9) / `96442793730` (3.10) / `96442793615` (3.11) / `96442793628` (3.12) — success
- lint: `96442793511` — success
- security / Bandit & pip-audit: `96442793250` / `96442792959` — success
- CodeQL / Analyze Python Code Security: pass — `96443041194` / `96442795395` — success
- Dependency Review / Gitleaks: `96442793312` / `96442793104` — success
- Helm v3 `96442793544` / v4 `96442793300` — success
- Release Gate: `96442793419` — success
- SDK & TypeScript: `96442793206` — success
- docker-build `96443299326`, build-and-push `96442793140`, deploy `96442793140` — success
- review threads: none unresolved
- security result: router no longer hardcoded to Anthropic; provider abstraction (anthropic/gemini/xai/ollama/local) with explicit precedence for provider/api-key/base-url; all gateway URLs scheme-checked (http/https only); local/ollama allow local addresses by design; remote gateways operator-trusted; 28 regression tests
- compatibility/rollback note: classify/route_and_call external contract unchanged; `ENDPOINT` + `x-api-key` retained for back-compat; other capabilities (code agent, models registry) still call Anthropic directly — separate slice
- next security hypothesis: SEC-007 RAG/document trust + tenant isolation

### Slice E.2 — Scoped CLAUDE.md Memory + Trust Boundary (item 3)

- PR: #67
- verified head: `7b18ef1` (all 18 PR checks green)
- merge commit: `7fa8e659336c7b98700a1e83642dd5ca1298c750`
- CI: `96468067780` (3.9) / `96468067631` (3.10) / `96468067741` (3.11) / `96468067587` (3.12) — success
- lint: `96468067637` — success
- security / Bandit & pip-audit: `96468067332` / `96468067939` — success
- CodeQL / Analyze Python Code Security: pass — `96468324098` / `96468066798` — success
- Dependency Review / Gitleaks: `96468067167` / `96468067552` — success
- Helm v3 `96468067074` / v4 `96468067205` — success
- Release Gate: `96468067695` — success
- SDK & TypeScript: `96468066986` — success
- docker-build `96468594419`, build-and-push `96468067167`, deploy `96468067167` — success
- review threads: none unresolved
- security result: CLAUDE.md memory now scoped (enterprise→user→project) with walk-up discovery; every file containment-checked via safe_resolve (symlink escape rejected, fail-closed); 256KiB size cap; loaded files wrapped in delimited <loaded_memory> untrusted block; --no-project-memory opt-out; 9 regression tests
- compatibility/rollback note: read_project/read_user/append_* backward-compatible; opt-out preserves fail-closed auto-load default; RAG/document retrieval trust + tenant isolation for namespaces are separate follow-ups
- next security hypothesis: SEC-007 RAG/document trust + tenant isolation

### Slice E.3 — Skills Loader Containment (item 4, security hardening)

- PR: #68
- verified head: `ed7fb08` (all 18 PR checks green, incl. test 3.9)
- merge commit: `98204b66bdb24866de4219718b3ba600e48877cd`
- CI: `96485973984` (3.9) / `96485974205` (3.10) / `96485974043` (3.11) / `96485973953` (3.12) — success
- lint: `96485973944` — success
- security / Bandit & pip-audit: `96485973710` / `96485974012` — success
- CodeQL / Analyze Python Code Security: pass — `96486235505` / `96485973754` — success
- Dependency Review / Gitleaks: `96485973754` / `96485973754` — success
- Helm v3/v4 `96485973754` — success
- Release Gate: `96485973710` — success
- SDK & TypeScript: `96485973944` — success
- docker-build / build-and-push / deploy `96485973710` — success
- review threads: none unresolved (one CI failure caught pre-merge: `Path | None` / `str | None` annotations broke Python 3.9 collection; fixed by using `Optional[...]` in code.py and `from __future__ import annotations` in the test module)
- security result: SKILL.md loading now containment-checked via safe_resolve (custom→skills_dir, plugin→plugin_dir; symlink escape rejected, fail-closed); 256KiB size cap; names with `/` or `..` rejected; 8 regression tests
- compatibility/rollback note: load_plugin_skills now also returns plugin_dir (additive key); no behavior change for managed/anthropic skills; full skills/slash lifecycle UX remains a follow-up; agent/command loaders need identical containment
- next security hypothesis: SEC-007 RAG/document trust + tenant isolation

### SEC-006 — MCP / Tool-Output Trust Boundary

- PR: #64
- verified head: `34524a9` (all 18 PR checks green)
- merge commit: `4cb9c141dc55c8cd6165645fb2f3abef387dc9c6`
- CI: `96402660389` (3.9) / `96402660213` (3.10) / `96402660376` (3.11) / `96402660334` (3.12) — success
- lint: `96402660100` — success
- security / Bandit & pip-audit: `96402660323` / `96402660201` — success
- CodeQL / Analyze Python Code Security: `96402660065` — success
- Dependency Review: `96402660454` — success
- Gitleaks: `96402660454` — success
- Helm v3 `96402659915` / v4 `96402660182` — success
- Release Gate: `96402660174` — success
- SDK & TypeScript: `96402659955` — success
- docker-build `96403032734`, build-and-push `96402660109`, deploy `96402773130` — success
- review threads: none unresolved
- security result: tool-agent loop gated (fail-closed approval, `safe_resolve` containment), browse fetch SSRF-gated via centralized boundary, compliance download filename sanitized
- next security hypothesis: SEC-007 RAG/document trust + tenant isolation

### SEC-005 — CodeAgent WebFetch SSRF

- PRs: #60 (tests) + #61 (remediation)
- verified head (exact merged SHA): `815a10c53f925ecf615b8c8a15bdc4329a6cffca`
- merge commits: #60 `056be7c` (tests), #61 `815a10c` (remediation)
- CI: `96389430697` (3.9) / `96389430474` (3.10) / `96389430504` (3.11) / `96389430510` (3.12) — success
- lint: `96389430155` — success
- security / Bandit & pip-audit: `96389430598` / `96389430652` — success
- CodeQL: `96389431198` — success
- Dependency Review: `96389430529` — success
- Gitleaks: `96389430529` — success
- Helm v3 `96389431372` / v4 `96389431098` — success
- Release Gate: `96389430460` — success
- SDK & TypeScript: `96389430893` — success
- docker-build `96389860141`, build-and-push `96389430757`, deploy `96389589866` — success
- review threads: none unresolved
- security result: CodeAgent WebFetch now routes through the centralized external-URL boundary; non-public literals/DNS, userinfo confusion, redirect hops, env-proxy bypass, and unbounded reads closed; 1 MiB response cap + redirect cap + proxy-disable hardening
- next security hypothesis: SEC-007 RAG/document trust + tenant isolation

### SEC-004 — CodeAgent Filesystem Workspace Containment

- PR: #48
- verified head: `14842197ddedbcffe912f42033ce962974d00e0e`
- merge commit: `9e85e2362d38f898bf9ee388cddb63e358d4a5ba`
- CI: `32278816677` — success
- CodeQL: `32278816719` — success
- Dependency Review: `32278816785` — success
- Release Gate: `32278816690` — success
- Helm Lint: `32278816768` — success
- SDK & TypeScript: `32278816704` — success
- review threads: none unresolved
- security result: relative traversal, absolute escape, symlink escape, read/enumeration escape, and Write/Edit outside-workspace mutation closed for CodeAgent filesystem tools
- next security hypothesis: SEC-007 RAG/document trust + tenant isolation

For every future merged slice record the PR number, exact verified head SHA, merge SHA, required workflow run IDs/results, test/coverage result, security/capability result, compatibility/migration note, rollback note, and next highest-priority unresolved slice.

Do not mark **Final Release Complete** until every release-blocking row in Section 6 is satisfied on one exact release candidate commit.
---

## 8. History Re-Signing Migration

**Date:** 2026-08-20

All 227 commits on `main` were re-signed with GPG key `220A4C8CCC7D2D50` (commit signing, `commit.gpgsign=true`). This rewrote every commit object; the re-signed history is verified byte-identical in content (all 227 trees match the pre-sign history in order) and every commit now carries a valid Good signature. Old SHA references recorded in this document were rewritten to their re-signed equivalents (e.g. `375fbc7→fe9809b`, `ce4e8c5→95d8582`, `0f00977→4cb9c14`, `965ac74→815a10c`). CI check-run IDs and verification evidence remain valid (they bind to the exact commits at verification time). Pre-sign backup preserved at `refs/tags/backup/pre-sign-375fbc7`.

