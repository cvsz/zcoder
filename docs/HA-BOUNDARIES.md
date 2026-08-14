# ZCoder High Availability (HA) & Operational Boundaries

## Architecture Boundaries
- **Control Plane**: Single-writer authoritative PostgreSQL primary. Horizontal stateless API instances.
- **Worker Fleet**: Distributed horizontal workers coordinating via `FOR UPDATE SKIP LOCKED` and monotonic fencing tokens.
- **Database Failover**: External infrastructure responsibility (e.g. AWS RDS Multi-AZ, Patroni HA). ZCoder auto-reconnects with exponential backoff upon primary promotion.
