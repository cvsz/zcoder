# Security Policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately. Do **not** open a public issue with exploit details, credentials, private data, or an unpatched proof of concept.

Use the repository Security policy entry point or contact the maintainer identified in repository metadata. Include:

- affected version or commit SHA;
- concise impact and trust boundary;
- deterministic reproduction steps using controlled, non-production data;
- sanitized logs or a minimal proof of concept when useful;
- suggested remediation or mitigations if known.

We aim to acknowledge actionable reports within 3 business days. Public disclosure should wait until a fix or coordinated mitigation is available.

## Supported versions

Security fixes target the current `main` branch and the most recent stable release. Older releases may receive fixes only when a supported upgrade path is not sufficient. For production use, stay on the latest verified release and review `CHANGELOG.md` and `exec-planning.md` before deployment.

## Security model

zcoder is an agentic coding platform. Treat model output, tool arguments, MCP/tool responses, retrieved documents, provider responses, repository content, web content, and user-supplied files as untrusted input until a boundary validates them.

The project follows these security principles:

- **Fail closed** for filesystem, network, permission, identity, tenant, and approval decisions.
- **Least privilege** for GitHub Actions tokens, provider credentials, containers, and runtime tools.
- **Provider-neutral authentication**: third-party/product traffic must not depend on Claude Free/Pro consumer OAuth credentials. Use explicit provider API keys, enterprise gateways, or approved local runtimes.
- **Bounded autonomous execution**: do not stack code changes on an unverified baseline; exact final heads must pass applicable hosted checks before merge.
- **No gate weakening**: tests, coverage thresholds, permissions, CodeQL, Dependency Review, Bandit, release gates, and other security controls are not relaxed to make a change pass.
- **Controlled validation only**: security tests must use repository fixtures, local/ephemeral resources, or explicitly authorized non-production systems. Do not attack third parties or production data.

## Built-in controls

Current controls include:

- centralized canonical path containment through `zcoder.core.security.safe_resolve()` for user/model-controlled filesystem paths, including CodeAgent `Read`, `Write`, `Edit`, `Glob`, `Grep`, and `LS` workspace access;
- conservative name/path validation and input-size limits;
- secret detection/redaction helpers and structured logging boundaries;
- HTTPS scheme validation and dedicated outbound-network security review requirements for fetch-style tools;
- sandbox controls for executable/tool surfaces and regression coverage for filesystem/network escape classes;
- explicit permission/approval boundaries for mutating operations;
- loopback-safe API server defaults unless an operator explicitly configures another bind address;
- non-root container execution and build-context secret exclusions;
- Python lint/test/security matrix plus Docker smoke validation;
- CodeQL, Dependency Review, Release Gate, Helm, and SDK/TypeScript hosted checks;
- Dependabot version updates for Python, GitHub Actions, and Docker dependencies;
- release checksums and artifact/container provenance attestations in release workflows.

## Secrets and credentials

Prefer environment injection from a secrets manager, workload identity, or provider-specific secure credential helper. Do not commit credentials, place secrets in issue bodies, or pass high-sensitivity admin/compliance keys on command lines where shell history or process inspection can expose them.

Provider, admin, compliance, GitHub, MCP, database, cloud, and signing credentials have different blast radii. Scope them to the minimum repository, tenant, operation, and lifetime required.

Local configuration files that can contain credentials are for controlled local development only unless protected by an appropriate operating-system or enterprise secret-storage mechanism.

## Agent/tool boundaries

Any new or changed tool must document and test:

1. the untrusted source of its arguments or content;
2. the privileged sink it can reach;
3. filesystem/network/secret/tenant/approval implications;
4. permission behavior in interactive and non-interactive modes;
5. redirect, symlink, subprocess, environment, and retry behavior where applicable;
6. bounded resource limits and safe error reporting.

Read-only classification does not by itself make a tool safe; reads and enumeration can expose host or tenant data.

## GitHub Actions and supply chain

Workflows should use least-privilege `permissions`, bounded timeouts/concurrency, maintained action runtimes, dependency review, and provenance for published artifacts. Prefer immutable full-length action SHAs for security-sensitive workflows when practical and keep pinned actions updated through Dependabot.

Release consumers should verify checksums and GitHub artifact attestations where provided.

## Known limitations

- Client-side retry/rate controls are not substitutes for server-side rate limiting in a shared deployment.
- Local and provider tool execution remains security-sensitive even when sandboxed; deployment policy must constrain filesystem, network, subprocess, identity, and secret access appropriate to the environment.
- Third-party MCP servers, plugins, hooks, skills, provider gateways, and retrieved content extend the trust boundary and require explicit operator review.
- Production multi-tenant deployments require external identity, authorization, data-isolation, audit-retention, backup/restore, and operational controls appropriate to the organization.

See `exec-planning.md` for current release-blocking security and production-readiness work. Security hypotheses are not treated as confirmed findings until source-to-sink reachability is validated.
