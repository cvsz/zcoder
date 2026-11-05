# Deployment Guide

## Local runtime configuration

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `ZCODER_BASE_URL` | No | `http://127.0.0.1:8080/v1` | Loopback llama.cpp chat endpoint |
| `ZCODER_MODEL` | No | `zqwen2.5-coder-7b-instruct-q4_k_m` | Local request label |
| `DATABASE_URL` | No | SQLite | PostgreSQL DSN for API and worker processes; Docker entrypoint derives it from the mounted ZCoder password secret when configured |
| `ZCODER_POSTGRES_SECRET_SOURCE` | Compose only | `${HOME}/.config/zcoder/postgresql.password` | Host path to the password file created by `make postgres-setup`; mounted read-only into the ZCoder container |
| `ZCODER_AUTH_ENABLED` | Production API | `false` | Require verified OIDC bearer-token authentication |
| `ZCODER_OIDC_ISSUER` | Production API | — | OIDC issuer used to validate tokens |
| `ZCODER_OIDC_AUDIENCE` | Production API | — | Required token audience claim |
| `ZCODER_CORS_ORIGINS` | No | Empty | Explicit browser origins; wildcards are rejected |
| `ZCODER_WORKER_ORGANIZATION_ID` | Tenant worker | Empty | Organization scope for tenant job claims |
| `ZCODER_WORKER_PROJECT_ID` | No | Empty | Optional project scope for a tenant worker |
| `GITHUB_TOKEN` | Optional integration | — | GitHub REST access for GitHub operations |
| `ZCODER_LOG_LEVEL` | No | `INFO` | Log verbosity |
| `ZCODER_LOG_FORMAT` | No | TTY-dependent | Force `json` or `text` logs |

The main prompt client accepts loopback HTTP only and refuses redirects.
Start the model server before issuing inference requests. See
[`LOCAL-INFERENCE.md`](../guides/LOCAL-INFERENCE.md).

## Run from source

```bash
make setup
export ZCODER_BASE_URL=http://127.0.0.1:8080/v1
zcoder -p "Explain this repository"
```

## Shared PostgreSQL

The shared Docker PostgreSQL container is named `zPostgreSQL`. ZCoder uses
database `zcoder_db` and role `zcoder` on the `zPostgreSQL_network` bridge.
Provision and check it with:

```bash
make postgres-setup
make postgres-status
```

The ZCoder Compose stack joins the external `zPostgreSQL_network` and mounts
the dedicated role's password file as a read-only Compose secret. The
container entrypoint derives `DATABASE_URL` in memory for `zcoder_db`/`zcoder`;
the DSN is not stored in the repository `.env` or baked into the image. Keep
the password file owned by the local operator and mode `0600`. Host-side
commands should use `python scripts/local_postgres.py run -- <command>` so the
credential is injected only into the child process.

Applications sharing this PostgreSQL server should use separate databases and
roles. Do not put database credentials in source control.

## Tenant-scoped API workers

The public `/api/v1/jobs` routes use the durable PostgreSQL `tenant_jobs`
queue. A worker must have an explicit organization scope before it can claim
tenant jobs:

```bash
export ZCODER_WORKER_ORGANIZATION_ID=org_example
make worker
```

Set `ZCODER_WORKER_PROJECT_ID` when the worker should process only one project.

## Validation commands

```bash
python -m pytest tests/unit
python -m pytest tests/integration
ruff check .
black --check .
bandit -r src
```

Integration tests require the shared PostgreSQL service and use the database
configured by `scripts/local_postgres.py`.

## Container deployment

```bash
docker build -t zcoder:local .
docker run --rm zcoder:local --version
```

The image does not bundle GGUF weights or a model server. The containerized
inference network has not been verified; use the local source installation
for the supported loopback model workflow. Do not expose an unauthenticated
model endpoint publicly.

The API server uses the configured `DATABASE_URL` and authentication settings.
Use a secret manager for production database and identity-provider values.

## Health checks

