# Runbook: Usage Metering Ingestion Error

## Severity: Medium
**Condition**: Discrepancy in recorded token usage or delayed billing ledger event ingestion.

## Diagnostic Steps
1. Check `usage_ledger` deduplication table for duplicate insertion rejects.
2. Inspect worker outbox status for pending usage events:
   ```sql
   SELECT COUNT(*) FROM usage_ledger WHERE occurred_at < NOW() - INTERVAL '1 hour';
   ```
3. Issue corrective billing adjustment records if needed without modifying historical ledger rows.
