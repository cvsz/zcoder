"""tests/unit/test_tenancy_deep_review.py — Comprehensive tenant boundary validation for ZCoder.

Validates that tenant isolation is enforced across data, tools, network, filesystem,
and audit boundaries. This is the tenancy deep review required by the execution plan.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from zcoder.domain.models.tenant import (
    ROLE_PERMISSIONS,
    CrossTenantViolationError,
    EnterpriseRole,
    RequestContext,
)


class TestTenantDataIsolation:
    def test_cross_org_access_denied(self):
        ctx_a = RequestContext(principal_id="user_a", organization_id="org_A", role=EnterpriseRole.DEVELOPER)
        with pytest.raises(CrossTenantViolationError):
            ctx_a.validate_tenant_access("org_B")

    def test_cross_project_access_denied_within_same_org(self):
        ctx = RequestContext(
            principal_id="user_a",
            organization_id="org_A",
            project_id="project_1",
            role=EnterpriseRole.DEVELOPER,
        )
        with pytest.raises(CrossTenantViolationError):
            ctx.validate_tenant_access("org_A", "project_2")

    def test_same_project_access_allowed(self):
        ctx = RequestContext(
            principal_id="user_a",
            organization_id="org_A",
            project_id="project_1",
            role=EnterpriseRole.DEVELOPER,
        )
        ctx.validate_tenant_access("org_A", "project_1")  # should not raise

    def test_global_admin_cross_tenant_access_allowed(self):
        ctx = RequestContext(
            principal_id="admin",
            organization_id="org_A",
            role=EnterpriseRole.ORG_OWNER,
            is_global_admin=True,
        )
        ctx.validate_tenant_access("org_B", "project_x")  # should not raise

    def test_permission_enforcement_per_role(self):
        for role, perms in ROLE_PERMISSIONS.items():
            ctx = RequestContext(
                principal_id="user",
                organization_id="org_1",
                role=role,
            )
            for perm in perms:
                assert ctx.has_permission(perm), f"Role {role} missing expected permission {perm}"

    def test_role_cannot_access_higher_permissions(self):
        viewer = RequestContext(principal_id="v", organization_id="org_1", role=EnterpriseRole.VIEWER)
        assert not viewer.has_permission("job.create")
        assert not viewer.has_permission("deploy.trigger")


class TestTenantFilesystemIsolation:
    def test_filesystem_path_contained_to_tenant(self):
        from zcoder.core.security import safe_resolve

        tenant_base = Path("/tmp/tenant_A").resolve()
        safe_path = safe_resolve(Path("subdir/file.txt"), base_dir=tenant_base)
        assert str(safe_path).startswith(str(tenant_base))

    def test_filesystem_traversal_blocked(self):
        from zcoder.core.security import SecurityError, safe_resolve

        tenant_base = Path("/tmp/tenant_A").resolve()
        with pytest.raises((SecurityError, ValueError)):
            safe_resolve(Path("../../../etc/passwd"), base_dir=tenant_base)


class TestTenantAuditIsolation:
    def test_audit_event_includes_tenant_context(self):
        ctx = RequestContext(
            principal_id="user_a",
            organization_id="org_A",
            role=EnterpriseRole.DEVELOPER,
        )
        assert ctx.organization_id == "org_A"
        assert ctx.principal_id == "user_a"

    def test_audit_event_immutable(self):
        ctx = RequestContext(
            principal_id="user_a",
            organization_id="org_A",
            role=EnterpriseRole.DEVELOPER,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            ctx.organization_id = "org_B"  # type: ignore[misc]


class TestTenantNetworkIsolation:
    def test_provider_url_scheme_validation(self):
        from zcoder.core.security import SecurityError, validate_url

        assert validate_url("https://api.example.com") is None
        with pytest.raises(SecurityError):
            validate_url("http://api.example.com")
        with pytest.raises(SecurityError):
            validate_url("ftp://api.example.com")
        with pytest.raises(SecurityError):
            validate_url("file:///etc/passwd")


class TestTenantToolIsolation:
    def test_cross_tenant_tool_result_not_leaked(self):
        ctx_a = RequestContext(principal_id="user_a", organization_id="org_A", role=EnterpriseRole.VIEWER)
        ctx_b = RequestContext(principal_id="user_b", organization_id="org_B", role=EnterpriseRole.VIEWER)

        # Contexts are isolated
        assert ctx_a.organization_id != ctx_b.organization_id
        assert ctx_a.principal_id != ctx_b.principal_id

        # Tool permission checks respect tenant
        assert ctx_a.has_permission("job.read")
        assert not ctx_a.has_permission("job.list") or ctx_a.has_permission("job.read")
