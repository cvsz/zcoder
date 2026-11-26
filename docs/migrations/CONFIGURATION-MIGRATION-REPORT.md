# Configuration Migration Report — zpostgressql → zpostgresql

## Migration Scope

All active references to `zpostgressql` were replaced with `zpostgresql` across
the zcoder and zalive repositories. Historical documentation and audit reports
retain `zpostgressql` when discussing the original migration source (allowed per
documentation policy).

## Modified Configuration Files

### zcoder repository

| File | Change | Reason |
|------|--------|--------|
| `docker-compose.yml` | Service `zpostgressql` → `zpostgresql`; container_name; volume `zpostgressql_data` → `zpostgresql_data`; network `zpostgressql_network` → `zpostgresql_network`; `ZCODER_POSTGRES_HOST` → `zpostgresql`; `depends_on` target | Canonical service naming |
| `docker-compose.zpitr.yml` | `PGHOST: zpostgressql` → `zpostgresql`; network `zpostgressql_network` → `zpostgresql_network` | zPITR connects to target |
| `scripts/local_postgres.py` | `CONTAINER` default `zpostgressql` → `zpostgresql`; `CONTAINER_FALLBACKS`; `POSTGRES_NETWORK`; network alias | Developer tool connects to target |
| `scripts/docker_entrypoint.py` | Default `ZCODER_POSTGRES_HOST` `zpostgressql` → `zpostgresql` | Container entrypoint connects to target |
| `scripts/run-full-validation.sh` | Default container `zpostgressql` → `zpostgresql` | Validation runner connects to target |
| `fix-zpitr.sh` | `PG_SERVICE` `zpostgressql` → `zpostgresql`; `NETWORK` `zpostgressql_network` → `zpostgresql_network` | zPITR repair script |
| `pitr-preflight.sh` | Container references `zpostgressql` → `zpostgresql` | PITR preflight checks target |
| `pitr-basebackup-verify.sh` | Container references `zpostgressql` → `zpostgresql` | Basebackup verification target |
| `pitr-restore-smoke-test.sh` | `SOURCE_CONTAINER` `zpostgressql` → `zpostgresql` | Smoke test target |
| `pitr-phase2-lab.sh` | `docker inspect zpostgressql` → `zpostgresql` | PITR lab script |
| `docker-resource-audit.sh` | `EXPECTED_CONTAINERS`, `EXPECTED_VOLUMES`, `EXPECTED_NETWORKS` updated | Resource audit expectations |
| `deploy/docker/zpitr/scripts/emit_evidence.py` | `"wal_source": "zpostgressql"` → `"zpostgresql"` | Evidence record |
| `.env.example` | `ZCODER_POSTGRES_HOST=zpostgressql` → `zpostgresql`; comments updated | Environment configuration |
| `tests/integration/test_postgres_store.py` | DSN default host `zpostgressql` → `zpostgresql` | Test connection |
| `tests/integration/test_upgrade_fence_multiprocess.py` | `PG_URL` default host `zpostgressql` → `zpostgresql` | Test connection |
| `tests/integration/test_postgres_multiprocess.py` | DSN default host `zpostgressql` → `zpostgresql` | Test connection |
| `tests/unit/test_production_config.py` | `DATABASE_URL` host `zpostgressql` → `zpostgresql` | Unit test configuration |
| `tests/unit/test_backup_restore.py` | All `zpostgressql` → `zpostgresql` (16 occurrences) | Backup/restore test fixtures |
| `tests/unit/test_sec008_env_inheritance.py` | All `zpostgressql` → `zpostgresql` (9 occurrences) | Security test fixtures |
| `tests/unit/test_docker_entrypoint.py` | Expected URL host `zpostgressql` → `zpostgresql` | Entry point test assertion |
| `tests/e2e/test_enterprise_suite.py` | `PG_URL` default host `zpostgressql` → `zpostgresql` | E2E test connection |
| `docs/migration/MIGRATION.md` | PostgreSQL host name fix section; compose example; version notes | Documentation |
| `docs/operations/deployment.md` | All `zpostgressql` → `zpostgresql` (6 occurrences) | Active documentation |
| `docs/operations/dr-rehearsal.md` | `zpostgressql` → `zpostgresql` | Active documentation |
| `docs/operations/zpitr-implementation.md` | All `zpostgressql` → `zpostgresql` (8 occurrences) | Active documentation |
| `docs/guides/LOCAL-FREE.md` | `zpostgressql` → `zpostgresql` | Active documentation |
| `docs/guides/NO-COST-MATRIX.md` | All `zpostgressql` → `zpostgresql` (2 occurrences) | Active documentation |
| `docs/guides/TROUBLESHOOTING.md` | All `zpostgressql` → `zpostgresql` (2 occurrences) | Active documentation |
| `docs/guides/INTEGRATION.md` | All `zpostgressql` → `zpostgresql` (4 occurrences) | Active documentation |
| `docs/guides/QUICKSTART.md` | `zpostgressql` → `zpostgresql` | Active documentation |
| `docs/claude-code-parity/BASELINE.md` | All `zpostgressql` → `zpostgresql` (3 occurrences) | Active documentation |
| `docs/engineering/ROADMAP.md` | All `zpostgressql` → `zpostgresql` (2 occurrences) | Active documentation |
| `docs/engineering/master-prompt-next.md` | All `zpostgressql` → `zpostgresql` (2 occurrences) | Active documentation |
| `docs/zpitr-implementation.md` | All `zpostgressql` → `zpostgresql` (3 occurrences) | Active documentation |
| `docs/compliance/EVIDENCE-MODEL.md` | `wal_source` example `zpostgressql` → `zpostgresql` | Compliance schema |
| `docs/zcoder-theme.md` | `zpostgressql` lifecycle → `zpostgresql` lifecycle | Theme documentation |
| `docs/superpowers/plans/2026-11-13-performance-optimization.md` | Container/network references updated | Planning documentation |
| `docs/migrations/zpostgressql-to-zpostgresql.md` | New file | Migration record |
| `docs/migrations/INFRASTRUCTURE-REPORT.md` | New file | Infrastructure report |
| `docs/migrations/DATA-INTEGRITY-REPORT.md` | New file | Data integrity report |

