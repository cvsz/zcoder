# v1.30 Claude Platform upgrade design

## Goal

Build on the v1.29 bootstrap with three opt-in integrations that improve
interactive performance, current Claude Platform compatibility, and secure
tool connectivity without changing default request behaviour.

## Workstreams

### 1. Capability preflight and model routing

Add a small `ModelCapabilityResolver` that queries `/v1/models` once per
process, caches only non-secret capability metadata, and validates the chosen
model before sending a request.  It must fall back to the static catalog when
offline and must never silently substitute a model.

Acceptance tests:

- available model passes through unchanged;
- unavailable model returns a clear actionable error;
- offline mode uses the packaged catalog;
- no API keys or authorization headers enter logs.

### 2. Automatic prompt caching

Add an explicit `cache_mode=off|automatic` option to `Coder`, TUI, and web
console configuration.  `automatic` sends top-level
`cache_control={"type":"ephemeral"}` only for supported direct-Claude
requests.  It is disabled by default and unavailable for providers that do
not support automatic caching.

Acceptance tests:

- request payload contains a single top-level cache control field;
- normal requests remain byte-for-byte unchanged with `cache_mode=off`;
- cache diagnostics remain isolated to `CachingCoder`;
- usage reporting exposes cache read/write tokens when returned.

### 3. Secure remote MCP connector

Create `claude_mcp_connector.py` for the Messages API remote MCP connector.
Only HTTPS URLs are accepted. Credentials are sourced from environment names,
not CLI literals or persisted config.  Every server requires an explicit
tool allowlist; deferred tool loading is the default for large tool sets.

The adapter sends `mcp_servers`, `mcp_toolset`, and the
`mcp-client-2025-11-20` beta. It emits a ZDR-ineligibility warning before
the first request and redacts authorization tokens from errors and logs.

Acceptance tests:

- reject HTTP, loopback, and blank allowlists;
- produce correct `mcp_servers`/`mcp_toolset` payloads;
- verify beta header and token redaction;
- validate per-tool enabled/deferred configuration;
- no network calls in unit tests.

## Rollout

Ship the three workstreams as independent pull requests after this bootstrap.
Do not make caching or MCP automatic defaults.  Require payload regression
tests plus mocked API tests for every new request field.
