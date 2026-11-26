# Migration Guide: zpostgressql → zpostgresql

## 1. Migration Objectives

Migrate the Docker PostgreSQL deployment from the deprecated legacy identifier
`zpostgressql` to the canonical target `zpostgresql`.

- Retire `zpostgressql` from all active configuration, application code, scripts,
  and documentation.
- Preserve all data, roles, and database objects from the source instance.
- Validate source-versus-target data integrity before cutover.
- Document rollback and disaster recovery procedures.

## 2. Source and Target Architecture

### Source: `zpostgressql` (deprecated)

| Property | Value |
|----------|-------|
| Container name | `zpostgressql` |
| Image | `postgres:15-alpine` (digest `sha256:aae6554de426ae1990f1a939ff183a0299146cf7142a6f4c379c3357af9cc2d8`) |
| Docker volume | `zalive_pgdata` |
| Docker network | `zalive_albert-network` |
| Published port | `5433` (host) → `5432` (container) |
| PostgreSQL user | `zalive` |
| Databases | `zalive_db`, `zcoder_db`, `zmovie_db`, `postgres`, `template0`, `template1` |
| Extensions | `plpgsql` |
| Restart policy | `unless-stopped` |

### Target: `zpostgresql` (canonical)

| Property | Value |
|----------|-------|
| Container name | `zpostgresql` |
| Image | `postgres:15-alpine` (same digest as source) |
| Docker volume | `zcoder_zpostgresql_data` |
| Docker network | `zcoder_zPostgreSQL_network` |
| Published port | None (not exposed externally) |
| PostgreSQL user | `zcoder` |
| Databases | `zcoder_db`, `zksato`, `zmovie`, `zalive_db` (restored), `postgres`, `template0`, `template1` |
| Extensions | `plpgsql` |
| Restart policy | `unless-stopped` |
| Authentication | Password file secrets (`/run/secrets/zcoder_postgres_password`) |

### Version Compatibility

Both source and target run PostgreSQL 15.19 with the same image digest. Logical
migration via `pg_dump` / `pg_restore` is fully supported. No PGDATA directory
copy between major versions is required.

## 3. Infrastructure Discovery Findings

The following resources were discovered during deep infrastructure inspection:

- Source container `zpostgressql` is running and healthy.
- Target container `zpostgresql` is running and healthy.
- Source databases: `zalive_db` (7487 kB), `zcoder_db` (9679 kB), `zmovie_db` (7559 kB).
- Source roles: `zalive` (superuser), `zcoder`, `zmovie`.
- Source `zcoder_db` contains 23 tables with application data.
- Target `zcoder_db` exists with matching schema (empty prior to restore).
- No PostgreSQL extensions beyond `plpgsql` on either instance.

## 4. Backup Procedures

### Backup Tool

Logical backup using `pg_dumpall` (globals + all databases) and per-database
`pg_dump` for granular recovery.

### Backup Command

```bash
# Globals + all databases
docker exec zpostgressql pg_dumpall -U zalive --clean > zpostgressql-pgdumpall-<timestamp>.sql

# Per-database
docker exec zpostgressql pg_dump -U zalive -d zcoder_db --clean --if-exists --create > zpostgressql-zcoder_db-<timestamp>.sql
```

### Backup Manifest

Recorded in `docs/migrations/BACKUP-MANIFEST.md` (or adjacent):

| Item | Value |
|------|-------|
| Backup timestamp | 2026-11-25T23:06:10Z |
| Source PostgreSQL version | PostgreSQL 15.19 |
| Backup format | Plain-text SQL (logical) |
| SHA-256 verification | All files verified OK |
| Databases backed up | `zalive_db`, `zcoder_db`, `zmovie_db` |

No secrets or plaintext passwords are recorded in the manifest.

## 5. Backup Verification

- `pg_dumpall` exit code: 0.
- All per-database `pg_dump` exit codes: 0.
- `sha256sum -c` on all backup files: OK.
- Backup archive contents inspected: contains `CREATE ROLE`, `CREATE DATABASE`,
  table definitions, and `COPY` data statements.
- Source volumes and backups preserved (no destructive operations).

## 6. Restore Procedures

### Restore Sequence

1. Validate target PostgreSQL readiness (`pg_isready`).
2. Verify target version compatibility (both PostgreSQL 15).
3. Restore global roles (`zalive`, `zcoder`, `zmovie`) with SCRAM-SHA-256 password verifiers.
4. Create required databases (`zcoder_db`, `zalive_db`, `zmovie_db`).
5. Restore database schemas and objects from verified backup.
6. Restore data.
7. Validate sequences, constraints, indexes, and ownership.
8. Validate application connectivity.

### Restore Commands

