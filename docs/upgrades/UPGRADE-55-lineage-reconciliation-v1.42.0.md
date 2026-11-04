# U61 lineage reconciliation — v1.42.0

Date: 2026-10-25  
Scope: canonical-tree selection, package version source, local-only unique CLI feature.

## Decision

`/home/cvsz/zcoder` remains canonical. Its implementation lives under
`src/zcoder/`, with package boundaries, 11 GitHub workflows, and established
release gates. `/home/cvsz/zcoder-v1.60.0` is an extracted, flat-layout
snapshot without Git history or `.github/workflows`; replacing the canonical
tree would discard repository history and current CI/release structure. No
import migration is required: the canonical package layout is retained.

## Comparison matrix

| Surface | Canonical repository | v1.60.0 archive | Classification / action |
|---|---|---|---|
| Python layout | `src/zcoder/` modular package | Flat feature modules plus `domain/`, `application/`, `infrastructure/`, `interfaces/` | both-different; retain canonical layout |
| Tracked Python files | 320 across source and tests | 216 Python files, 63 test files | both-different; archive has no Git history |
| Tests | 150 test files | 63 test files | both-different; canonical suite remains authoritative |
| GitHub workflows | 11 workflows | none in archive | only-A; preserve canonical gates |
| CLI flags | 482 scraped option strings before port (483 after) | 479 scraped option strings | both-different; local plugin validation was missing and is now wired; local-session get/info names are equivalent |
| `--plugin-validate` | validator function existed, CLI option absent | option documented | only-B; ported as local filesystem validation |
| `--whoami` | absent | present; performs Messages API request | only-B; excluded by local-only request |
| Remote Compliance session commands | absent | present; reads remote Anthropic Compliance API | only-B; excluded by local-only request |
| Model catalog | lacks archive's newer cloud model names | adds Anthropic 5.5 family entries | only-B; excluded because it advertises remote API models |
| Version source | pyproject `1.41.5`; CLI and package init had literals | archive's internal version strings disagreed | both-different; metadata lookup now consumes package version |
| Release/upgrade docs | current modular repo history and gates | snapshot-specific docs/prompts | both-different; decision/evidence recorded here |

Counts are repository snapshots and string-level scans, not behavioral proof
of full CLI parity. The archive's full baseline suite recorded 898 passed,
0 failed, 0 skipped. The canonical baseline recorded 1,491 passed, 1 failed,
28 skipped; the pre-existing failure is
`test_01_api_key_guard_bypass`, and the skips require unavailable PostgreSQL.
The canonical test count is larger than the archive baseline.

## Changes

- `pyproject.toml` is the single package version source (`1.42.0`).
- `zcoder.__version__` and `zcoder.main.VERSION` read installed metadata,
  returning `0+unknown` in an uninstalled source checkout.
- `--plugin-validate PATH` invokes the existing local filesystem validator;
  validation errors return exit code 1. It does not install plugins or make
  network requests; plugin source files are not modified.
- `--live` now invokes the loopback model client in normal and
  `ZCODER_LOCAL_MODE` configurations. It no longer creates an Anthropic SDK
  client with a placeholder key or returns a fabricated offline response.
- `--cite` and `--rag` answer from local files with the loopback model client;
  returned source IDs are checked against supplied documents. They do not
  claim server-verified offsets or quoted passages.
- Structured JSON generation and schema-guided extraction now use the local
  model, followed by client-side required-field validation.
- `--advisor` now runs local advisor and executor passes; it does not send
  provider-tool requests or API credentials.
- The local provider branch of `--route` now delegates classifier and
  specialist generations to the loopback `Coder`; it no longer returns a
  canned stub as if local inference had run.
- The core `--code-agent` now uses loopback `/v1/chat/completions`, translates
  tool schemas and tool history to local function-call format, accepts a
  constrained JSON tool-call envelope, and ignores provider API-key values.
  One CPU smoke run completed a real read-only `Read` tool call. Remote MCP
  tunneling remains unavailable in local-only mode.
- The ordinary `--stream` command now consumes local llama-server SSE,
  requests token usage, rejects non-loopback URLs and redirects, and sends no
  provider credentials. A CPU smoke run returned `LOCAL_STREAM_OK` with usage
  counts. Provider-specific fine-grained tool streaming remains unavailable
  in local-only mode.
