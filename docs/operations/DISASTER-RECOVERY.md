# ZCoder Disaster Recovery (DR) & Incident Response Runbook

## Overview
This runbook provides actionable standard operating procedures (SOP) for recovering the ZCoder control plane, worker fleet, and underlying databases during production outages.

---

### 1. Database Outage / Loss (`DB-DOWN`)
**Symptoms**: API returns 503 / DB connection timeout; workers log `PostgreSQL connection failed`.

**First Diagnostic Steps**:
1. Check database connectivity: `python main.py doctor --json`
2. Check PostgreSQL service status / pod logs: `kubectl logs -l app.kubernetes.io/name=postgres`
3. Verify connection pool metrics: `curl -s http://localhost:9090/metrics | grep zcoder_db_pool`

**Recovery Procedures**:
- **Transient Connection Loss**: PostgreSQL connection pool auto-reconnects with exponential backoff.
- **Catastrophic Database Loss (Restore Drill)**:
  1. Spin up a clean PostgreSQL instance.
  2. Locate latest verified backup: `ls -lt /var/backups/zcoder/pgdump_*.sql.gz | head -n 1`
  3. Execute restore drill command:
     ```bash
     python -c "from backup_restore import BackupManager; bm = BackupManager(); print(bm.run_restore_drill('latest_backup_id'))"
     ```
  4. Run database schema migration / verification: `python main.py --health-check-deep`

---

### 2. Worker Fleet Loss / Pod Termination (`WORKER-LOSS`)
**Symptoms**: `zcoder_worker_active` drops to 0; `zcoder_jobs_queued` rises steadily.

**Recovery Procedures**:
1. Leases on in-flight jobs will expire automatically after configured `lease_duration_seconds` (default 120s).
2. The control plane reconciler marks expired RUNNING jobs back to READY.
3. Newly launched replacement worker pods register into `worker_registry` and atomically claim READY jobs with new monotonic fencing tokens.
4. If a previously crashed worker resumes, its writes are rejected by database fencing token checks.

---

### 3. API Control Plane Crash (`API-DOWN`)
**Symptoms**: Ingress health check `/health/live` fails; 502 Bad Gateway at ingress.

**Recovery Procedures**:
1. Workers continue processing claimed jobs independently using durable PostgreSQL state.
2. Ingress routes traffic to surviving API replicas.
3. Restart or roll API deployment: `kubectl rollout restart deployment/zcoder-api`.
4. Check readiness probe `/health/ready` before receiving traffic.

---

### 4. GitHub / Anthropic Outage Handling
**GitHub Outage**: Outbox messages buffer mutations with exponential backoff up to 5 attempts before DEAD-lettering. Replay via `POST /api/v1/outbox/retry`.
**Anthropic Outage**: Jobs enter `RETRYING` state with bounded jittered backoff; no infinite token consumption loops.
