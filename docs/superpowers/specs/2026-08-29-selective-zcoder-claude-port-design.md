# Selective zcoder-claude Port Design

## Goal

Make `zcoder` the canonical implementation while selectively adopting the
useful, architecture-compatible changes identified in `zcoder-claude`.
The work must preserve `zcoder`'s package layout, durable control-plane
direction, tenant boundaries, and existing local changes.

## Scope

The port has three bounded workstreams:

1. Anthropic compatibility: Files API GA response and pagination handling,
   Skills API GA headers, GA computer-use request construction with an
   explicit legacy path, and model-aware session cost estimation.
2. Runtime safety: fail-closed public API authentication, configured CORS,
   resolver-backed webhook SSRF validation, truthful job submission behavior,
   and production configuration validation at load time.
3. Deployment correctness: invoke the packaged worker module from the Helm
   deployment, overriding the image entrypoint correctly.

## Architecture

`zcoder` remains the source of truth. Anthropic wire changes stay in the
existing `zcoder.claude` modules and reuse its retry, error, and cost helpers.
The API boundary uses the existing OIDC validator and maps verified identity
claims into the existing immutable `RequestContext`; request headers cannot
select an organization, principal, role, or project. An API request without
usable OIDC configuration or a valid bearer token is rejected.

The public jobs endpoint will not fabricate a successful job until it is wired
to the tenant-scoped durable queue and worker claim path. It will return a
stable not-implemented error instead of returning an ID that cannot be found
or executed. Webhook registration remains an API operation, but its URL is
checked by the existing outbound security boundary, including DNS-resolved
private-address rejection.

The existing flat local-state and devtools modules in `zcoder-claude` have no
corresponding target abstraction and are not introduced as a second storage
architecture.

## Error handling

- Files responses without an ID fail before local registration.
- GA expiration fields are normalized defensively; legacy responses remain
  usable.
- Unsupported GA computer-use models fail before an HTTP request; callers can
  opt into the dated legacy tool shape.
- Invalid production configuration raises `ConfigValidationError` for errors
  while preserving warning-only configurations.
- Missing or invalid API authentication returns an authentication failure;
  missing server auth configuration is an unavailable-authentication failure.
- Unsupported job submission returns a stable 501 error and is never cached as
  a successful idempotent result.
- SSRF validation failures return a stable `SSRF_BLOCKED` API error.

## Verification

Each behavior change is covered test-first with focused unit tests and fake
HTTP or validator boundaries. The final gates are the complete local pytest
suite, Ruff, diff whitespace checks, and a review of the final diff and
preserved worktree entries. Live Anthropic, PostgreSQL, and OIDC provider
verification remains separate evidence and is not claimed by local tests.

## Explicit exclusions

No wholesale repository merge, alternate web console, flat JSON persistence,
dirty release/version claims, dependency refresh, commit/push, or real
provider traffic is part of this change.
