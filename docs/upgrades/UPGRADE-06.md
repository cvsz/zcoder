# UPGRADE-06: Multi-Tenant Outbox & Idempotent Worker State Machines

## Overview
Upgrade-06 hardens asynchronous job execution with transactional outbox patterns and durable state machines:

1. **Transactional Outbox:**
   - Guarantees event delivery across worker process lifecycles with deduplication keys.

2. **Durable Worker State Machine:**
   - States: `READY` -> `CLAIMED` -> `PLANNING` -> `EXECUTING` -> `VALIDATING` -> `COMPLETED` / `FAILED`.

3. **Lease Management:**
   - Worker heartbeat leases preventing split-brain job processing.
