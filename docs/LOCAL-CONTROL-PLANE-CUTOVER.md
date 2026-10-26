# Local Administration, Compliance and Orchestration Cutover

## Scope

`src/zcoder/services/local_control.py` is an **offline foundation**, not a
drop-in replacement for Anthropic administration/compliance or managed agents.
It uses Python stdlib SQLite and makes zero HTTP calls. No model provider is
needed for user/role metadata, task approval records or local audit inspection.

### Current capabilities

- Offline first-admin bootstrap (once per database)
- Local RBAC for `admin`, `operator`, and `auditor`
- Durable pending tasks and independent approval/rejection
- Append-only *application-level* SHA-256 audit chain with verification
- Deny-by-default access to admin actions and audit export
- Authenticated `/local/v1` API for principal roles, audit export, task approval,
  status, and approved task execution through loopback `llama.cpp`
- One-time task consumption and durable `RUNNING` / `COMPLETED` / `FAILED`
  execution state

### API configuration

The API reuses the repository's verified OIDC bearer-token middleware. Configure
`ZCODER_LOCAL_ORGANIZATION_ID` to bind the local SQLite database to one verified
organization. On first startup only, `ZCODER_LOCAL_BOOTSTRAP_ADMIN_SUBJECT` may
bootstrap the matching OIDC subject as the first administrator. Remove that
bootstrap setting after the first successful initialization. The database path
defaults to `~/.local/share/zcoder/local-control.sqlite3` and can be overridden
with `ZCODER_LOCAL_CONTROL_DATABASE`.

Routes are under `/local/v1`: `admin/principals`, `compliance/audit`, and
`tasks`. Task execution requires a separate admin approval and calls the
`llama.cpp` loopback provider; it does not run generated shell commands or
tools. Model output is stored as task result evidence.

### Security limits

- The store accepts an actor identifier and does not authenticate it itself.
  The `/local/v1` adapter validates OIDC bearer tokens and organization binding,
  then applies the store's local RBAC. Keep the adapter behind a trusted network
  boundary until API-level authorization and deployment tests are complete.
- The SQLite file can be modified by its OS owner; SHA-256 chaining is
  not a keyed signature, tamper-proof ledger, or independent attestation.
- Production admission still requires API integration tests for missing/invalid
  tokens, organization mismatch, role denial and bootstrap lifecycle; hardened
  deployment/network policy; durable backup and restore; off-host audit anchoring;
  retention and encryption policies.
- `APPROVED` is an approval **record**, not permission to execute arbitrary
  commands. The job runner needs its own identity, resource limits, isolation,
  replay protection, and live execution disabled by default.
- State transitions are transactional; there is no distributed worker queue,
  idempotency key, lease, fencing, or high-availability guarantee yet.

## Desired no-Anthropic migration

1. Default model inference to loopback `llama.cpp` GGUF via PR #137,
   when all release gates pass. Avoid implicit fallback to paid cloud APIs.
2. Separate the Anthropic-specific administration/compliance commands from
   local control-plane operations. Do not silently repurpose an Anthropic
   account management command to manage local identities.
3. Introduce explicit CLI namespaces such as `local-admin`, `local-compliance`,
   and `local-agent`. They remain separate from the API and must not be exposed
   until authenticated permission checks and CLI integration tests are complete.
4. Build a local agent workflow engine with SQLite/Postgres journal,
   bounded retries, fail-closed approval consumption, replay safety, model
   inference over loopback, cancellation and task evidence.
5. Gate or retire each old Anthropic-specific operation explicitly. Do not
   claim universal cloud independence while old `anthropic` SDK imports and
   direct `api.anthropic.com` requests remain reachable.
6. Run CLI, security, orchestration and full integration tests on the exact
   commit; add a deny-egress integration test and real GGUF model run.

## Developer validation

```bash
python -m pytest tests/unit/test_local_control.py -q
ruff check src/zcoder/services/local_control.py tests/unit/test_local_control.py
black --check src/zcoder/services/local_control.py tests/unit/test_local_control.py
```

The application-level tests are not evidence of production security. The API
adapter is now part of this draft, so add API-level authorization/bootstrap
regressions before treating it as an externally deployable service. Keep this
feature branch as a draft PR until security and independent review.
