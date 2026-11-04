# ZCoder End-to-End Data Flow Map

```text
1. Ingress (TLS 1.3 Termination)
     ↓ [HTTPS / JSON]
2. API Control Plane (auth_oidc / RequestContext)
     ↓ [SQL / SET LOCAL app.current_org]
3. PostgreSQL HA (Row-Level Security & Fencing)
     ↓ [Lease Claim / SKIP LOCKED]
     └── WAL Generator (wal_level=replica)
            ↓ [Streaming Replication Protocol]
4. zPITR Service [deploy/docker/zpitr/]
      ├── pg_receivewal daemon → zpitr_wal_archive volume (continuous WAL)
      ├── pg_basebackup → zpitr_base_backups volume (periodic snapshots)
      └── Restore Drill Orchestrator → Isolated Sandbox (recovery.signal + restore_command)
            ↓ [Evidence Emit]
5. Release Gate [scripts/release_gate.py]
     ← docs/evidence/pitr-qualification-<SHA>.json (schema v1)
4. Regional Worker (residency_models / policy_engine)
     ├── Local llama.cpp [loopback HTTP]
     ├── GitHub API [OAuth / GitHub App Installation]
     └── Artifact Store [AES-256 GCM Encrypted Objects]
```
