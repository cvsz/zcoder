# ZCoder Enterprise Feature & Evidence Tier Matrix

| Enterprise Feature | Implemented | Evidence Tier | Automated Tests | Live Postgres Tested | Limitations |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Hard Multi-Tenancy** | YES | **E3 (System)** | `test_enterprise_suite.py` | YES | PostgreSQL multi-tenant schema |
| **Connection Pool Isolation**| YES | **E3 (System)** | `test_connection_pool_tenant_isolation_and_no_leakage` | YES | Transaction-local `SET LOCAL` |
| **Cross-Tenant Negative Matrix**| YES | **E3 (System)** | `test_cross_tenant_negative_matrix_job_isolation` | YES | Enforces zero cross-tenant access |
| **Enterprise Scoped RBAC** | YES | **E2 (Integration)**| `test_enterprise_suite.py` | YES | Scoped to Org and Project |
| **Policy-as-Code Engine** | YES | **E2 (Integration)**| `test_policy_as_code_engine_with_obligations` | N/A (In-Memory) | Supports obligations & explain mode |
| **Service Accounts & API Keys**| YES | **E3 (System)** | `test_scoped_api_keys_lifecycle` | YES | SHA-256 hashed with non-secret prefixes |
| **SCIM 2.0 Provisioning** | YES | **E2 (Integration)**| `test_scim_provisioning_and_non_destructive_deactivation` | N/A (Service) | RFC 7643 / 7644 Users & Groups |
| **Immutable Usage Ledger**| YES | **E3 (System)** | `test_usage_metering_deduplication` | YES | Deduplicated by event key |
| **Quota Atomic Reservations**| YES | **E3 (System)** | `test_quota_atomic_reservation_race_prevention` | YES | Row-level locking prevents overspend |
| **Enterprise Audit Log** | YES | **E3 (System)** | `test_enterprise_audit_log_and_export` | YES | Append-only with JSONL export |
