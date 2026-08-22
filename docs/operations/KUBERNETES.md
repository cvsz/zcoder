# ZCoder Kubernetes & Helm Deployment Architecture

## Architecture Overview
ZCoder production deployments separate the **API Control Plane** from the **Horizontal Worker Fleet**.

```text
               Ingress / Load Balancer (TLS Termination)
                                 │
                 ┌───────────────┴───────────────┐
                 ▼                               ▼
       ZCoder API Replica 1             ZCoder API Replica 2
                 │                               │
                 └───────────────┬───────────────┘
                                 ▼
                     PostgreSQL HA Database
                                 │
                 ┌───────────────┼───────────────┐
                 ▼               ▼               ▼
           Worker Pool:    Worker Pool:    Worker Pool:
             Standard         Sandbox         Trusted
```

## Security & Reliability Controls
1. **Non-Root Execution**: Container runs with UID/GID `1000:1000`, `readOnlyRootFilesystem: true`, `allowPrivilegeEscalation: false`, and capabilities dropped (`ALL`).
2. **Readiness vs Liveness**:
   - `/health/live`: Liveness probe — static `{"status": "alive"}`, always HTTP 200 (internal process health only; avoids pod restart storms on DB transient blips).
   - `/health/ready`: Readiness probe — checks database connectivity; returns HTTP 200 `{"status": "ready"}` or fail-closed HTTP 503 `{"status": "unavailable"}` (safely gates incoming HTTP traffic).
   - `/metrics`: Prometheus scrape endpoint — `text/plain; version=0.0.4` exposition from the ZCoder metrics registry.
   - `/health`: Legacy combined check (`{"status": "ok", ...}`); retained for backward compatibility only.
3. **Graceful Worker Draining**: On `SIGTERM`, worker sets state to `DRAINING`, stops claiming jobs, completes in-flight executions within `terminationGracePeriodSeconds` (default 120s), and safely releases remaining leases before termination.
4. **NetworkPolicy**: Strict ingress/egress boundaries limiting traffic between API, Workers, PostgreSQL, OpenTelemetry Collector, and authorized external endpoints (GitHub API, Anthropic API).
5. **No Plaintext Secrets**: Helm values reference Kubernetes Secret names and keys rather than embedding credentials.
