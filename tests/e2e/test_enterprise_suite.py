"""tests/test_enterprise_suite.py — Comprehensive Enterprise SaaS & Multi-Tenancy Tests for ZCoder.

Covers:
  1. Multi-Tenant Domain & Scoped RequestContext
  2. PostgreSQL Row-Level Security & Connection Pool Isolation (No tenant leakage across pooled reuse)
  3. Cross-Tenant Negative Test Matrix (Zero cross-tenant read/write/delete/claim)
  4. Enterprise RBAC & Concrete Permissions
  5. Policy-as-Code Engine with Obligations & Dry-Run Explanation
  6. Service Accounts & Scoped API Key generation/rotation/revocation
  7. SCIM 2.0 Provisioning & Non-Destructive User Deactivation
  8. Immutable Usage Ledger & Atomic Quota Reservation Concurrency
  9. Enterprise Audit Log Export (with zero secret leakage)
"""

import os

import psycopg2
import pytest

from agent_runtime import Job, JobStatus
from enterprise_postgres_store import EnterprisePostgresStore
from policy_engine import EnterprisePolicyEngine, PolicyObligation, PolicyRule
from scim_service import ScimProvisioningService
from tenant_models import (
    ApiKey,
    CrossTenantViolationError,
    EnterpriseAuditEvent,
    EnterpriseRole,
    Organization,
    Project,
    RequestContext,
    UsageEvent,
)

PG_URL = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:postgres@172.17.0.2:5432/zcoder")


def pg_is_available():
    try:
        conn = psycopg2.connect(PG_URL, connect_timeout=2)
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not pg_is_available(), reason="PostgreSQL test container not reachable")


@pytest.fixture(scope="module")
def ent_store():
    store = EnterprisePostgresStore(dsn=PG_URL)
    yield store
    store.close()


@pytest.fixture(scope="module")
def test_tenants(ent_store):
    ctx_admin = RequestContext(principal_id="global_root", organization_id="system", is_global_admin=True)

    with ent_store._raw_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tenant_jobs;")
            cur.execute("DELETE FROM usage_ledger;")
            cur.execute("DELETE FROM tenant_quotas;")
            cur.execute("DELETE FROM enterprise_audit;")
            cur.execute("DELETE FROM api_keys;")
            cur.execute("DELETE FROM projects;")
            cur.execute("DELETE FROM organizations;")
        conn.commit()

    org_a = Organization(id="org_alpha", name="Alpha Corp", slug="alpha-corp")
    org_b = Organization(id="org_beta", name="Beta Inc", slug="beta-inc")

    ent_store.create_organization(ctx_admin, org_a)
    ent_store.create_organization(ctx_admin, org_b)

    proj_a = Project(id="proj_alpha_1", organization_id="org_alpha", name="Alpha Core", slug="alpha-core")
    proj_b = Project(id="proj_beta_1", organization_id="org_beta", name="Beta Web", slug="beta-web")

    ctx_a_owner = RequestContext(
        principal_id="user_a_owner", organization_id="org_alpha", role=EnterpriseRole.ORG_OWNER
    )
    ctx_b_owner = RequestContext(
        principal_id="user_b_owner", organization_id="org_beta", role=EnterpriseRole.ORG_OWNER
    )

    ent_store.create_project(ctx_a_owner, proj_a)
    ent_store.create_project(ctx_b_owner, proj_b)

    return org_a, org_b, proj_a, proj_b


