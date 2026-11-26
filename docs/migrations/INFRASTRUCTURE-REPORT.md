# Infrastructure Report — zpostgressql → zpostgresql Migration

## Source Container Findings

| Property | Value |
|----------|-------|
| Container name | `zpostgressql` |
| Container ID | `58033f21ecb6b1b263916bfd4ff6e2d7c49669b8e95122630301eaa10349d9a6` |
| Image | `postgres:15-alpine` |
| Image digest | `sha256:aae6554de426ae1990f1a939ff183a0299146cf7142a6f4c379c3357af9cc2d8` |
| Entrypoint | `docker-entrypoint.sh postgres` |
| State | Running |
| Restart count | 0 |
| Restart policy | `unless-stopped` |
| Docker volume | `zalive_pgdata` (mounted at `/var/lib/postgresql/data`) |
| Docker network | `zalive_albert-network` |
| Published port | `0.0.0.0:5433 → 5432/tcp` |
| Environment | `POSTGRES_USER=zalive`, `POSTGRES_PASSWORD=zalive`, `POSTGRES_DB=zalive_db` |
| Health check | `pg_isready` (implicit via container runtime) |

### Source Databases

| Database | Owner | Size |
|----------|-------|------|
| `zalive_db` | `zalive` | 7487 kB |
| `zcoder_db` | `zcoder` | 9679 kB |
| `zmovie_db` | `zmovie` | 7559 kB |
| `postgres` | `zalive` | 7329 kB |

### Source Roles

| Role | Attributes |
|------|------------|
| `zalive` | Superuser, Create role, Create DB, Replication, Bypass RLS |
| `zcoder` | (no special attributes) |
| `zmovie` | (no special attributes) |

### Source Extensions

| Extension | Version |
|-----------|---------|
| `plpgsql` | 1.0 |

## Target Container Configuration

| Property | Value |
|----------|-------|
| Container name | `zpostgresql` |
| Container ID | `cab6209e0fa9562c828dfb722e2fc1eb9263ace93c1d4bf482a02fd5049b0c27` |
| Image | `postgres:15-alpine` |
| Image digest | `sha256:aae6554de426ae1990f1a939ff183a0299146cf7142a6f4c379c3357af9cc2d8` |
| Entrypoint | `docker-entrypoint.sh postgres` |
| State | Running |
| Restart count | 0 |
| Restart policy | `unless-stopped` |
| Health status | Healthy |
| Docker volume | `zcoder_zpostgresql_data` (mounted at `/var/lib/postgresql/data`) |
| Docker network | `zcoder_zPostgreSQL_network` |
| Published port | None (not exposed externally) |
| Environment | `POSTGRES_PASSWORD_FILE=/run/secrets/zcoder_postgres_password`, `POSTGRES_DB=zcoder_db`, `POSTGRES_USER=zcoder` |
| Health check | `pg_isready` (healthy) |
| Authentication | Password file secrets (no password in environment) |

### Target Databases (after restore)

| Database | Owner | Size |
|----------|-------|------|
| `zcoder_db` | `zcoder` | Restored from backup |
| `zksato` | `zcoder` | Pre-existing |
| `zmovie` | `zmovie` | Pre-existing |
| `zalive_db` | `zalive` | Restored from backup |
| `postgres` | `zcoder` | System |
| `template0` | `zcoder` | System |
| `template1` | `zcoder` | System |

### Target Roles

| Role | Attributes |
|------|------------|
| `zcoder` | (pre-existing) |
| `zalive` | Restored (superuser, Create role, Create DB, Replication, Bypass RLS) |
| `zmovie` | Restored |

### Target Extensions

| Extension | Version |
|-----------|---------|
| `plpgsql` | 1.0 |

## Docker Volumes

| Volume | Purpose | Associated Container |
|--------|---------|---------------------|
| `zalive_pgdata` | Source PostgreSQL data | `zpostgressql` (preserved) |
| `zcoder_zpostgresql_data` | Target PostgreSQL data | `zpostgresql` |
| `zcoder_zpostgressql_data` | Legacy volume (from compose definition) | Not in use |

## Network Topology

| Network | Driver | Containers |
|---------|--------|------------|
| `zalive_albert-network` | bridge | `zpostgressql`, albert-server, mitmproxy, firmware-server |
| `zcoder_zPostgreSQL_network` | bridge | `zpostgresql` |
| `zcoder_zpostgressql_network` | bridge | Legacy (defined in compose, not currently attached) |
| `zPostgreSQL_network` | bridge | Legacy (standalone) |

## PostgreSQL Versions

| Instance | Version | Compatible |
|----------|---------|------------|
| Source `zpostgressql` | PostgreSQL 15.19 | Yes |
| Target `zpostgresql` | PostgreSQL 15.19 | Yes |

Both instances share the same major version (15) and image digest, enabling
logical migration without PGDATA directory copying.

## Security Configuration

| Property | Source `zpostgressql` | Target `zpostgresql` |
|----------|----------------------|---------------------|
| Password in environment | Yes (`POSTGRES_PASSWORD=zalive`) | No (password file) |
| Password file | No | Yes (`/run/secrets/zcoder_postgres_password`) |
| Published port | Yes (5433) | No |
| Secret management | No | Docker secrets |
| Authentication | `POSTGRES_PASSWORD` env var | `POSTGRES_PASSWORD_FILE` secret |
| Network access | Bridge network (zalive_albert-network) | Bridge network (zcoder_zPostgreSQL_network) |

## Security Notes

- Source exposes PostgreSQL port 5433 on all interfaces; target does not publish any port.
- Source uses `POSTGRES_PASSWORD` in environment (visible in `docker inspect`); target uses password file via Docker secrets.
- Target follows secure-by-default: no published ports, password file authentication.
- No secrets are recorded in reports or documentation.
