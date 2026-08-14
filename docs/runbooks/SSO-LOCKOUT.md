# Runbook: SSO Lockout Incident Response

## Severity: High
**Condition**: Organization members unable to authenticate via external IdP or misconfigured JWKS endpoint.

## Diagnostic Steps
1. Verify IdP metadata discovery endpoint reachability.
2. Check JWKS certificate validity and expiration.
3. Validate client ID and secret references in secret manager.

## Resolution
1. Use emergency **Break-Glass Administration** (`ZCODER_BREAK_GLASS_SECRET`) to log in and repair the IdP configuration.
2. Verify token issuance and retry SSO login flow.
