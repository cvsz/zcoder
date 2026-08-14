# UPGRADE-08: OpenTelemetry Observability & Prometheus Metrics

## Overview
Upgrade-08 equips zcoder with distributed tracing, standardized RED metrics, and health telemetry:

1. **OpenTelemetry (OTel) Integration:**
   - Distributed trace propagation across HTTP API, worker execution processes, and model invocations.

2. **Prometheus Metrics Exporter:**
   - Real-time gauge and counter metrics for active workers, queued jobs, error rates, and token consumption.

3. **Structured Logging:**
   - JSON structured logging with correlation IDs (`trace_id`, `span_id`, `tenant_id`).