### zalive repository

| File | Change | Reason |
|------|--------|--------|
| `.env` | `DATABASE_URL`, `TEST_DATABASE_URL`, `ZALIVE_POSTGRES_HOST` `zpostgressql` → `zpostgresql` | Application connection |
| `.env.example` | `ZALIVE_POSTGRES_HOST` `zpostgressql` → `zpostgresql`; commented URLs | Environment configuration |
| `README.md` | Config table examples `zpostgressql` → `zpostgresql` | Documentation |

## Files NOT Modified (Historical — allowed to retain `zpostgressql`)

| File | Reason |
|------|--------|
| `zcoder/docs/audit/FINAL-REPORT.md` | Historical audit report |
| `zcoder/docs/audit/REPOSITORY-INVENTORY.md` | Historical inventory |
| `zcoder/docs/audit/TEST-RESULTS.md` | Historical test results |
| `zcoder/docs/audit/TASK-LEDGER.md` | Historical task ledger |
| `zcoder/docs/audit/repository-inventory.md` | Historical inventory |
| `zcoder/docs/audit/SUBSYSTEM-TEST-MATRIX.md` | Historical test matrix |
| `zcader/docs/audit/OLLAMA_MIGRATION_FULL_AUDIT_REPORT.md` | Historical migration audit |
| `zcoder/docs/audit/dependency-upgrade-report.md` | Historical dependency report |
| `zcoder/docs/audit/integration-test-report.md` | Historical integration report |
| `zcoder/docs/audit/build-lint-test-report.md` | Historical build report |
| `zcoder/docs/audit/ISSUE-BACKLOG.md` | Historical backlog |
| `zalive/Final-Report.md` | Historical final report |

## Generated/Cache Artifacts (Contain `zpostgressql` — Not Active Configuration)

| File | Reason |
|------|--------|
| `zcoder/src/zcoder.egg-info/PKG-INFO` | Generated package metadata artifact (not manually edited) |
| `zcoder/.pytest_cache/v/cache/nodeids` | Pytest cache (regenerated on each test run) |
| `zcoder/logs/docker-resource-audit-20261111-223233.log` | Historical log file from previous audit run |

## Updated Generated/Tracked Artifact

| File | Change |
|------|--------|
| `zcoder/pytest-structural.txt` | Replaced `zpostgressql` → `zpostgresql` (6 occurrences) — tracked test output log |

## Intentional Historical Reference (Migration Documentation)

| File | Line | Reason |
|------|------|--------|
| `zcoder/docs/migration/MIGRATION.md` | 42 | Shows "Old (legacy)" value `zpostgressql` as historical context of what was replaced |

## Semantic Notes

- `zpostgressql` in `MIGRATION.md:42` is retained as the "Old (legacy)" value in the migration documentation, showing what the previous value was. This is historical context, not an active reference.
- The `src/zcoder.egg-info/PKG-INFO` is a generated artifact and was not manually modified.
- No third-party dependencies, package names, or unrelated SQL identifiers were modified.
