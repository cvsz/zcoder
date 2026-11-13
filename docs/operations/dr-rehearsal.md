# Disaster-Recovery Rehearsal Runbook

## Purpose and scope

This document is the **procedure** for the quarterly ZCoder disaster-recovery
rehearsal: it exercises backup creation, restore into an isolated target,
state verification, retention policy observation, and WAL archiving readiness
using `BackupManager` (`src/zcoder/services/backup_restore.py`).

**Evidence caveat (read before filing results):** this document describes the
PROCEDURE only. Evidence produced by following it satisfies the
**Operations / DR-rehearsal row** of the final-release gate matrix
(`exec-planning.md` §6) **only when the rehearsal is executed against the
exact release-candidate SHA** — per the release-candidate immutability rule
(`exec-planning.md` §2, rule 12), any code/config/dependency change after the
run invalidates the evidence and requires re-execution on a new RC. A rehearsal
performed against any other commit is practice only and must not be recorded
as release evidence.

Related documents:

| Document | Relationship |
|---|---|
| `docs/operations/DISASTER-RECOVERY.md` | Incident-response SOPs during a live outage (`DB-DOWN`, `WORKER-LOSS`, `API-DOWN`) |
| `docs/operations/deployment.md` | Deployment, health checks, and container rollback |
| `docs/zpitr-implementation.md` | **zPITR containerized Point-in-Time Recovery service** (continuous WAL streaming + automated restore drill + Release Gate evidence emission) |
| `deploy/docker/zpitr/` | zPITR Docker service definition (Dockerfile, entrypoint, scripts, Compose) |
| `exec-planning.md` §6 | Release gates this evidence feeds ("backup/restore, rollback, migration rehearsal, and disaster-recovery evidence") |

---

## zPITR — Containerized PITR Drill Service (New)

ZCoder now ships a dedicated `zPITR` service (`deploy/docker/zpitr/`, orchestrated by `docker-compose.zpitr.yml`) that automates the physical PITR path described in this runbook:

- **Continuous WAL streaming** via `pg_receivewal` daemon into `zpitr_wal_archive` volume (real-time, per-commit RPO).
- **Periodic base backups** via `pg_basebackup -Ft -z -Xs` with SHA-256 manifest into `zpitr_base_backups` volume.
- **On-demand restore drill** (`docker exec zPITR /app/scripts/run_restore_drill.sh`) that restores into an isolated temp directory, injects `recovery.signal` + `restore_command`, verifies WAL archive continuity, and emits Release Gate evidence JSON.
- **Evidence emission** via `emit_evidence.py` writes `docs/evidence/pitr-qualification-<SHA>.json` (schema v1) bound to the exact release-candidate SHA for `scripts/release_gate.py --check`.

Use `zPITR` when you need an automated, repeatable PITR drill tied to a specific RC SHA. Use the manual `BackupManager.run_restore_drill()` procedure above for logical `pg_dump`/`pg_restore` drills without WAL replay.

---

## Prerequisites

Before starting a rehearsal, verify all of the following:

| # | Requirement | Check |
|---|---|---|
| 1 | PostgreSQL reachable from the operator host | `psql "$DATABASE_URL" -c 'SELECT 1'` succeeds |
| 2 | `pg_dump` and `pg_restore` installed | `pg_dump --version && pg_restore --version` (postgresql-client) |
| 3 | `RESTORE_DRILL_DATABASE_URL` points at an **isolated, non-production** database | Confirm the target host/database name; **never point this at production**. The code refuses to run if unset, but only you can confirm the target is truly isolated |
| 4 | `DATABASE_URL` set to the source database | `echo "${DATABASE_URL:?not set}"` |
| 5 | Backup destination writable with sufficient disk space | Default `/var/backups/zcoder`; size the free space at ≥ 2× your current database size (dump + restored target headroom) |
| 6 | `BACKUP_ENCRYPTION_KEY` handled per secrets policy (if encryption-at-rest for backup files is in scope for the environment) | Do not paste keys into shell history or logs |
| 7 | Expected verification IDs collected beforehand | A short list of known job IDs and repository IDs that existed at backup time |

