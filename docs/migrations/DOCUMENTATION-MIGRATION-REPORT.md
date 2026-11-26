# Documentation Migration Report — zpostgressql → zpostgresql

## Updated Documents (Active Documentation)

The following documents were updated to replace `zpostgressql` with `zpostgresql`
as the canonical Docker PostgreSQL deployment identifier:

### zcoder repository

| File | Section/Context |
|------|-----------------|
| `docs/migrations/zpostgressql-to-zpostgresql.md` | New migration guide |
| `docs/migrations/INFRASTRUCTURE-REPORT.md` | New infrastructure report |
| `docs/migrations/DATA-INTEGRITY-REPORT.md` | New data integrity report |
| `docs/migrations/CONFIGURATION-MIGRATION-REPORT.md` | New configuration report |
| `docs/migration/MIGRATION.md` | PostgreSQL host name fix section; compose example; v1.60.0 notes |
| `docs/operations/deployment.md` | Container name, network, health check, troubleshooting |
| `docs/operations/dr-rehearsal.md` | Shared cluster reference |
| `docs/operations/zpitr-implementation.md` | Mermaid diagram, environment variables, network |
| `docs/guides/LOCAL-FREE.md` | Shared PostgreSQL container reference |
| `docs/guides/NO-COST-MATRIX.md` | Shared PostgreSQL container reference |
| `docs/guides/TROUBLESHOOTING.md` | `docker exec` command, environment variable |
| `docs/guides/INTEGRATION.md` | Environment variable, compose service, depends_on |
| `docs/guides/QUICKSTART.md` | Shared PostgreSQL section header |
| `docs/claude-code-parity/BASELINE.md` | Queue/Jobs row, Container row, Network row |
| `docs/engineering/ROADMAP.md` | Shared container and network reference |
| `docs/engineering/master-prompt-next.md` | Docker service and network reference |
| `docs/zpitr-implementation.md` | Sidecar container, WAL streaming source |
| `docs/compliance/EVIDENCE-MODEL.md` | `wal_source` field example value |
| `docs/zcoder-theme.md` | Shared lifecycle reference |
| `docs/superpowers/plans/2026-11-13-performance-optimization.md` | Container and network reference |

### zalive repository

| File | Section/Context |
|------|-----------------|
| `.env` | `DATABASE_URL`, `TEST_DATABASE_URL`, `ZALIVE_POSTGRES_HOST` |
| `.env.example` | `ZALIVE_POSTGRES_HOST`, commented `DATABASE_URL` examples |
| `README.md` | Configuration table examples |

## Documents Preserved With `zpostgressql` (Historical)

The following documents retain `zpostgressql` because they are historical records
discussing the original migration source or past state:

### zcoder repository

| File | Reason |
|------|--------|
| `docs/audit/FINAL-REPORT.md` | Historical audit report |
| `docs/audit/REPOSITORY-INVENTORY.md` | Historical inventory |
| `docs/audit/TEST-RESULTS.md` | Historical test results |
| `docs/audit/TASK-LEDGER.md` | Historical task ledger |
| `docs/audit/repository-inventory.md` | Historical inventory |
| `docs/audit/SUBSYSTEM-TEST-MATRIX.md` | Historical test matrix |
| `docs/audit/OLLAMA_MIGRATION_FULL_AUDIT_REPORT.md` | Historical migration audit (documents migration TO zpostgressql) |
| `docs/audit/dependency-upgrade-report.md` | Historical dependency report |
| `docs/audit/integration-test-report.md` | Historical integration report |
| `docs/audit/build-lint-test-report.md` | Historical build report |
| `docs/audit/ISSUE-BACKLOG.md` | Historical backlog |
| `src/zcoder.egg-info/PKG-INFO` | Generated artifact |

### zalive repository

| File | Reason |
|------|--------|
| `Final-Report.md` | Historical final report documenting original setup |

## Documentation Consistency

All active documentation now consistently describes:
- `zpostgresql` as the current Docker PostgreSQL deployment
- Correct container name: `zpostgresql`
- Correct database hostname: `zpostgresql`
- Correct environment variables: `ZCODER_POSTGRES_HOST=zpostgresql`, `ZALIVE_POSTGRES_HOST=zpostgresql`
- Correct volume: `zpostgresql_data`
- Correct network: `zpostgresql_network`
- Correct connection strings: `postgresql://...@zpostgresql:5432/...`
