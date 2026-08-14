# UPGRADE-21: Durable Engineering Runtime & Checkpoint Stores

## Overview
Upgrade-21 introduces the durable, crash-consistent engineering store and orchestrator runtime:

1. **Durable Engineering Store (`SQLiteEngineeringStore` & `PostgresEngineeringStore`):**
   - SQLite WAL mode execution providing crash consistency under hard process failure (`SIGKILL`).
   - Tables: `tasks`, `attempts`, and `checkpoints`.

2. **Checkpoint & Snapshot Primitives:**
   - Atomic checkpoints with state snapshots allowing task resumption and rollback.

3. **Autonomous Engineering Loop Orchestration:**
   - Durable task lifecycle management (`EngineeringOrchestrator`).
