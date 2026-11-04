# ZCoder Evidence Model & Single Source of Truth

## Evidence Tiers
- **E0 (Implementation)**: Source code written and structurally complete.
- **E1 (Unit)**: Function-level logic verified in isolation.
- **E2 (Integration)**: Multi-component workflows verified against mock/embedded stores.
- **E3 (System)**: Multi-process concurrency and live database constraints verified.
- **E4 (Live External)**: Live external provider or infrastructure integration tested.
- **E5 (Production Observed)**: Live telemetry metrics observed under operational production load.

## Status Classifications
- `PASS`: Complete requirements fulfilled with matching evidence tier.
- `PASS_WITH_LIMITATIONS`: Core architecture and automation proven; documented environmental boundaries remain.
- `FAIL`: Requirement unmet or broken.
- `STALE`: Previously valid evidence that has exceeded its TTL.

## PITR Evidence Schema (zPITR Service)

The `zPITR` containerized service (`deploy/docker/zpitr/`, `docker-compose.zpitr.yml`) emits Release Gate evidence for the Point-in-Time Recovery gate row (`PITR`) in `scripts/release_gate.py --check`.

Evidence files are written to `docs/evidence/pitr-qualification-<SHA>.json` (schema version 1):

| Field | Type | Description |
|---|---|---|
| `schema` | integer | Evidence schema version (currently `1`). |
| `sha` | string | Release-candidate Git SHA this evidence qualifies (first 8 chars used in filename). |
| `wal_archive_verified` | boolean | `true` when WAL archive continuity was verified during the drill. |
| `restore_drill_passed` | boolean | `true` when the isolated restore drill completed successfully. |
| `tested_at` | string | UTC ISO-8601 timestamp ending in `Z` when the drill executed. |
| `evidence_ref` | string | Reference in form `ZPITR-REHEARSAL/<drill-id>`. |
| `evidence_sha256` | string | 64-hex SHA-256 digest of the backup/drill proof artifact. |
| `details.wal_source` | string | Source of WAL stream (e.g. `zPostgreSQL`). |
| `details.restore_target` | string | Recovery target environment (e.g. `isolated-sandbox`). |
| `details.method` | string | Recovery method (e.g. `pg_receivewal+basebackup`). |

Example:

```json
{
  "schema": 1,
  "sha": "f7de74125291232d4dce137b22c3629f9fac108c",
  "wal_archive_verified": true,
  "restore_drill_passed": true,
  "tested_at": "2026-11-04T16:50:00Z",
  "evidence_ref": "ZPITR-REHEARSAL/DRILL-20261104-165000",
  "evidence_sha256": "aaaa...aaaa",
  "details": {
    "wal_source": "zPostgreSQL",
    "restore_target": "isolated-sandbox",
    "method": "pg_receivewal+basebackup"
  }
}
```

This evidence binds the PITR drill to the exact release-candidate SHA; any code/config change after the drill invalidates the evidence and requires re-execution on a new RC (per `exec-planning.md` §2, rule 12).
