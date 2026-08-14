# Runbook: API Key Compromise Response

## Severity: High
**Condition**: Suspected leaked API key in public repositories, logs, or unapproved network traces.

## Containment Procedure
1. Locate key record using the non-secret prefix:
   ```sql
   SELECT id, organization_id, status FROM api_keys WHERE prefix = '<prefix>';
   ```
2. Instantly revoke the compromised key:
   ```sql
   UPDATE api_keys SET status = 'REVOKED' WHERE prefix = '<prefix>';
   ```
3. Generate replacement key and audit recent executions performed under the compromised key identifier.