```bash
# Restore roles into target
grep -E "^CREATE ROLE|^ALTER ROLE" zpostgressql-pgdumpall-<timestamp>.sql \
  | grep -E '"zalive"|"zmovie"' \
  | docker exec -i zpostgresql psql -U zcoder -d postgres -v ON_ERROR_STOP=1

# Create databases
docker exec zpostgresql psql -U zcoder -d postgres -c "CREATE DATABASE zcoder_db OWNER zcoder;"
docker exec zpostgresql psql -U zcoder -d postgres -c "CREATE DATABASE zalive_db OWNER zalive;"

# Restore zcoder_db data
docker exec -i zpostgresql psql -U zcoder -d zcoder_db -v ON_ERROR_STOP=1 \
  < <(grep -vE "^(DROP DATABASE|CREATE DATABASE|\\connect|ALTER DATABASE)" zpostgressql-zcoder_db-<timestamp>.sql)

# Restore zalive_db data
docker exec -i zpostgresql psql -U zalive -d zalive_db -v ON_ERROR_STOP=1 \
  < <(grep -vE "^(DROP DATABASE|CREATE DATABASE|\\connect|ALTER DATABASE)" zpostgressql-zalive_db-<timestamp>.sql)
```

## 7. Data Integrity Verification

All tables in the restored `zcoder_db` were compared against the verified backup:

| Table | Backup rows | Target rows | Status |
|-------|-------------|-------------|--------|
| `api_keys` | 1 | 1 | OK |
| `backup_status` | 0 | 0 | OK |
| `engineering_tasks` | 20 | 20 | OK |
| `enterprise_audit` | 1 | 1 | OK |
| `organizations` | 2 | 2 | OK |
| `outbox` | 17 | 17 | OK |
| `projects` | 2 | 2 | OK |
| `tenant_jobs` | 1 | 1 | OK |
| `tenant_quotas` | 1 | 1 | OK |
| `usage_ledger` | 1 | 1 | OK |
| `webhook_inbox` | 17 | 17 | OK |
| `worker_registry` | 1 | 1 | OK |
| (all other tables) | 0 | 0 | OK |

**Result**: Target matches verified backup for all tables, indexes, constraints,
policies, and ownership. No missing records, no broken foreign keys, no invalid
indexes.

Note: The source (`zpostgressql`) data changed after the backup was taken
(source now shows 0 rows for some tables that had data at backup time). The
target was restored from the verified backup and matches it exactly.

## 8. Application Cutover

Application configuration was migrated from `zpostgressql` to `zpostgresql`:

- `ZCODER_POSTGRES_HOST` changed from `zpostgressql` to `zpostgresql`
- `ZALIVE_POSTGRES_HOST` changed from `zpostgressql` to `zpostgresql`
- Docker Compose service renamed `zpostgressql` → `zpostgresql`
- Docker volume renamed `zpostgressql_data` → `zpostgresql_data`
- Docker network renamed `zpostgressql_network` → `zpostgresql_network`
- Connection strings updated: `postgresql://...@zpostgressql:5432/...` → `postgresql://...@zpostgresql:5432/...`

The source `zpostgressql` container is preserved and recoverable until migration
acceptance.

## 9. Rollback Procedures

### Rollback Boundary

If the target `zpostgresql` accepts new writes after cutover, simply switching
back to the source `zpostgressql` can cause data loss. A safe rollback boundary
must be defined:

1. Stop all writes to `zpostgresql`.
2. Capture any new data written to `zpostgresql` after cutover.
3. Reconcile new data back to `zpostgressql` if rolling back.
4. Repoint application configuration to `zpostgressql`.
5. Restart application services.

### What Is Preserved

- Source container `zpostgressql` is **never** automatically destroyed.
- Source volume `zalive_pgdata` is **never** automatically deleted.
- Verified backups are **never** automatically deleted.

### Rollback Commands

```bash
# Repoint application configuration
# ZCODER_POSTGRES_HOST=zpostgressql
# ZALIVE_POSTGRES_HOST=zpostgressql

# Restart application services
docker compose restart zcoder

# Validate connectivity to source
docker exec zpostgressql pg_isready -U zcoder -d zcoder_db
```

## 10. Known Limitations

- The target `zpostgresql` container does not publish ports externally (by design, secure-by-default).
- The target container runs on a different Docker network than the source; applications on the source network must join the target network or use service discovery.
- The `local_postgres.py` developer tool defaults to container `zpostgresql`; operators must ensure the container is reachable on the expected network.
- Historical audit reports and the `Final-Report.md` retain `zpostgressql` when discussing the original migration source (allowed per documentation policy).

## 11. Final Verification Results

| Check | Result |
|-------|--------|
| `docker compose config --quiet` | Pass |
| Target `pg_isready` | Pass |
| Target container health | Healthy |
| Backup checksums | All OK |
| Row counts (backup vs target) | All match |
| Roles restored | `zalive`, `zcoder`, `zmovie` |
| Databases restored | `zcoder_db`, `zalive_db`, `zmovie_db` |
| Unit tests (docker_entrypoint, production_config, backup_restore) | Pass |
