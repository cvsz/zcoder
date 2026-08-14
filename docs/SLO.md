# ZCoder Service Level Objectives (SLOs) and Alerting Framework

## Service Level Indicators (SLIs) & Objectives

| Service | Indicator | SLI Definition | Target SLO |
| :--- | :--- | :--- | :--- |
| **API** | Availability | `sum(rate(zcoder_api_requests_total{status!~"5.."}[5m])) / sum(rate(zcoder_api_requests_total[5m]))` | **99.9%** (30-day window) |
| **API** | Latency | `sum(rate(zcoder_api_duration_seconds_bucket{le="0.5"}[5m])) / sum(rate(zcoder_api_duration_seconds_count[5m]))` | **99% < 500ms** |
| **Workers** | Job Scheduling | `sum(rate(zcoder_job_wait_seconds_bucket{le="10.0"}[5m])) / sum(rate(zcoder_job_wait_seconds_count[5m]))` | **95% queued jobs claimed < 10s** |
| **Outbox** | Mutation Latency | `sum(rate(zcoder_outbox_delivery_latency_seconds_bucket{le="30.0"}[5m])) / sum(rate(zcoder_outbox_delivery_latency_seconds_count[5m]))` | **99% delivered < 30s** |
| **Backups** | Freshness | `time() - zcoder_backup_last_success_timestamp < 93600` (26h) | **100% daily** |
| **Disaster Recovery** | Drill Recency | `time() - zcoder_backup_last_restore_drill_timestamp < 2592000` (30d) | **100% monthly** |

## Core Alerts
- **APIUnavailable**: High 5xx rate > 1% over 5m window.
- **WorkerFleetEmpty**: `zcoder_worker_active == 0` while `zcoder_jobs_queued > 0`.
- **DatabaseUnavailable**: `zcoder_db_pool_in_use == max` or DB health check failure.
- **OutboxStuck**: `zcoder_outbox_pending > 50` for > 15m.
- **BackupStale**: `time() - zcoder_backup_last_success_timestamp > 93600`.
- **RestoreDrillOverdue**: `time() - zcoder_backup_last_restore_drill_timestamp > 2592000`.
