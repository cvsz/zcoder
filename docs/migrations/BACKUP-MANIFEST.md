# PostgreSQL Backup Manifest — zpostgressql → zpostgresql Migration

## Backup metadata
- **Source instance**: `zpostgressql` (Docker container)
- **Source image**: `postgres:15-alpine` (digest `sha256:aae6554de426ae1990f1a939ff183a0299146cf7142a6f4c379c3357af9cc2d8`)
- **Source PostgreSQL version**: PostgreSQL 15.19
- **Backup timestamp**: 2026-11-25T23:06:10Z (start) / 2026-11-25T23:07:24Z (per-DB complete)
- **Backup tool**: `pg_dumpall` + `pg_dump` (logical backup)
- **Backup directory**: `/tmp/opencode/zpostgres-migration/backups/`
- **Backup format**: Plain-text SQL

## Databases backed up
| Database | Owner | Size (source) |
|----------|-------|---------------|
| `zalive_db` | `zalive` | 7487 kB |
| `zcoder_db` | `zcoder` | 9679 kB |
| `zmovie_db` | `zmovie` | 7559 kB |

## Roles backed up
`zalive` (superuser), `zcoder`, `zmovie` (with SCRAM-SHA-256 password verifiers)

## Backup files

| File | SHA-256 | Size | Status |
|------|---------|------|--------|
| `zpostgressql-pgdumpall-20261125T230634Z.sql` | `b69d7e456d5d20dcffff07ce015b775a61e60ceb38023d2146fe0ecec818293e` | 51,199 bytes | Verified OK |
| `zpostgressql-zcoder_db-20261125T230724Z.sql` | (see `.sha256`) | 42,856 bytes | Verified OK |
| `zpostgressql-zalive_db-20261125T230724Z.sql` | (see `.sha256`) | 1,415 bytes | Verified OK |
| `zpostgressql-zmovie_db-20261125T230724Z.sql` | (see `.sha256`) | 1,415 bytes | Verified OK |

## Integrity verification
- All `sha256sum -c` checks returned **OK**.
- `pg_dumpall` exit code: 0.
- All per-database `pg_dump` exit codes: 0.
- Backup archive contents inspected: contains `CREATE ROLE`, `CREATE DATABASE`, table definitions, and `COPY` data statements.
- Backup can be inspected and restored (logical format).

## Notes
- No secrets/passwords are included in this manifest. Role password verifiers are stored only within the SQL backup file itself (SCRAM-SHA-256 hashes, not plaintext).
- Source volumes and backups are preserved. No destructive operations were performed on the source.
- Source and target share the same PostgreSQL major version (15), so logical migration is supported without PGDATA copying.