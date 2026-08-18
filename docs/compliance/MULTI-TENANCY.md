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
3. **Database-Enforced RLS**:
   `enterprise_postgres.py` enables `FORCE ROW LEVEL SECURITY` on every
   tenant-scoped table and installs one policy per table comparing the
   row's `organization_id` to `current_setting('app.current_org', true)`;
   an unset variable fails closed. `FORCE` applies the policy even to the
   table owner, so RLS cannot be bypassed by the application role.
4. **Application-Layer Zero-Trust**:
   `RequestContext.validate_tenant_access(target_org_id)` intercepts all repository operations. Direct SQL queries and API requests referencing foreign tenant IDs fail closed.

> Scope note: RLS enforcement lives in the multi-tenant enterprise store.
> The single-tenant engineering/control-plane store
> (`postgres_engineering.py`) deliberately has no RLS statements — enabling
> RLS without policies would silently deny all rows to any non-owner role,
> and the store has no tenant column to key policies on. Multi-tenant
> isolation for engineering data is enforced at the application layer.
