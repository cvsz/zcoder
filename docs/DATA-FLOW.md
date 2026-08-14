# ZCoder End-to-End Data Flow Map

```text
1. Ingress (TLS 1.3 Termination)
     ↓ [HTTPS / JSON]
2. API Control Plane (auth_oidc / RequestContext)
     ↓ [SQL / SET LOCAL app.current_org]
3. PostgreSQL HA (Row-Level Security & Fencing)
     ↓ [Lease Claim / SKIP LOCKED]
4. Regional Worker (residency_models / policy_engine)
     ├── Anthropic API [TLS 1.3 / Inference Geo]
     ├── GitHub API [OAuth / GitHub App Installation]
     └── Artifact Store [AES-256 GCM Encrypted Objects]
```
