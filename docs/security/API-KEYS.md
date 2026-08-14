# ZCoder API Keys Guide

## 1. Key Format & Identification
API Keys follow a secure structure:
```text
zck_<org_slug>_<key_id>_<secret_payload>
```
Example: `zck_alpha_09f1_v3A8kL9...`

- Key prefixes are non-secret and logged for auditability.
- Raw secrets are never logged or stored plaintext.

## 2. Rotation & Revocation
Keys can be instantly revoked by setting status to `REVOKED`. Invalidation is enforced immediately at the database query layer.
