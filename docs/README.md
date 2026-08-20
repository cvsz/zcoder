# zcoder Documentation

Documentation is organized by concern:

- `architecture/` — data flow and high-availability boundaries. The canonical architecture document remains [`/ARCHITECTURE.md`](../ARCHITECTURE.md).
- `security/` — credentials, encryption, identity, SSO, SCIM, service accounts, and security design material. The repository security policy remains [`/SECURITY.md`](../SECURITY.md).
- `compliance/` — controls, evidence, data residency, multi-tenancy, retention, quotas, regions, and policy.
- `operations/` — deployment, Kubernetes, SLOs, disaster recovery, billing, metering, observability, runbooks, and [GitHub governance/workflow policy](operations/GITHUB-GOVERNANCE.md).
- `enterprise/` — enterprise feature matrix, RBAC, organizations, and MCP conformance.
- `guides/` — user and operator guides, [Developer Portal](DEVELOPER-PORTAL.md), [Zero-Cost Matrix](guides/NO-COST-MATRIX.md), and [Offline Free Guide](guides/LOCAL-FREE.md). [`/QUICKSTART.md`](../QUICKSTART.md) remains the repository quick-start entry point.
- `upgrades/` — historical release, migration, audit, and upgrade notes.
- `prompts/` — historical upgrade/audit prompt assets.

Repository-level governance and contribution entry points live at the root: [`GOVERNANCE.md`](../GOVERNANCE.md), [`SUPPORT.md`](../SUPPORT.md), [`CODE_OF_CONDUCT.md`](../CODE_OF_CONDUCT.md), [`CONTRIBUTING.md`](../CONTRIBUTING.md), [`SECURITY.md`](../SECURITY.md), and the canonical production execution plan [`exec-planning.md`](../exec-planning.md).

New documentation must be placed in the matching taxonomy instead of the `docs/` root unless it is a repository-level community-health or canonical project document.
