# Runbook: SCIM 2.0 Provisioning Failure

## Severity: Medium
**Condition**: External IdP fails to sync users/groups or returns 401/403 on SCIM endpoints.

## Diagnostic Steps
1. Verify SCIM bearer token validity.
2. Check SCIM audit log for parsing errors or unsupported attributes.
3. Validate user payload against RFC 7643 schema.

## Resolution
1. Rotate SCIM API token via administrative console.
2. Re-trigger full reconciliation sync from identity provider.
