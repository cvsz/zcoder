# Selective zcoder-claude Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the architecture-compatible Anthropic GA and correctness improvements from the clean `zcoder-claude` reference into canonical `zcoder`, while adding the identified fail-closed API/deployment safeguards.

**Architecture:** Keep `zcoder`'s `src/zcoder` package and durable control-plane direction. Adapt wire-level behavior in existing Claude modules, use the existing OIDC validator for verified API identity, reuse the existing outbound URL security boundary, and do not introduce the alternate repository's flat storage or web-console architecture.

**Tech Stack:** Python 3.10+, urllib-based Anthropic adapters, pytest, Ruff, FastAPI optional web extra, PostgreSQL/SQLite control-plane backends, Helm templates.

## Global Constraints

- Work in `/home/cvsz/platforms/zcoder` on the current `main` checkout because the user approved implementation in the named target; do not create a second mutating worker.
- Preserve the seven pre-existing untracked target entries and do not inspect or modify the dirty `zcoder-claude` worktree.
- Use tests first for every behavior change: add or change the focused test, run it to observe the expected failure, implement the smallest compatible change, then rerun it green.
- Do not merge repository histories, copy the alternate flat architecture, update release claims, refresh dependencies, make provider calls, commit, or push.
- Never report local fake HTTP, skipped PostgreSQL, or absent OIDC-provider verification as live integration proof.

---

## Task 1: Port Files API GA behavior

**Files:**

- Add `tests/unit/test_claude_files_ga.py`.
- Modify `src/zcoder/claude/integrations/files.py`.

### Test-first steps

- [x] Add fake `urlopen_json` coverage for absolute `expires_at`, relative `expires_in_seconds`, malformed expiration values, and legacy responses.
- [x] Add assertions that `_headers()` and `ask_about_file()` omit `anthropic-beta` while keeping authentication and version headers.
- [x] Add upload tests requiring a returned file ID and normalizing relative expiry before local registration.
- [x] Add `page` query support tests and pagination tests for GA `next_page` cursors plus legacy `has_more`/`after_id` fallback.
- [x] Run `.venv/bin/python -m pytest -q tests/unit/test_claude_files_ga.py`; observe failures for the missing GA behavior.

### Implementation steps

- [x] Add a defensive `parse_expires_at(file_obj, now=None)` using timezone-aware standard-library datetimes; prefer an absolute string and derive one from non-negative relative seconds.
- [x] Retain `BETA_HEADER` only as a compatibility constant, remove it from every outgoing Files and file-reference request, and document the GA wire contract.
- [x] Validate upload responses contain a non-empty `id` before writing the local registry.
- [x] Add optional `page`, URL-encode list parameters, normalize expiry on list items, follow `next_page`, and stop safely on malformed/empty legacy pages.
- [x] Rerun the focused file tests and the existing file-related suite.

## Task 2: Port Skills API GA headers

**Files:**

- Modify `tests/unit/test_claude_skills_api.py`.
- Modify `src/zcoder/claude/enterprise/skills.py`.

### Test-first steps

- [x] Change expected beta lists so Skills and Files beta constants are absent while `CODE_EXECUTION_BETA` remains.
- [x] Add a wire-level fake request test proving the header contains no Skills/Files beta strings.
- [x] Add a test proving `_call(..., betas=[])` omits `anthropic-beta` entirely.
- [x] Run the focused Skills tests and observe the pre-change failures.

### Implementation steps

- [x] Make `_call` and `_post` accept optional beta lists and only add the header when the list is non-empty.
- [x] Keep the compatibility constants importable, but send only the code-execution beta from single- and multi-turn Skills calls; keep `has_file_uploads` accepted without reintroducing the Files beta.
- [x] Run the focused Skills tests and existing Claude tool tests.

## Task 3: Add GA computer-use request shape with legacy rollback

**Files:**

- Add `tests/unit/test_claude_computer_use_ga.py`.
- Modify `src/zcoder/claude/models/registry.py`.

### Test-first steps

- [x] Add fake HTTP tests for the GA descriptor, no beta header, custom dimensions, default and replacement `configs`, and multiple ordered `tool_use` blocks.
- [x] Add model-gating tests for Fable 5, Mythos 5, Opus 5, Sonnet 5, and Opus 4.8, plus a pre-request failure for unsupported models.
- [x] Add legacy opt-in tests asserting the existing dated tools and beta header remain available, and reject unknown toolset names.
- [x] Run the focused tests and observe failures against the current legacy-only implementation.

### Implementation steps

- [x] Add `COMPUTER_USE_TOOLSET_GA`, the supported-model set, and `computer_use_toolset_for_model()` with `zoom`, `batch_actions`, dimensions, and per-member configs.
- [x] Add `toolset` and `configs` constructor arguments, defaulting to GA and validating `ga`/`legacy`.
- [x] Make the request helper add a beta header only for legacy mode; preserve ordered response extraction and existing error conversion.
- [x] Run the focused computer-use tests and the existing server-tool registry tests to ensure the separate `ToolCoder` path is unchanged.

## Task 4: Route CodeSession costs through canonical pricing

