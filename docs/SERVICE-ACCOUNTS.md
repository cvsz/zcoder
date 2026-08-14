# ZCoder Service Accounts & Scoped API Keys

## 1. Non-Human Principals
Automated pipelines, CI/CD runners, and background workers authenticate using dedicated `ServiceAccount` objects rather than user impersonation accounts.

## 2. API Key Security & Lifecycle
- **Format**: `zck_<org_prefix>_<random_id>_<secret_key>`
- **Storage**: Only SHA-256 hashes are stored in the database. Full secrets are shown once at creation time.
- **Rotation**: Supports overlapping keys for zero-downtime rotation.
- **Scoping**: API keys carry explicit permission scopes (e.g. `job:create`, `repo:read`) bounded strictly by the parent organization and project.
