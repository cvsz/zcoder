# Deployment Guide

## Local runtime configuration

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `ZCODER_BASE_URL` | No | `http://127.0.0.1:8080/v1` | Loopback llama.cpp chat endpoint |
| `ZCODER_MODEL` | No | `zqwen2.5-coder-7b-instruct-q4_k_m` | Local request label |
| `DATABASE_URL` | No | SQLite | PostgreSQL DSN for API, worker, and integration-test commands |
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
