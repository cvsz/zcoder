# UPGRADE-05: Enterprise RBAC, SCIM Provisioning & OIDC Identity

## Overview
Upgrade-05 introduces enterprise identity, automated directory synchronization, and role-based access control:

1. **OIDC Identity Federation:**
   - JWT validation, claims mapping, and integration with enterprise identity providers (Okta, Azure AD, Keycloak).

2. **SCIM 2.0 Provisioning:**
   - Full implementation of `/v2/Users` and `/v2/Groups` endpoints for automated onboarding and offboarding.

3. **Hierarchical RBAC Model:**
   - Roles (`ADMIN`, `OPERATOR`, `DEVELOPER`, `VIEWER`) enforced across both API endpoints and local CLI operations.
