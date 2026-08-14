# ZCoder Enterprise Multi-Tenancy Architecture & Hard Isolation

## 1. Tenant Hierarchy
ZCoder enforces a strict 4-level organizational hierarchy:
```text
Platform (Global Admin)
  └── Organization (Tenant Security & Billing Boundary)
        └── Project (Logical Subdivision / Workspace)
              ├── Repositories & Fleet Integrations
              ├── Jobs & Autonomous Agent Executions
              ├── Fine-grained Policies
              └── Usage Ledger & Quotas
```

## 2. PostgreSQL Row-Level Security & Connection Pool Isolation
1. **Transaction-Local Tenant Context**:
   Every database query executed by the API or workers sets `SET LOCAL app.current_org = '<org_id>';` inside an explicit transaction block.
2. **Post-Transaction Pool Reset**:
   When connections are returned to the pool, `RESET app.current_org;` is executed to prevent cross-request tenant context leakage.
3. **Application-Layer Zero-Trust**:
   `RequestContext.validate_tenant_access(target_org_id)` intercepts all repository operations. Direct SQL queries and API requests referencing foreign tenant IDs fail closed.
