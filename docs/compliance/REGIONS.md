# ZCoder Multi-Region Architecture & Topology

## Regional Model
ZCoder explicitly differentiates regional concerns:
- **Control Plane Region**: Authoritative single-writer coordinator (`us-east-1`).
- **Database Region**: Authoritative PostgreSQL primary database.
- **Worker Regions**: Distributed worker fleets deployed regionally (`us-east-1`, `eu-west-1`, `ap-southeast-1`).
- **Artifact Regions**: Object storage buckets located regionally.
- **Provider Inference Geo**: LLM provider inference geography (`us`, `eu`, `global`).

## Failure & Partition Model
- If a worker region fails, jobs are rerouted only to compliant regions permitted by `OrganizationResidencyPolicy`.
- If no allowed regions remain healthy, execution pauses in `WAITING_CAPACITY` rather than violating residency boundaries.