Credentials travel via `PGPASSWORD` inside a filtered child environment
(SEC-008) — passwords must never appear on command lines or in captured logs;
the module redacts them from error text as a best effort.

---

## Quarterly rehearsal procedure

### Step 0 — Record context

Record before anything else:

```bash
git rev-parse HEAD          # RC SHA this rehearsal qualifies (or practice-only)
date -u +%FT%TZ            # start timestamp
```

If `HEAD` is not the exact release-candidate SHA, label the drill
**PRACTICE — not RC evidence** in the record below.

### Step 1 — Freshness check

Confirm backups exist and the latest one is fresh (< 26 hours old):

```python
from zcoder.services.backup_restore import BackupManager
bm = BackupManager()
print(bm.get_freshness_report())
```

Expected fields: `status == "OK"` (i.e. `last_backup_age_hours < 26`),
non-zero `backup_count`, and a non-empty `sha256`. If `status == "STALE"`
or `"NO_BACKUPS"`, stop and investigate the scheduled backup job before
proceeding — do not rehearse against stale state.

### Step 2 — Run a fresh backup

```python
record = bm.run_pg_dump_backup()
assert record.success, record.error
```

This runs `pg_dump --format=custom --compress=9` into
`<backup_destination>/pgdump_<epoch>.sql.gz` (60-minute timeout). On failure
the returned `BackupRecord.error` carries a redacted diagnostic.

### Step 3 — Record SHA256 and size from the manifest

The manifest is written next to the dump as `<backup_id>.json`:

```bash
cat /var/backups/zcoder/<backup_id>.json   # fields: sha256, size_bytes, destination
```

Copy the full `sha256` and `size_bytes` values into the evidence table below.
(Do not rely on `get_freshness_report()`'s `sha256` field for evidence — it
is truncated to 16 hex characters.)

Independently verify integrity if desired:

```bash
sha256sum /var/backups/zcoder/<backup_id>.sql.gz
```

### Step 4 — Restore drill into the isolated target

Run the restore drill against the isolated database, passing the known-good
IDs collected in the prerequisites:

```python
drill = bm.run_restore_drill(
    backup_id="<backup_id>",
    target_database_url="",        # empty → uses RESTORE_DRILL_DATABASE_URL
    expected_job_ids=["<job-id-1>", "<job-id-2>"],
    expected_repo_ids=["<repo-id-1>"],
)
print(drill)
```

The tool restores via `pg_restore --clean --if-exists` (exit code 1 is
tolerated as warnings) and reports a `RestoreDrillResult` including
`rto_seconds`.

**Operator check (required):** inspect the result notes and the drill log
warnings. The tool currently sets `success=True` when `pg_restore` itself
succeeded even if an expected job/repo ID was *not* found (it logs a warning
instead of failing) — so the operator MUST confirm every expected ID was found
before declaring PASS. See Known gaps below.

### Step 5 — Verification queries

Against the restored target database, confirm content beyond the automated
checks:

```sql
SELECT COUNT(*) FROM jobs;
SELECT COUNT(*) FROM repositories;
SELECT id FROM jobs    WHERE id IN ('<job-id-1>', '<job-id-2>');
SELECT id FROM repositories WHERE id = '<repo-id-1>';
```

Optionally spot-check row-level integrity for one high-value record (compare a
few columns against the source database).

### Step 6 — Retention enforcement (dry observation)

Observe what the retention policy *would* delete before running it for real:

```bash
ls -lt /var/backups/zcoder/pgdump_*.sql.gz
```

For each file compute age in days vs `retention_days_daily` (default 7).
Only then, if cleanup is intended this quarter:

```python
deleted = bm.enforce_retention()
print(f"retention deleted {deleted} backup(s)")
```

