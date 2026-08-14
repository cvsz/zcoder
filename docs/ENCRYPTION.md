# ZCoder Encryption & Key Management Boundary

## Cryptographic Standards
- **Data in Transit**: Enforced TLS 1.3 for API ingress, database connections, and external LLM/GitHub calls.
- **Data at Rest**: AES-256-GCM authenticated encryption for sensitive payloads and backup archives.
- **API Key Hashes**: High-entropy SHA-256 digests. Raw secrets are never persisted plaintext.
- **Secret Management**: Externalized via `SecretRef` patterns (Vault, Kubernetes Secrets, AWS Secrets Manager).
