# ZCoder — Integration Test Report

**Repository:** https://github.com/cvsz/zcoder
**Date:** 2026-11-08

## Integration Test Execution

| Command | Result | Tests | Failures | Skips |
|---------|--------|-------|----------|-------|
| `python scripts/local_postgres.py run -- python -m pytest tests/integration` | PASS | 78 | 0 | 0 |
| `python scripts/local_postgres.py run -- python -m pytest tests/e2e` | PASS | 130 | 0 | 0 |

## PostgreSQL Setup

The shared PostgreSQL container `zpostgressql` on network `zPostgreSQL_network` was started and provisioned:
- Container: `zpostgressql` (postgres:15-alpine)
- Database: `zcoder_db`
- Role: `zcoder`
- Network: `zPostgreSQL_network`

`python scripts/local_postgres.py setup` completed successfully:
```
zcoder_db ready for zcoder (PostgreSQL 15.19 on x86_64-pc-linux-musl)
```

## Integration Test Coverage

Integration tests exercise actual component boundaries:
- PostgreSQL store integration
- Outbox concurrency
- Multi-process claim/fence/crash/reclaim
- Upgrade fence and lease
- Continuous engineering PostgreSQL backend
- Maintenance campaigns

All tests use the real PostgreSQL database (no mocks for database interactions).

## Without PostgreSQL

When PostgreSQL is unavailable, 28 tests are skipped with explicit justification:
- "PostgreSQL instance not reachable"
- "PostgreSQL test container not reachable"
- "DATABASE_URL PostgreSQL instance not reachable"

This is expected behavior. Integration tests require a live PostgreSQL database.