Note: `enforce_retention()` deletes immediately and also removes the matching
`.json` manifest — there is no dry-run mode. Never invoke it before the
restore drill has consumed the backup under test.

### Step 7 — WAL archiving configuration checklist

PITR capability requires continuous WAL archiving plus periodic base backups;
pg_dump alone is not low-RPO DR. Generate the configuration the server needs:

```python
from zcoder.services.backup_restore import BackupManager
BackupManager.get_wal_archive_config()   # → dict of postgresql.conf settings
```

For object storage, install the same pinned WAL-G release on the PostgreSQL
primary and every isolated recovery host, then generate the WAL-G commands.
Use `backend="s3"` for S3-compatible storage or `backend="gcs"` for Google
Cloud Storage:

```python
from zcoder.services.backup_restore import BackupManager
BackupManager.get_wal_archive_config(backend="s3")
BackupManager.get_wal_archive_config(backend="gcs")
```

Both modes return `wal-g wal-push '%p'` and `wal-g wal-fetch '%f' '%p'`. This
helper does not install WAL-G, configure storage, pass credentials, create
base backups, or prove recovery.

For S3-compatible storage, set `WALG_S3_PREFIX=s3://<dedicated-bucket>/<cluster-prefix>`
and `AWS_REGION` in the PostgreSQL service environment. For a compatible
endpoint, configure WAL-G's `AWS_ENDPOINT` and path-style option only when the
provider requires them. Provide access through a workload IAM role where
available; otherwise use dedicated credentials from a secret manager with
only the required bucket/prefix access.

For Cloudflare R2, configure the S3-compatible endpoint and region as follows;
use a dedicated bucket/prefix and supply credentials through the PostgreSQL
service's secret mechanism:

```dotenv
WALG_S3_PREFIX=s3://<dedicated-r2-bucket>/zcoder/postgresql
AWS_ENDPOINT=https://<account-id>.r2.cloudflarestorage.com
AWS_REGION=auto
AWS_S3_FORCE_PATH_STYLE=true
AWS_ACCESS_KEY_ID=<secret-manager-reference>
AWS_SECRET_ACCESS_KEY=<secret-manager-reference>
```

Cloudflare R2 does not implement the S3 Object Lock API. Configure and verify
R2 Bucket Lock Rules through Cloudflare's supported control plane if the
retention policy requires deletion protection. Do not assume that a bucket is
immutable because it accepts S3 writes.

For Google Cloud Storage, set
`WALG_GS_PREFIX=gs://<dedicated-bucket>/<cluster-prefix>`. WAL-G uses
Application Default Credentials. On a GCE/GKE PostgreSQL host, grant a
dedicated runtime service account the required access to this bucket. Do not
use a human Cloud Shell session identity as the production database identity
or put service-account JSON keys in this repository's `.env`.

Google Cloud Shell can inspect/configure GCS and run an operator-triggered
test, but it is an interactive shell rather than the continuously running
PostgreSQL primary that must archive each completed WAL segment. Use the
production database host's runtime identity for continuous archiving and the
isolated recovery host's identity for restore. Cloud Shell success alone is
not PITR evidence.

