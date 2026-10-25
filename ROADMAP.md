# ZCoder Roadmap

## Current direction

ZCoder is moving to local-first inference. The default prompt and routing
commands use the loopback llama.cpp server and a GGUF model. The local
database setup uses the shared Docker PostgreSQL container named
`zPostgreSQL`, with an isolated `zcoder_db` database and role.

## Completed in the current worktree

- Default `zcoder -p` generation uses the loopback chat-completions endpoint.
- The `--route` default uses the local model gateway; the retired provider
  choice is rejected by the CLI and provider resolver.
- Interactive chat, Git text generation, GitHub review assistance, prompt
  optimization, evaluations, and RAG generation use the shared local model
  client.
- The local client rejects non-loopback URLs and HTTP redirects.
- PostgreSQL-backed API, worker, and integration-test commands use the
  shared `zPostgreSQL` container and the `zPostgreSQL_network` bridge.

## Remaining implementation

### Local inference coverage

- Replace the remaining direct remote inference clients in capabilities,
  administration, compliance, files, model utilities, observability, and
  orchestration.
- Replace provider-specific tool formats with local tool orchestration, or
  make unsupported operations fail clearly before attempting network access.
- Add end-to-end coverage for each supported local capability and verify
  outbound requests stay on loopback.

### Administration and compliance

- Connect authentication and verified identities to local user and role
  management.
- Complete audit export, retention, backup, access controls, and integrity
  verification for local compliance records.
- Integrate durable approvals with the local agent worker and cancellation
  lifecycle.

### Documentation and release

- Replace stale migration notes and examples with the current local runtime,
  database, and security behavior.
- Reconcile CLI help, README, architecture records, and operational guides
  against implemented behavior.
- Complete the full integration, security, packaging, and local-model
  acceptance gates before release.

## Release criteria

- No supported CLI, API, worker, or web path can send inference requests to a
  retired remote model endpoint.
- Every advertised local feature has automated coverage and a documented
  failure mode when its local dependency is unavailable.
- Administration and compliance operations enforce authenticated identity
  and authorization at the service boundary.
- All required CI, security, packaging, and runtime acceptance checks pass on
  the exact release commit.
