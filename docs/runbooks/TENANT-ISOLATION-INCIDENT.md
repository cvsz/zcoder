# Runbook: Tenant Isolation Incident Response

## Severity: P0 / Critical
**Condition**: Suspected cross-tenant data access, leaked session context, or RLS bypass.

## Diagnostic Steps
1. Verify database session context settings:
   ```sql
   SHOW app.current_org;
   ```
2. Inspect application error logs for `CrossTenantViolationError` exceptions.
3. Run the automated tenant isolation suite:
   ```bash
   python3 -m pytest tests/test_enterprise_suite.py -k "test_cross_tenant_negative_matrix_job_isolation"
   ```

## Containment Actions
1. Immediately suspend suspected compromised organization:
   ```sql
   UPDATE organizations SET status = 'SUSPENDED' WHERE id = '<org_id>';
   ```
2. Invalidate all active sessions and rotate API keys for affected tenants.