Do not reuse ZWorkforce credentials, place access keys in this repository's
`.env`, or expose credentials in process arguments/logs. Use a dedicated
backup bucket/prefix with server-side encryption, retention, and protection
against accidental deletion configured and verified. The Supabase
S3-compatible credentials in the separate ZWorkforce release config are not
ZCoder PITR credentials. Supabase documents that its Storage S3 API does not
support S3 versioning or Object Lock; do not use it as the sole immutable PITR
archive without an independently protected copy and an accepted recovery-risk
plan. See the [WAL-G storage documentation](https://github.com/wal-g/wal-g/blob/master/docs/STORAGES.md)
and [Google Cloud Shell authentication](https://cloud.google.com/shell/docs/auth).

Use a dedicated backup bucket/prefix with server-side encryption, retention,
and protection against accidental deletion configured and verified. The
Supabase S3-compatible credentials currently present in the separate
ZWorkforce release config are not ZCoder PITR credentials. Supabase documents
that its Storage S3 API does not support S3 versioning or Object Lock; do not
use it as the sole immutable PITR archive without an independently protected
copy and an accepted recovery-risk plan.

An S3 PITR qualification is a **physical PostgreSQL recovery**, not the
`pg_dump`/`pg_restore` logical drill described above. On the production primary,
verify the effective settings and archiver counters, and create periodic
physical base backups with WAL-G as the `postgres` OS user. On an isolated,
empty recovery host of the same PostgreSQL major version, fetch a base backup
and replay WAL to a selected UTC target time. Keep the recovery host isolated
from application traffic and pause at the target for inspection:

```bash
wal-g backup-fetch "$PGDATA" LATEST
touch "$PGDATA/recovery.signal"
```

Set `restore_command` to the generated WAL-G command, set
`recovery_target_time` to the chosen UTC target and
`recovery_target_action = 'pause'`, then start only the isolated recovery
instance. Verify it reached the intended target, inspect PostgreSQL recovery
logs and `pg_is_in_recovery()`, then query known records that should exist at
that time and records/changes that should not yet exist. Record the actual
backup label, recovery target, WAL archiver counters, results, timestamps and
sanitized evidence reference. Do not count a successful object upload or a
successful `pg_restore` as proof that WAL replay works.

The current `BackupManager.run_restore_drill()` restores a custom-format
`pg_dump` file with `pg_restore`; it does not perform this physical WAL-G
recovery. Only an Operations-run recovery on the production archive and an
isolated target can qualify the production PITR gate.

Apply and verify each item:

| Setting | Value | Checklist |
|---|---|---|
| `wal_level` | `replica` | ☐ set |
| `archive_mode` | `on` | ☐ set |
| `archive_command` | `cp %p <archive_path>/%f` | ☐ set ☐ archive dir exists and is writable by the postgres user |
| `archive_timeout` | `60` | ☐ set (caps RPO contribution at ~60 s) |
| `max_wal_senders` | `3` | ☐ set |
| `restore_command` | `cp <archive_path>/%f %p` | ☐ documented for recovery use |

**Restart caveat:** these parameters require a PostgreSQL **restart** to take
effect — schedule the restart within the approved maintenance window, or
confirm they are already active:

```sql
SHOW archive_mode; SHOW archive_command;
SELECT COUNT(*) FROM pg_stat_archiver;   -- archived_count should advance
```

Per the module's own warning: setting `archive_mode=on` alone is NOT PITR.
You must confirm WAL files are actually landing in the archive destination,
physical base backups are available, and a physical recovery test works before
claiming PITR support.

### Local Cloudflare R2 verification (2026-11-03)

A synthetic PostgreSQL 16 drill used WAL-G `v3.0.9` in a disposable container,
an isolated restore volume, and a temporary prefix under the existing shared
`z-platform` R2 bucket. The source used `archive_command = 'wal-g wal-push %p'`;
`wal-g backup-push "$PGDATA"` created a physical backup, and the restore used
`wal-g backup-fetch "$PGDATA" LATEST` plus
`restore_command = 'wal-g wal-fetch %f %p'`. Recovery to
`2026-11-03 15:42:35.80926+00` promoted successfully. The restored database
contained the row committed before the target and did not contain the row
committed after it. The source archiver reported 7 archived segments and 0
failures. The temporary container, volume, and objects under the unique drill
prefix were removed and cleanup was verified.

This confirms the local WAL-G/R2 upload and recovery path for synthetic data;
it is not production evidence. The shared `zpostgressql` cluster still has
`archive_mode=off`, and `z-platform` is not a dedicated ZCoder PITR bucket.
Only an Operations-run drill using the approved production archive and an
isolated production recovery target can satisfy the release gate.

---

## Evidence record template

One completed copy of this table per rehearsal, filed with the release
evidence for the RC SHA listed:

| Field | Value |
|---|---|
| Drill ID | `drill_<epoch>` (from `RestoreDrillResult.drill_id`) |
| RC SHA | `<git rev-parse HEAD>` — exact release-candidate SHA, else mark PRACTICE |
| Backup ID | `pgdump_<epoch>` |
| Started (UTC) | `<YYYY-MM-DDTHH:MM:SSZ>` |
| Completed (UTC) | `<YYYY-MM-DDTHH:MM:SSZ>` |
| RTO seconds | `<RestoreDrillResult.rto_seconds>` |
| Jobs verified | `<count>` of `<expected>` |
| Repos verified | `<count>` of `<expected>` |
| Events verified | `<n/a — not populated by current tooling>` |
| Backup SHA256 | `<full 64-hex digest from manifest>` |
| Backup size bytes | `<size_bytes>` |
| Freshness status at start | `OK` / `STALE` / `NO_BACKUPS` |
| WAL archiving checklist | complete / incomplete (list gaps) |
| Result | PASS / FAIL |
| Operator | `<name>` |

---

## Pass/fail criteria and rollback notes

PASS requires ALL of:

1. `get_freshness_report().status == "OK"` before starting.
2. `run_pg_dump_backup()` returned `success=True` with full SHA256 + size recorded.
3. Restore drill completed with `success=True`.
4. **Every** expected job ID and repo ID confirmed present in the restored
   database (by operator query, not just absence of warnings — see Known gaps).
5. Verification queries return plausible counts consistent with the source.
6. WAL archiving checklist complete (or a dated remediation ticket exists).

FAIL on any of: backup failure, restore failure or timeout, missing expected
records, count mismatch, or freshness `NO_BACKUPS`.

Rollback / containment notes:

- The drill never touches production: writes go only to the
  `RESTORE_DRILL_DATABASE_URL` target. If the drill itself corrupts the target
  (e.g. `--clean --if-exists` dropped objects it could not recreate), simply
  drop and recreate the isolated drill database — no production rollback is
  implicated.
- If retention deleted a needed backup, it cannot be recovered by this
  tooling; re-run `run_pg_dump_backup()`.
- Application-level rollback (previous container tag) is covered in
  `docs/operations/deployment.md` § Rollback and is out of scope here.

Failure escalation: on FAIL, stop the quarterly cycle and open a **HANDOFF**
entry per loop-engineering discipline (bounded slice, explicit next-owner,
exact observed state, reproduction commands from this document). Do not mark
the Operations gate row progressed until a subsequent PASS exists at the same
RC SHA.

---

## Known gaps (honest scope, as of this writing)

Documented discrepancies between this procedure and current
`backup_restore.py` behavior — operators must compensate manually until fixed:

1. **Expected-ID misses do not fail the drill.** `_verify_restored_state`
   only logs a warning when an expected job/repo ID is absent, while
   `run_restore_drill` still returns `success=True`. Operator step 4/5 above
   is therefore mandatory, not advisory.
2. **Verification exceptions are swallowed.** If state verification raises
   (e.g. `psycopg2` missing), counts silently become `0, 0`; treat a drill
   with zero verified rows as suspicious and re-check manually.
3. **Retention weekly tier unused.** `enforce_retention()` applies only
   `retention_days_daily`; `retention_days_weekly` is accepted but not
   enforced.
4. **No dry-run mode for retention** — deletion is immediate.
5. **File naming:** dumps are written as `*.sql.gz` although the format is
   pg_dump *custom* format with gzip compression (not plain SQL).
6. **`events_verified` exists on `RestoreDrillResult` but is never populated.**
7. **No built-in scheduling** — the module expects invocation by cron /
   Kubernetes CronJob; the quarterly cadence in this runbook is procedural,
   not enforced.
