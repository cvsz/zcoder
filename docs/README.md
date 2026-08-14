# zcoder Documentation

Documentation is organized by concern:

- `architecture/` — data flow and high-availability boundaries. The canonical architecture document remains [`/ARCHITECTURE.md`](../ARCHITECTURE.md).
- `security/` — credentials, encryption, identity, SSO, SCIM, and service accounts. The repository security policy remains [`/SECURITY.md`](../SECURITY.md).
- `compliance/` — controls, evidence, data residency, multi-tenancy, retention, quotas, regions, and policy.
- `operations/` — deployment, Kubernetes, SLOs, disaster recovery, billing, metering, observability, and runbooks.
- `enterprise/` — enterprise feature matrix, RBAC, organizations, and MCP conformance.
- `guides/` — user and operator guides, [Developer Portal](DEVELOPER-PORTAL.md), [Zero-Cost Matrix](guides/NO-COST-MATRIX.md), and [Offline Free Guide](guides/LOCAL-FREE.md). [`/QUICKSTART.md`](../QUICKSTART.md) remains the repository quick-start entry point.
- `upgrades/` — historical release, migration, audit, and upgrade notes (UPGRADE-01 through UPGRADE-23, v1.40.0).
- `prompts/` — historical upgrade/audit prompt assets.

New documentation must be placed in the matching taxonomy instead of the `docs/` root.