- Fixed `/skill info` slash dispatch: the singular command is now routed, the
  skills directory is canonicalized before containment checks, and the command
  reads the registry's stored `path` field. Regression coverage verifies a
  project-local skill can be found and reported.
- The local-only CLI guard now has a parameterized integration test that
  parses and dispatches all 150 direct-provider CLI destinations and confirms
  each exits before its provider-specific handler is reached, including native
  Excel/PowerPoint Skills modes; local Excel/PowerPoint modes remain allowed.
- Local `Coder`, `--code-agent`, and `--stream` requests now emit provider-
  neutral model spans plus Prometheus call, error, and duration metrics; trace
  attributes identify provider, model, and operation without high-cardinality
  metric labels.
- Local-only enforcement now covers CLI dispatch and direct library entry
  points: Anthropic SDK clients are rejected before construction and shared
  outbound HTTP boundaries reject Anthropic-hosted URLs before network access.
- CLI paths that still use provider-specific APIs fail closed under local
  provider settings. This reduces accidental remote calls while their local
  replacements remain incomplete.
- `ZCODER_LOCAL_MODE=1` takes precedence over `ZCODER_PROVIDER`; regression
  tests cover conflicting remote and invalid provider values so they cannot
  bypass the direct-API command guard. The shared provider resolver now gives
  local-only mode precedence over both CLI and environment provider overrides,
  including the multi-agent router; a regression test proves remote dispatch
  is not reached when a remote provider is explicitly requested. The local
  provider also discards any supplied API key before request construction.
- Web-console chat streaming now uses the loopback llama-server SSE endpoint;
  non-loopback model URLs are rejected, legacy request API keys are ignored,
  and the model selector exposes only configured local `ZCODER_MODEL`.
- Runtime readiness now enforces the package's Python 3.12 minimum; contributor
  instructions and the pull request template match the CI 3.12/3.13 matrix.
- Ruff, Black, and mypy targets now follow the Python 3.12 minimum. Existing
  string Enum output is preserved through a shared compatibility base.
- No Anthropic API calls or cloud model catalog additions were introduced.

## Verification

- Targeted plugin, version, CLI wiring, local-live, local-citation, and release-candidate tests passed.
- Ruff passed on all changed Python files; `node --check
  scripts/release-candidate.mjs` passed; `git diff --check` passed.
- A live `--route` smoke test using `qwen-1.5b-q4km.gguf` and loopback
  llama-server completed both classifier and specialist generations and
  returned `LOCAL_ROUTE_OK`; the model server was stopped afterward.
- The latest wheel built successfully, its ZIP integrity check passed, and
  the Docker image built with the locked dependencies and printed version
  `1.42.0`.
- Full suite after local citations, structured output, CLI guard, advisor
  migration, local web-console stream, and local router generation:
  **1,561 passed, 0 skipped** using the shared PostgreSQL 16 Docker service
  through `scripts/local_postgres.py run -- python -m pytest -o addopts='' -q -rA`.
  The suite includes regression coverage for provider overrides attempting
  to bypass local-only mode, local web streaming, and runtime Python baseline.
  The latest run, including local router generation, local-only web model
  catalog, and readiness-check changes, completed in 86.27 seconds.
- Release-candidate fixture exposed an outdated literal-only version check;
  the checker now recognizes metadata lookup in both runtime modules. Its
  focused fixture tests pass. An actual clean-HEAD release preflight remains
  unverified because this working tree is intentionally uncommitted.
- Editable package installation refreshed metadata to `1.42.0`; runtime
  package, CLI, and project version assertions pass.
- `uv lock --check`, `pip check`, wheel build, Docker build, and container
  `--version` smoke check pass. The local model health endpoint did not
  respond during startup; after loading, a CPU inference using
  `qwen-7b-q4km.gguf` returned `LOCAL_OK` through loopback. Other model and
  hardware acceptance remains open.
- `pip-audit -r requirements.txt -r requirements-dev.txt` reported no known
  vulnerabilities in the audited dependency set.
- Mypy reports 420 errors across 40 source files; this remains open
  type-safety work. After migrating the core local code-agent call path, the
  refreshed static scan finds references in 27 source modules. This does
  not prove reachability or complete local-only
  behavior.
- Live GitHub inspection found strict main protection and a one-approval
  requirement. The live required-check matrix was reconciled with CI by
  removing obsolete Python 3.10/3.11 contexts and requiring Python 3.12/3.13.
  Admin enforcement remains enabled, with force-push and deletion disabled.
  Local `main` remains ahead of `origin/main`; hosted checks have not run for
  this uncommitted candidate.
