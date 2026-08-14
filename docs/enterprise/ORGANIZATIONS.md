# ZCoder Organization Management Guide

## 1. Organization Lifecycle
Organizations are the primary administrative, security, and billing boundary in ZCoder:
- `ACTIVE`: Normal operational state. Users can submit jobs, access projects, and manage integrations.
- `SUSPENDED`: Read-only state due to quota breach or administrative action. Running jobs finish; new jobs are blocked.
- `DELETING`: Asynchronous tenant deletion lifecycle active. Resources entering retention/grace period.
- `DELETED`: Cryptographically erased or scrubbed.

## 2. API & Management
```python
from tenant_models import Organization, OrgStatus, RequestContext
from enterprise_postgres_store import EnterprisePostgresStore

# Creating an organization
ctx_admin = RequestContext(principal_id="admin_1", organization_id="system", is_global_admin=True)
org = Organization(id="org_enterprise_1", name="Acme Corp", slug="acme-corp", status=OrgStatus.ACTIVE)
store.create_organization(ctx_admin, org)
```
