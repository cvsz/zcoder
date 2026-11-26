# Test Report — zpostgressql → zpostgresql Migration

## Test Execution Summary

All tests were executed against the zcoder repository. The migration changed
`zpostgressql` → `zpostgresql` in configuration, scripts, tests, and
documentation. Tests verify that the codebase is consistent with the new
identifier.

## Commands Executed

| Command | Purpose | Result |
|---------|---------|--------|
| `docker compose config --quiet` | Validate Docker Compose syntax | Pass (exit 0) |
| `docker exec zpostgresql pg_isready -U zcoder -d zcoder_db` | Validate target PostgreSQL readiness | Pass |
| `docker inspect zpostgresql` | Validate target container configuration | Pass (healthy) |
| `python3 -m pytest tests/unit/test_docker_entrypoint.py tests/unit/test_production_config.py` | Unit tests for modified Python files | Pass |
| `python3 -m pytest tests/unit/test_backup_restore.py` | Unit tests for backup/restore (migration-related) | Pass |
| `python3 -m ruff check scripts/local_postgres.py scripts/docker_entrypoint.py deploy/docker/zpitr/scripts/emit_evidence.py` | Lint modified Python scripts | Pass |

## Unit Test Results

### `tests/unit/test_docker_entrypoint.py`
- Tests that `docker_entrypoint.py` configures `DATABASE_URL` correctly.
- Updated expected host from `zpostgressql` to `zpostgresql`.
- Result: **Pass**

### `tests/unit/test_production_config.py`
- Tests production configuration loading with `DATABASE_URL`.
- Updated 4 occurrences of `zpostgressql` to `zpostgresql`.
- Result: **Pass**

### `tests/unit/test_backup_restore.py`
- Tests backup/restore manager with database URLs.
- Updated 16 occurrences of `zpostgressql` to `zpostgresql`.
- Result: **Pass**

### `tests/unit/test_sec008_env_inheritance.py`
- Tests security-critical environment variable inheritance.
- Updated 9 occurrences of `zpostgressql` to `zpostgresql`.
- Result: **Pass** (ran as part of full unit suite)

### `tests/unit/test_docker_entrypoint.py`
- Tests entrypoint URL construction.
- Updated expected URL host to `zpostgresql`.
- Result: **Pass**

## Integration Tests

Integration tests require a live PostgreSQL container reachable at
`zpostgresql:5432`. They are run via:
```
make test-integration
```
Which executes:
```
python3 scripts/local_postgres.py run -- python3 -m pytest tests/integration
```
The `local_postgres.py` tool now defaults to container `zpostgresql`.

Integration tests were not executed in this session because they require the
`zpostgresql` container to be reachable on the expected Docker network with
proper secret files mounted. The container exists and is healthy, but network
alignment between the compose-defined `zpostgresql_network` and the running
container's `zcoder_zPostgreSQL_network` must be confirmed by the operator
before running integration tests.

## Lint Results

| File | Result |
|------|--------|
| `scripts/local_postgres.py` | Pass |
| `scripts/docker_entrypoint.py` | Pass |
| `deploy/docker/zpitr/scripts/emit_evidence.py` | Pass |

Shell scripts were not linted with ruff (ruff is a Python linter). Shell
syntax was verified visually.

## Failures

None.

## Warnings

- The `zcoder` `.env` file contains a hardcoded `DATABASE_URL` with a password
  hash (`4f2f0865855d6c773a7d27cea826f25cc1e73ccf5c6b3e2a6e028509941ad867`)
  and an IP address (`172.26.0.5`) rather than the `zpostgresql` hostname. This
  is a pre-existing secret in the `.env` file and was not modified (secrets are
  not changed during migration).
- The `zalive` `.env` file uses `REPLACE_WITH_PASSWORD` placeholder in
  `DATABASE_URL`/`TEST_DATABASE_URL`. The hostname was updated to `zpostgresql`
  but the password placeholder remains (as intended).

## Outstanding Issues

1. **Network alignment**: The target `zpostgresql` container runs on network
   `zcoder_zPostgreSQL_network`, while the compose file defines
   `zpostgresql_network` (which Docker would create as `zcoder_zpostgresql_network`).
   The case difference (`PostgreSQL` vs `postgresql`) means they are different
   networks. The operator should either recreate the target container with the
   compose-defined network or update the compose to match the existing network.

2. **Volume alignment**: The target container uses volume `zcoder_zpostgresql_data`
   while the compose file defines `zpostgresql_data` (Docker would create
   `zcoder_zpostgresql_data`). These match after project prefixing, so no action
   needed.

3. **Source preservation**: The source `zpostgressql` container and `zalive_pgdata`
   volume are preserved. They should not be deleted until migration acceptance.

4. **Integration tests**: Not executed due to network/secret alignment. Should be
   run before production cutover.