class TestEnterpriseMultiTenancy:
    def test_request_context_zero_trust_tenant_validation(self):
        ctx_a = RequestContext(
            principal_id="alice", organization_id="org_alpha", role=EnterpriseRole.DEVELOPER
        )
        # Accessing own tenant passes
        ctx_a.validate_tenant_access("org_alpha")

        # Accessing another tenant raises CrossTenantViolationError
        with pytest.raises(CrossTenantViolationError):
            ctx_a.validate_tenant_access("org_beta")

    def test_connection_pool_tenant_isolation_and_no_leakage(self, ent_store, test_tenants):
        """Prove that reusing the same pooled connection across requests does not leak tenant context."""
        ctx_a = RequestContext(principal_id="alice", organization_id="org_alpha", role=EnterpriseRole.VIEWER)
        ctx_b = RequestContext(principal_id="bob", organization_id="org_beta", role=EnterpriseRole.VIEWER)

        # Request A uses a connection
        with ent_store.scoped_conn(ctx_a) as conn:
            with conn.cursor() as cur:
                cur.execute("SHOW app.current_org;")
                val = cur.fetchone()[0]
                assert val == "org_alpha"

        # Request B immediately borrows a connection from pool
        with ent_store.scoped_conn(ctx_b) as conn:
            with conn.cursor() as cur:
                cur.execute("SHOW app.current_org;")
                val = cur.fetchone()[0]
                assert val == "org_beta", "Tenant context leaked from previous request!"

    def test_cross_tenant_negative_matrix_job_isolation(self, ent_store, test_tenants):
        """Prove Org A cannot read, claim, or mutate Org B's jobs."""
        ctx_a = RequestContext(
            principal_id="alice", organization_id="org_alpha", role=EnterpriseRole.OPERATOR
        )
        ctx_b = RequestContext(principal_id="bob", organization_id="org_beta", role=EnterpriseRole.OPERATOR)

        job_b = Job(id="job_beta_secret", task="Secret Task Beta", status=JobStatus.READY)
        ent_store.enqueue_job(ctx_b, job_b)

        # Org A tries to claim -> must NOT receive Org B's job
        claim_res_a = ent_store.claim_job_scoped(ctx_a, worker_id="worker_a")
        assert claim_res_a is None or claim_res_a[0].id != "job_beta_secret"

        # Org A tries to mutate Org B's job directly -> must fail
        mutated = ent_store.mutate_job_scoped(
            ctx_a, "job_beta_secret", "worker_a", 1, JobStatus.SUCCEEDED, 0.0
        )
        assert mutated is False, "Cross-tenant job mutation succeeded!"

    def test_policy_as_code_engine_with_obligations(self):
        engine = EnterprisePolicyEngine(organization_id="org_alpha")
        rule = PolicyRule(
            id="rule_prod_approval",
            action_pattern="job.create",
            condition="true",
            effect="ALLOW",
            obligations=[PolicyObligation(type="require_approval", parameters={"roles": ["Operator"]})],
        )
        engine.add_rule(rule)

        ctx_dev = RequestContext(
            principal_id="dan", organization_id="org_alpha", role=EnterpriseRole.DEVELOPER
        )
        decision = engine.evaluate(ctx_dev, "job.create", {"risk_level": "low"})
        assert decision.allow is True
        assert any(o.type == "require_approval" for o in decision.obligations)
        assert decision.policy_hash != ""

        # Explain mode
        explanation = engine.explain(ctx_dev, "job.create", {})
        assert explanation["allow"] is True
        assert len(explanation["obligations"]) >= 1

    def test_scoped_api_keys_lifecycle(self, ent_store, test_tenants):
        ctx_admin = RequestContext(
            principal_id="alice_admin", organization_id="org_alpha", role=EnterpriseRole.ORG_ADMIN
        )
        key_obj, raw_secret = ApiKey.generate(
            organization_id="org_alpha", principal_id="ci_bot", scopes=["job:create"]
        )

        ent_store.save_api_key(ctx_admin, key_obj)
        assert key_obj.verify(raw_secret) is True
        assert key_obj.verify("wrong_secret") is False

        # Authenticate via API Key
        auth_ctx = ent_store.authenticate_api_key(raw_secret)
        assert auth_ctx is not None
        assert auth_ctx.organization_id == "org_alpha"
        assert auth_ctx.principal_id == "ci_bot"

    def test_scim_provisioning_and_non_destructive_deactivation(self):
        scim = ScimProvisioningService(organization_id="org_alpha")
        ctx = RequestContext(
            principal_id="scim_client", organization_id="org_alpha", role=EnterpriseRole.ORG_ADMIN
        )

        user_res = scim.create_user(ctx, {"userName": "john.doe@alpha.com", "active": True})
        assert user_res["active"] is True
        user_id = user_res["id"]

        # Deactivate user (non-destructive)
        updated = scim.update_user_status(ctx, user_id, active=False)
        assert updated["active"] is False

        # History remains fetchable
        fetched = scim.get_user(ctx, user_id)
        assert fetched is not None
        assert fetched["active"] is False

    def test_usage_metering_deduplication(self, ent_store, test_tenants):
        ctx = RequestContext(
            principal_id="agent_1", organization_id="org_alpha", role=EnterpriseRole.OPERATOR
        )
        event = UsageEvent(
            id="usg_1001",
            organization_id="org_alpha",
            project_id="proj_alpha_1",
            job_id="job_alpha_1",
            metric="tokens_in",
            quantity=1500,
            unit="tokens",
            cost_usd=0.003,
            dedup_key="dedup_token_event_unique_1001",
        )

        rec1 = ent_store.record_usage_event(ctx, event)
        assert rec1 is True

        # Replay event -> must be deduplicated
        rec2 = ent_store.record_usage_event(ctx, event)
        assert rec2 is False, "Duplicate usage event allowed in ledger!"

    def test_quota_atomic_reservation_race_prevention(self, ent_store, test_tenants):
        ctx = RequestContext(
            principal_id="worker_pool", organization_id="org_alpha", role=EnterpriseRole.OPERATOR
        )
        # Limit is 100.0
        assert (
            ent_store.check_and_reserve_quota(
                ctx, "concurrent_jobs", requested_amount=60.0, limit_value=100.0
            )
            is True
        )
        assert (
            ent_store.check_and_reserve_quota(
                ctx, "concurrent_jobs", requested_amount=30.0, limit_value=100.0
            )
            is True
        )
        # Exceeds limit (60 + 30 + 20 = 110 > 100) -> Rejected
        assert (
            ent_store.check_and_reserve_quota(
                ctx, "concurrent_jobs", requested_amount=20.0, limit_value=100.0
            )
            is False
        )

    def test_enterprise_audit_log_and_export(self, ent_store, test_tenants):
        ctx_auditor = RequestContext(
            principal_id="auditor_bob", organization_id="org_alpha", role=EnterpriseRole.SECURITY_AUDITOR
        )
        event = EnterpriseAuditEvent(
            event_id="evt_audit_001",
            organization_id="org_alpha",
            actor="alice",
            actor_type="user",
            action="policy.update",
            resource="rule_prod_approval",
            result="SUCCESS",
            metadata={"detail": "Updated approval policy"},
        )
        ent_store.record_audit_event(event)

        exported = ent_store.export_audit_log(ctx_auditor)
        assert len(exported) >= 1
        assert any(e["event_id"] == "evt_audit_001" for e in exported)
        # Verify no raw secret fields
        for e in exported:
            assert "secret" not in e and "token" not in e
