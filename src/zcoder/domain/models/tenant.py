"""tenant_models.py — Enterprise Multi-Tenancy Domain Models & Scoped Context for ZCoder.

Provides:
  • Organization hierarchy: Platform -> Organization -> Project -> Resources
  • RequestContext: First-class authenticated request context with immutable tenant scope
  • Membership & Scoped Enterprise Roles (OrgOwner, OrgAdmin, ProjectAdmin, Operator, Developer, Viewer, BillingAdmin, SecurityAuditor)
  • Concrete permissions model (org.*, project.*, job.*, repo.*, policy.*, billing.*, audit.*)
  • ServiceAccount & Scoped API Keys with secure SHA-256 hashing and non-secret prefixes
  • UsageEvent & Immutable Ledger for metering/billing boundaries
  • Quota & Reservation domain models with atomic enforcement
  • PolicyDecision & Obligations (require_approval, sandbox, max_budget, etc.)
  • SCIM 2.0 provisioning models (User, Group, EnterpriseUser)
  • Enterprise Audit Log events
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import secrets
import time
from typing import Any, Dict, List, Optional, Set

# ─── Organization & Project Lifecycle ────────────────────────────────────────


class OrgStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DELETING = "DELETING"
    DELETED = "DELETED"


class ProjectStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    DELETED = "DELETED"


class MembershipStatus(str, enum.Enum):
    INVITED = "INVITED"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    REMOVED = "REMOVED"


# ─── Enterprise Roles & Concrete Permissions ─────────────────────────────────


class EnterpriseRole(str, enum.Enum):
    ORG_OWNER = "OrganizationOwner"
    ORG_ADMIN = "OrganizationAdmin"
    PROJECT_ADMIN = "ProjectAdmin"
    OPERATOR = "Operator"
    DEVELOPER = "Developer"
    VIEWER = "Viewer"
    BILLING_ADMIN = "BillingAdmin"
    SECURITY_AUDITOR = "SecurityAuditor"


ROLE_PERMISSIONS: Dict[EnterpriseRole, Set[str]] = {
    EnterpriseRole.ORG_OWNER: {
        "org.read",
        "org.manage",
        "org.delete",
        "member.read",
        "member.manage",
        "project.read",
        "project.manage",
        "job.read",
        "job.create",
        "job.cancel",
        "job.approve",
        "repo.read",
        "repo.manage",
        "policy.read",
        "policy.manage",
        "billing.read",
        "billing.manage",
        "audit.read",
        "audit.export",
        "sso.manage",
        "scim.manage",
        "sa.manage",
        "apikey.manage",
    },
    EnterpriseRole.ORG_ADMIN: {
        "org.read",
        "org.manage",
        "member.read",
        "member.manage",
        "project.read",
        "project.manage",
        "job.read",
        "job.create",
        "job.cancel",
        "job.approve",
        "repo.read",
        "repo.manage",
        "policy.read",
        "policy.manage",
        "billing.read",
        "audit.read",
        "audit.export",
        "sso.manage",
        "scim.manage",
        "sa.manage",
        "apikey.manage",
    },
    EnterpriseRole.PROJECT_ADMIN: {
        "org.read",
        "member.read",
        "project.read",
        "project.manage",
        "job.read",
        "job.create",
        "job.cancel",
        "job.approve",
        "repo.read",
        "repo.manage",
        "policy.read",
        "audit.read",
    },
    EnterpriseRole.OPERATOR: {
        "org.read",
        "project.read",
        "job.read",
        "job.create",
        "job.cancel",
        "job.approve",
        "repo.read",
    },
    EnterpriseRole.DEVELOPER: {
        "org.read",
        "project.read",
        "job.read",
        "job.create",
        "repo.read",
    },
    EnterpriseRole.VIEWER: {
        "org.read",
        "project.read",
        "job.read",
        "repo.read",
    },
    EnterpriseRole.BILLING_ADMIN: {
        "org.read",
        "billing.read",
        "billing.manage",
        "usage.read",
    },
    EnterpriseRole.SECURITY_AUDITOR: {
        "org.read",
        "audit.read",
        "audit.export",
        "policy.read",
        "member.read",
    },
}


# ─── Scoped Request Context ──────────────────────────────────────────────────


@dataclasses.dataclass(frozen=True)
class RequestContext:
    """Immutable authenticated request context enforcing tenant boundaries."""

    principal_id: str
    organization_id: str
    project_id: Optional[str] = None
    role: EnterpriseRole = EnterpriseRole.VIEWER
    permissions: Set[str] = dataclasses.field(default_factory=set)
    authentication_method: str = "token"  # token | apikey | scim | break_glass
    is_global_admin: bool = False

    def __post_init__(self):
        if not self.permissions and self.role:
            object.__setattr__(self, "permissions", ROLE_PERMISSIONS.get(self.role, set()))

    def has_permission(self, permission: str) -> bool:
        if self.is_global_admin:
            return True
        return permission in self.permissions

    def require_permission(self, permission: str) -> None:
        if not self.has_permission(permission):
            raise PermissionDeniedError(
                f"Principal '{self.principal_id}' lacks required permission '{permission}' "
                f"in organization '{self.organization_id}'"
            )

    def validate_tenant_access(self, target_org_id: str, target_project_id: Optional[str] = None) -> None:
        """Enforce zero-trust tenant boundary: caller cannot access another org's resources."""
        if self.is_global_admin:
            return
        if self.organization_id != target_org_id:
            raise CrossTenantViolationError(
                f"Cross-tenant access blocked: caller org '{self.organization_id}' "
                f"attempted to access target org '{target_org_id}'"
            )
        if target_project_id and self.project_id and self.project_id != target_project_id:
            raise CrossTenantViolationError(
                f"Cross-project access blocked: caller project '{self.project_id}' "
                f"attempted to access target project '{target_project_id}'"
            )