**Files:**

- Add or extend `tests/unit/test_claude_code_session_cost.py`.
- Modify `src/zcoder/claude/capabilities/code.py`.

### Test-first steps

- [x] Add a test that a Sonnet 5 session with one million input and output tokens uses the canonical `$2/$10` rates rather than the hardcoded Sonnet 4.5 `$3/$15` rates.
- [x] Add a legacy Sonnet 4.5 assertion to prove the shared estimator still honors its legacy price table.
- [x] Run the focused test and observe the Sonnet 5 pricing failure.

### Implementation steps

- [x] Import `estimate_cost` from `zcoder.claude.optimization.cost` and replace the local arithmetic with `estimate_cost(self.model, input_tokens, output_tokens)`.
- [x] Preserve cumulative token and cost accounting and run the focused plus existing cost optimizer tests.

## Task 5: Harden public API identity and CORS configuration

**Files:**

- Add `src/zcoder/api/auth.py`.
- Add `tests/unit/test_api_auth.py`.
- Modify `src/zcoder/api/server.py`.

### Test-first steps

- [x] Add pure tests for missing/disabled OIDC configuration, missing/malformed bearer headers, validator failures, and valid identity mapping.
- [x] Assert organization and project come from verified claims, principal comes from `sub`, and caller-supplied `X-Organization-Id`, `X-Principal-Id`, `X-Project-Id`, and role values are ignored.
- [x] Add parser tests for empty CORS configuration, comma-separated explicit HTTP(S) origins, wildcard rejection with credentials, and malformed origins.
- [x] Run the focused tests before implementation.

### Implementation steps

- [x] Implement a FastAPI-independent `authenticate_request(headers)` helper that requires `ZCODER_AUTH_ENABLED=true`, issuer, and audience; validates the bearer token through `OidcValidator`; maps `ZCoderRole` to `EnterpriseRole`; and requires a non-empty organization claim and subject.
- [x] Implement `parse_cors_origins()` with an empty default and explicit-origin validation; reject `*` because credentials are enabled.
- [x] Configure the app with parsed origins and have `/api/v1` translate authentication-unavailable and invalid-token failures to 503/401 responses before dispatch.
- [x] Remove the default-admin context and all tenant/role selection from unverified request headers.
- [x] Run focused auth tests and the optional API server tests when FastAPI is installed.

## Task 6: Make public API behavior truthful and SSRF-safe

**Files:**

- Add `tests/unit/test_public_api_safety.py`.
- Modify `src/zcoder/api/public/v1.py`.

### Test-first steps

- [x] Add a job submission test proving the route does not return a synthetic `201` or an ID when no tenant-scoped durable enqueue path is wired.
- [x] Add webhook tests for loopback, metadata, private-DNS, userinfo-confusion, and public-DNS cases using a patched resolver/security boundary.
- [x] Run the focused public API tests and observe the current synthetic-success and substring-filter failures.

### Implementation steps

- [x] Return a stable 501 `JOB_QUEUE_UNAVAILABLE` API error for job creation until the tenant-scoped queue and worker claim contract are connected; do not cache this failure as a successful idempotent response.
- [x] Replace the webhook substring denylist with `validate_external_http_url()` and translate validation failures to `SSRF_BLOCKED`.
- [x] Run focused public API tests and existing router tests.

## Task 7: Enforce production configuration and correct the Helm worker command

**Files:**

- Modify `tests/unit/test_production_config.py`.
- Modify `src/zcoder/config/production.py`.
- Add `tests/unit/test_helm_worker_entrypoint.py`.
- Modify `deploy/helm/zcoder/templates/deployment.yaml`.

### Test-first steps

- [x] Add a production-profile load test that raises `ConfigValidationError` when required database/auth settings are missing.
- [x] Add a valid production load test that returns a configuration while retaining warning-only issues.
- [x] Add a manifest test asserting the worker overrides the image entrypoint with `python -m zcoder.worker.process` and passes only worker arguments.
- [x] Run focused tests and observe failures before changing implementation/template files.

### Implementation steps

- [x] Call `validate_config()` after file and environment resolution; raise `ConfigValidationError` only for `ERROR:` entries and preserve warning behavior.
- [x] Set Helm worker `command` to `["python", "-m", "zcoder.worker.process"]` and `args` to `["--pool-type", "standard"]`, matching the package source and Docker entrypoint semantics.
- [x] Run focused config and manifest tests.

## Task 8: Final verification and handoff

- [x] Inspect `git diff --stat`, `git diff --check`, and the full diff for only planned files.
- [x] Confirm the seven pre-existing untracked target entries remain present and untouched.
- [x] Run focused suites for Files, Skills, computer-use, CodeSession cost, API auth/safety, config, and Helm.
- [x] Run `.venv/bin/python -m pytest -q --disable-warnings --maxfail=1` and record optional dependency/PostgreSQL skips without treating them as failures.
- [x] Run `.venv/bin/ruff check src tests` if available and report any environment-specific omission.
- [x] Do not commit or push; hand off the exact changed files, test result, skips, and deferred live-provider evidence.