```bash
zcoder --health-check
zcoder --health-check --health-check-deep
```

The standard check validates the Python runtime, writable configuration
directory, and loopback model configuration. The deep check makes one local
inference request and is intended for startup or manual diagnosis, not frequent
liveness probes.

## Logging and rollback

In non-interactive environments, JSON logs are enabled by default. Credential
patterns and authorization header values are redacted by
`src/zcoder/config/logging.py`.

Deploy tagged artifacts only after the exact commit passes the required CI,
security, packaging, and runtime gates. Roll back by deploying the previous
known-good tag. Validate database backup and restore procedures before a
production migration.

## Incident response

| Symptom | First step |
|---|---|
| Local inference fails | Check `llama-server` health, GGUF path, and loopback URL |
| Model URL validation fails | Set `ZCODER_BASE_URL` to an HTTP loopback URL without credentials or query parameters |
| PostgreSQL connection fails | Check container `zPostgreSQL`, network membership, role, database, and secret-file permissions |
| API readiness returns 503 | Check database health and API configuration before adding traffic |
| Circuit breaker opens | Inspect the local service logs and dependency health; avoid repeated retries while the dependency is unavailable |

## zPITR — Point-in-Time Recovery Service

ZCoder includes a dedicated `zPITR` Docker service for automated Point-in-Time Recovery (RPO < 5 min, RTO < 30 min) and Release Gate PITR evidence generation.

### Architecture

`zPITR` runs as a sidecar container on `zPostgreSQL_network` with:
- **`pg_receivewal` daemon** — continuous WAL streaming from `zPostgreSQL` into `zpitr_wal_archive` Docker volume.
- **`pg_basebackup` scheduler** — periodic full physical snapshots into `zpitr_base_backups` Docker volume.
- **Restore drill** — isolated recovery into `/tmp/pg_drill_data` with `recovery.signal` + `restore_command`, WAL archive continuity check, and Release Gate evidence emission.

### Deployment

```bash
# Build and start zPITR (daemon mode streams WAL continuously)
docker compose -f docker-compose.zpitr.yml up -d --build

# Verify WAL streaming
docker logs -f zPITR
```

### Credentials

The PostgreSQL password travels as a Docker secret (`zcoder_postgres_password`) mounted read-only at `/run/secrets/zcoder_postgres_password`, per SEC-008. The host source is `${HOME}/.config/zcoder/postgresql.password` (mode `0600`) unless `ZCODER_POSTGRES_SECRET_SOURCE` overrides it. Never bake credentials into the image or `.env`.

### Restore Drill (Release Gate Evidence)

Run the drill against an isolated target to generate evidence bound to the release-candidate SHA:

```bash
# Run PITR drill (generates docs/evidence/pitr-qualification-<SHA>.json)
docker exec -it -e CANDIDATE_SHA="$(git rev-parse HEAD)" zPITR /app/scripts/run_restore_drill.sh

# Verify evidence file
ls -la docs/evidence/pitr-qualification-*.json

# Run Release Gate to confirm PASS
python scripts/release_gate.py --check
```

The evidence JSON conforms to schema v1 (`wal_archive_verified`, `restore_drill_passed`, `tested_at` UTC Z, `evidence_sha256` 64-hex) required by `scripts/release_gate.py`.

### Operational commands

| Purpose | Command |
|---|---|
| Continuous WAL streaming | `docker compose -f docker-compose.zpitr.yml up -d` |
| Manual base backup | `docker exec -it zPITR /app/scripts/run_basebackup.sh` |
| Restore drill + evidence | `docker exec -it -e CANDIDATE_SHA=<SHA> zPITR /app/scripts/run_restore_drill.sh` |
| View WAL archive | `docker run --rm -v zpitr_wal_archive:/archive alpine ls -la /archive` |

**Note:** zPITR is a DR rehearsal and Release Gate tool. Production PITR qualification still requires an Operations-run recovery against the production archive on an isolated target — local synthetic drills do not by themselves satisfy the production PITR gate.
