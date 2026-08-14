# UPGRADE-07: PostgreSQL Control Plane & Distributed Fencing Tokens

## Overview
Upgrade-07 scales the control plane to clustered PostgreSQL backends with concurrency protections:

1. **Atomic Job Claiming:**
   - PostgreSQL `SELECT ... FOR UPDATE SKIP LOCKED` query patterns ensuring zero double-claiming across worker pools.

2. **Monotonic Fencing Tokens:**
   - Generation tokens attached to attempts, rejecting stale writes from disconnected or timed-out workers.

3. **Tenant-Scoped Partitioning:**
   - Strict tenant schema isolation and indexed queries for multi-tenant scaling.
