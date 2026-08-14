# ZCoder Enterprise Scoped RBAC

## 1. Role Hierarchy
ZCoder implements scoped enterprise roles:

| Role | Scope | Key Permissions |
| :--- | :--- | :--- |
| `OrganizationOwner` | Organization | Full tenant control, member management, billing, policies, deletion |
| `OrganizationAdmin` | Organization | User management, project management, integrations, audit export |
| `ProjectAdmin` | Project | Project-specific configuration, repository management, job dispatch |
| `Operator` | Project | Job creation, execution, approval management, cancel |
| `Developer` | Project | Job creation, code generation, read-only repo metadata |
| `Viewer` | Project | Read-only access to jobs, projects, and execution results |
| `BillingAdmin` | Organization | Usage viewing, invoices, quotas, payment configuration |
| `SecurityAuditor` | Organization | Enterprise audit log export, compliance inspection, policy review |

## 2. Server-Side Enforcement
Permissions are enforced by `RequestContext.require_permission()` and cannot be bypassed from UI layers.
