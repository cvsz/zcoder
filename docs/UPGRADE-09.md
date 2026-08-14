# UPGRADE-09: Production Deployment Stack & Reliability Engineering

## Summary of Upgrades
Upgrade-09 transforms ZCoder into a production-grade distributed system with measurable reliability properties:

1. **PostgreSQL Multi-Process Verification**:
   - `postgres_store.PostgresControlPlaneStore` utilizing `SELECT ... FOR UPDATE SKIP LOCKED` for atomic job claiming.
   - Proved with live 3-process worker concurrency across 30 jobs with zero duplicate claims and monotonic fencing tokens.
   - Worker crash recovery and stale write rejection verified.

2. **OIDC Authentication & Server-Side RBAC**:
   - `auth_oidc.py` provides OIDC JWT verification, role mapping (`VIEWER`, `OPERATOR`, `ADMIN`), and server-side RBAC enforcement.
   - Emergency Break-Glass administration with full audit logging.

3. **OpenTelemetry & Prometheus Observability**:
   - `observability_otel.py` exports bounded-cardinality metrics (`jobs_queued`, `worker_active`, `outbox_pending`, RED API metrics, backup freshness).
   - OTel trace spans for job lifecycle, GitHub API, and Anthropic invocations.

4. **Production Configuration Schema**:
   - `production_config.py` provides typed configuration sections, precedence resolution (defaults -> config file -> env -> CLI), and secret redaction.

5. **Disaster Recovery & Backup/PITR**:
   - `backup_restore.py` manages `pg_dump` snapshots, SHA256 manifests, retention policies, WAL archive configurations, and automated restore drills.
   - Complete standard operating procedures documented in `docs/DISASTER-RECOVERY.md`.

6. **Containerization & Helm Chart**:
   - Non-root hardened container execution.
   - Kubernetes deployments with `PodDisruptionBudget`, `NetworkPolicy`, `readinessProbe` / `livenessProbe`, and HPA.

7. **Test Results**:
   - **694 tests passed, 2 optional skipped**.
