"""tests/test_upgrade11_evidence_suite.py — Upgrade-11 Comprehensive Verification Suite.

Tests:
  1. Version single source of truth across main.py and pyproject.toml
  2. Real PostgreSQL Tenant Isolation & Connection Pool Safety (against live Postgres container)
  3. Strict Fail-Closed behavior on missing/malformed tenant context
  4. Multi-Region Data Residency policy evaluation & failover guarantees
  5. Compliance Control Catalog with evidence TTL & expiration (STALE detection)
"""

import os
import time

import psycopg2
import pytest

import main
from zcoder.domain.models.residency import OrganizationResidencyPolicy, ResidencyScheduler
from zcoder.domain.models.tenant import CrossTenantViolationError, EnterpriseRole, RequestContext
from zcoder.infrastructure.stores.enterprise_postgres import EnterprisePostgresStore
from zcoder.services.compliance_evidence import ComplianceCatalog, ControlStatus

PG_URL = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:postgres@172.17.0.2:5432/zcoder")


def test_version_single_source_of_truth():
    """Verify that main.py version matches pyproject.toml version exactly."""
    try:
        import tomllib

        with open("pyproject.toml", "rb") as f:
            pyproj = tomllib.load(f)
        toml_ver = pyproj["project"]["version"]
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore

            with open("pyproject.toml", "rb") as f:
                pyproj = tomllib.load(f)
            toml_ver = pyproj["project"]["version"]
        except ImportError:
            import re

            with open("pyproject.toml", encoding="utf-8") as f:
                content = f.read()
            match = re.search(r'version\s*=\s*"([^"]+)"', content)
            toml_ver = match.group(1) if match else None

    assert main.VERSION == toml_ver == "1.41.0"


def test_data_residency_policy_evaluation():
    scheduler = ResidencyScheduler()
    policy = OrganizationResidencyPolicy(
        organization_id="org_eu_bank",
        home_region="eu-west-1",
        allowed_worker_regions={"eu-west-1"},
        allowed_provider_inference_regions={"eu", "global"},
    )
    scheduler.set_policy(policy)

    # Compliant placement
    ok, msg = scheduler.evaluate_placement("org_eu_bank", "eu-west-1", "global")
    assert ok is True

    # Non-compliant worker region rejected
    not_ok, msg = scheduler.evaluate_placement("org_eu_bank", "us-east-1", "global")
    assert not_ok is False
    assert "not in allowed worker regions" in msg

    # Non-compliant provider inference geo rejected
    not_ok_geo, msg_geo = scheduler.evaluate_placement("org_eu_bank", "eu-west-1", "us")
    assert not_ok_geo is False
    assert "not in allowed inference regions" in msg_geo


def test_residency_safe_failover():
    scheduler = ResidencyScheduler()
    policy = OrganizationResidencyPolicy(
        organization_id="org_strict_eu",
        home_region="eu-west-1",
        allowed_worker_regions={"eu-west-1"},
    )
    scheduler.set_policy(policy)

    # When eu-west-1 fails and no other EU region is allowed -> must PAUSE, never violate residency
    target_region, reason = scheduler.failover_placement("org_strict_eu", failed_worker_region="eu-west-1")
    assert target_region is None
    assert "PAUSED" in reason


def test_compliance_evidence_freshness_and_expiration():
    catalog = ComplianceCatalog()
    catalog.record_evidence("TI-01", is_effective=True, summary="Automated RLS cross-tenant tests passed")
    assert catalog.get_control_status("TI-01") == ControlStatus.EFFECTIVE

    # Simulate expired evidence (TTL exceeded)
    ctrl = catalog.controls["TI-01"]
    ctrl.evidence_ttl_seconds = 0.01
    time.sleep(0.02)
    assert catalog.get_control_status("TI-01") == ControlStatus.STALE


def test_missing_tenant_context_fails_closed():
    """Verify that attempting an operation with empty/mismatched tenant context fails closed."""
    ctx_empty = RequestContext(principal_id="attacker", organization_id="", role=EnterpriseRole.DEVELOPER)
    with pytest.raises(CrossTenantViolationError):
        ctx_empty.validate_tenant_access("org_target")


# ─── Live PostgreSQL Tests ───────────────────────────────────────────────────


def pg_is_live():
    try:
        conn = psycopg2.connect(PG_URL, connect_timeout=2)
        conn.close()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not pg_is_live(), reason="PostgreSQL test instance required")
def test_real_postgres_connection_pool_isolation():
    store = EnterprisePostgresStore(dsn=PG_URL)
    ctx_a = RequestContext(principal_id="alice", organization_id="org_alpha", role=EnterpriseRole.VIEWER)
    ctx_b = RequestContext(principal_id="bob", organization_id="org_beta", role=EnterpriseRole.VIEWER)

    with store.scoped_conn(ctx_a) as conn:
        with conn.cursor() as cur:
            cur.execute("SHOW app.current_org;")
            assert cur.fetchone()[0] == "org_alpha"

    with store.scoped_conn(ctx_b) as conn:
        with conn.cursor() as cur:
            cur.execute("SHOW app.current_org;")
            assert cur.fetchone()[0] == "org_beta"

    store.close()
