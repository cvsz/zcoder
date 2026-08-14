# ZCoder Data Retention & Legal-Hold Boundary

## 1. Configurable Retention Classes
- `job_events`: 90 days
- `usage_ledger`: 7 years (audit/financial compliance)
- `enterprise_audit`: 1 year (or tenant-defined)
- `agent_artifacts`: 30 days

## 2. Legal-Hold Enforcement
When an organization or project is marked `LEGAL_HOLD`, retention pruning jobs skip deletions for all associated resources until the hold is lifted by a `SecurityAuditor`.
