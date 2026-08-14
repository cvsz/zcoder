# Runbook: Quota Exceeded & Concurrency Incident

## Severity: Low to Medium
**Condition**: Jobs queued in `WAITING_BUDGET` or rejected with quota errors.

## Diagnostic Steps
1. Query current organization spend vs limit:
   ```sql
   SELECT metric, current_value, limit_value FROM tenant_quotas WHERE organization_id = '<org_id>';
   ```
2. Verify if in-flight reserved budget needs manual release or if organization needs an approved quota increase.