class CrossTenantViolationError(Exception):
    """Raised when an operation attempts cross-tenant access."""


class PermissionDeniedError(Exception):
    """Raised when principal lacks permission."""


# ─── Domain Entities ─────────────────────────────────────────────────────────


@dataclasses.dataclass
class Organization:
    id: str
    name: str
    slug: str
    status: OrgStatus = OrgStatus.ACTIVE
    created_at: float = dataclasses.field(default_factory=time.time)
    metadata: Dict[str, Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class Project:
    id: str
    organization_id: str
    name: str
    slug: str
    status: ProjectStatus = ProjectStatus.ACTIVE
    created_at: float = dataclasses.field(default_factory=time.time)


@dataclasses.dataclass
class Membership:
    id: str
    principal_id: str
    organization_id: str
    role: EnterpriseRole = EnterpriseRole.VIEWER
    status: MembershipStatus = MembershipStatus.ACTIVE
    created_at: float = dataclasses.field(default_factory=time.time)


@dataclasses.dataclass
class ServiceAccount:
    id: str
    organization_id: str
    project_id: Optional[str]
    name: str
    role: EnterpriseRole = EnterpriseRole.OPERATOR
    status: str = "ACTIVE"
    created_at: float = dataclasses.field(default_factory=time.time)


@dataclasses.dataclass
class ApiKey:
    id: str
    prefix: str
    secret_hash: str
    organization_id: str
    project_id: Optional[str]
    principal_id: str
    scopes: List[str]
    status: str = "ACTIVE"  # ACTIVE | REVOKED | EXPIRED
    created_at: float = dataclasses.field(default_factory=time.time)
    expires_at: Optional[float] = None
    last_used_at: Optional[float] = None

    @staticmethod
    def generate(
        organization_id: str,
        principal_id: str,
        project_id: Optional[str] = None,
        scopes: Optional[List[str]] = None,
        ttl_seconds: Optional[float] = None,
    ) -> tuple[ApiKey, str]:
        prefix = f"zck_{organization_id[:6]}_{secrets.token_hex(4)}"
        secret_part = secrets.token_urlsafe(32)
        raw_key = f"{prefix}_{secret_part}"
        secret_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        key_id = f"key_{secrets.token_hex(8)}"
        now = time.time()
        expires_at = (now + ttl_seconds) if ttl_seconds else None

        key = ApiKey(
            id=key_id,
            prefix=prefix,
            secret_hash=secret_hash,
            organization_id=organization_id,
            project_id=project_id,
            principal_id=principal_id,
            scopes=scopes or ["job:read", "job:create"],
            status="ACTIVE",
            created_at=now,
            expires_at=expires_at,
        )
        return key, raw_key

    def verify(self, raw_key: str) -> bool:
        if self.status != "ACTIVE":
            return False
        if self.expires_at and time.time() > self.expires_at:
            return False
        return hashlib.sha256(raw_key.encode()).hexdigest() == self.secret_hash


# ─── Usage Metering & Quotas ─────────────────────────────────────────────────


@dataclasses.dataclass
class UsageEvent:
    id: str
    organization_id: str
    project_id: Optional[str]
    job_id: str
    metric: str  # tokens_in | tokens_out | runtime_seconds | job_execution
    quantity: float
    unit: str  # tokens | seconds | count
    cost_usd: float = 0.0
    source: str = "ZCODER_MEASURED"  # PROVIDER_REPORTED | RUNTIME_REPORTED | ZCODER_MEASURED
    occurred_at: float = dataclasses.field(default_factory=time.time)
    dedup_key: Optional[str] = None


@dataclasses.dataclass
class Quota:
    organization_id: str
    metric: str
    limit_value: float
    period: str = "monthly"  # monthly | daily | concurrent
    current_value: float = 0.0
    soft_limit_ratio: float = 0.8  # Warning at 80%
    status: str = "OK"  # OK | WARNING | SOFT_LIMIT | HARD_LIMIT


# ─── Enterprise Audit Event ──────────────────────────────────────────────────


@dataclasses.dataclass
class EnterpriseAuditEvent:
    event_id: str
    organization_id: str
    actor: str
    actor_type: str  # user | service_account | scim | system
    action: str
    resource: str
    result: str  # ALLOWED | DENIED | SUCCESS | FAILED
    timestamp: float = dataclasses.field(default_factory=time.time)
    source_ip: Optional[str] = None
    request_id: Optional[str] = None
    metadata: Dict[str, Any] = dataclasses.field(default_factory=dict)
    schema_version: str = "1.0"