- The release gate remains **NOT QUALIFIED**: version and test evidence,
  security, PITR, and final qualification are UNKNOWN for the uncommitted
  candidate.

## Latest candidate verification — 2026-10-26

- The local `--code-agent` CPU smoke test returned `LOCAL_AGENT_READ_OK` after
  invoking the real `Read` tool against `README.md`; its loopback llama-server
  was stopped and port 8080 was confirmed closed afterward.
- The local `--stream` CPU smoke test returned `LOCAL_STREAM_OK`, reported
  34 input and 4 output tokens, and confirmed the llama-server port was
  closed after shutdown.
- Latest full PostgreSQL-backed rerun after provider-neutral model
  observability, architecture-boundary, and local-provider-precedence changes:
  **1,597 passed, 0 skipped** in 87.87 seconds, using
  `python scripts/local_postgres.py run --` against the dedicated `zcoder_db`
  PostgreSQL 16.15 service.
- `ruff check .`, `black --check .` (339 files unchanged), and `pip check`
  passed. Bandit reported 81 low-severity findings and no medium/high findings;
  the scanner exited non-zero, so the security gate is not marked passed.
- The current source built `zcoder-1.42.0-py3-none-any.whl`; ZIP integrity
  passed and the wheel contains `zcoder/services/model_observability.py`.
  After the local-provider-precedence fix, the wheel was rebuilt and its ZIP
  integrity passed again after credential stripping. Docker image
  `zcoder:check-local-guard-20261026` built successfully and printed
  `ZCoder CLI v1.42.0` for `--version`.
- `pip-audit` evidence above belongs to the earlier candidate validation and
  has not been repeated after the latest source changes.
- Current static inventory: 28 source modules still reference Anthropic SDK
  classes or endpoints. Hosted exact-candidate checks, clean-HEAD release
  evidence, PITR, mypy cleanup, and final release qualification remain open.

## Follow-up hardening — 2026-10-26

- Local-only outbound policy is re-applied to every redirect in the shared
  urllib boundary and to redirects from caller-supplied external URLs. This
  closes a path where a non-Anthropic URL could redirect into an Anthropic
  endpoint after the initial check.
- OIDC JWKS retrieval now checks the provider policy before using `httpx` and
  disables redirects only in local-only mode. Normal configured OIDC operation
  retains the existing redirect behavior.
- Regression tests verify that local-only mode rejects Anthropic SDK client
  construction, direct urllib requests, external URL redirects, generic urllib
  redirects, and OIDC JWKS requests before network access. The focused local-only,
  CLI-guard, and OIDC suite passed **99 tests**. Ruff, Black, targeted mypy,
  Bandit `-ll`, and `git diff --check` passed for these changes.
- These tests prove the guarded call paths and CLI dispatch behavior; they do
  not prove real inference for every feature, hosted-provider parity, or
  repository-wide absence of Anthropic-compatible modules.
- Release evidence handling was also tightened: CI matrix requirements now
  match Python 3.12/3.13; merge-commit dependency review is tied back to its PR
  head; dirty worktrees cannot promote commit evidence; and PITR needs a fresh
  (30-day) operational restore record with a digest, supplied through the
  `ZCODER_PITR_EVIDENCE_JSON` Actions variable. The variable is not configured
  in the repository, so PITR and overall release qualification remain UNKNOWN.
- The release-evidence/preflight test group passed **45 tests**. Workflow YAML
  parsed successfully; `actionlint` is unavailable in this environment.
- After these follow-up source changes, the full dedicated PostgreSQL 16.15
  suite passed **1,609 tests** in 90.41 seconds. Ruff and Black passed across
  the repository, mypy passed all 168 source files, and `git diff --check`
  passed.
- The current wheel rebuilt as `zcoder-1.42.0-py3-none-any.whl` and passed
  ZIP integrity verification. The current Docker image rebuilt and, with
  `ZCODER_LOCAL_MODE=1`, printed `ZCoder CLI v1.42.0`.
- Clean exact-head hosted checks, production WAL archive verification, and a
  production restore drill have not been performed. The worktree remains
  dirty and these changes are not committed.

## Next cycle

U62 in the archive assumes live Anthropic model retirement behavior. Re-scope
that prompt to local-model/provider behavior before implementing any remote
catalog or endpoint change.
