# zcoder Developer Portal & API Integration Guide

Welcome to the **zcoder Developer Portal**. This document provides the official technical reference for integrating with the zcoder Public REST API (`/api/v1/`), SDKs (Python & TypeScript), and Webhooks.

---

## 1. Quickstart & Authentication

All API requests require authentication via an API Key passed in the `Authorization` header as a Bearer token:

```http
GET /api/v1/health HTTP/1.1
Host: api.zcoder.internal
Authorization: Bearer zc_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
Content-Type: application/json
```

### 1.1 Generating API Keys

API keys are created per tenant organization and assigned specific role ceilings:
- `zc_live_...` — Production API keys (SHA-256 hashed in database).
- `zc_test_...` — Sandbox / Mock environment keys.

---

## 2. API Endpoints (`/api/v1/`)

### 2.1 Organizations & Projects
- `GET /api/v1/organizations` — Retrieve organization details and quota limits.
- `GET /api/v1/projects` — List registered projects.
- `POST /api/v1/projects` — Register a new project repository.

### 2.2 Engineering Tasks & Jobs
- `POST /api/v1/jobs` — Submit an autonomous engineering or coding job.
- `GET /api/v1/jobs/{job_id}` — Get job execution status, attempt counters, and logs.
- `POST /api/v1/jobs/{job_id}/cancel` — Gracefully terminate an active job.

### 2.3 Idempotency Keys
All mutating POST/PUT requests support the `Idempotency-Key` header:
```http
POST /api/v1/jobs HTTP/1.1
Idempotency-Key: 7b84f3e6-5c74-4b55-a0c5-e5f8f9b9a691
```
Replaying a request with the same idempotency key returns the cached result without creating duplicate tasks. If a payload mismatch is detected, HTTP `409 Conflict` is returned.

### 2.4 Rate Limiting
Requests are rate-limited per principal using a bounded sliding window algorithm:
```http
X-RateLimit-Limit: 120
X-RateLimit-Remaining: 118
X-RateLimit-Reset: 1723632000
```
When exhausted, endpoints return `HTTP 429 Too Many Requests` with a JSON error envelope.

---

## 3. SDK Client Libraries

### 3.1 Python SDK (`zcoder.interfaces.sdk.client`)

```python
from zcoder.interfaces.sdk.client import ZCoderClient

client = ZCoderClient(
    api_key="zc_live_your_key_here",
    base_url="https://api.zcoder.internal",
)

# Submit a coding task
job = client.submit_job(
    project_id="proj_backend",
    task_description="Refactor user authentication to support OAuth2 PKCE",
    model="claude-3-7-sonnet-20250219",
)

print(f"Submitted Job ID: {job.id}, Status: {job.status}")
```

### 3.2 TypeScript SDK (`zcoder-sdk.ts`)

```typescript
import { ZCoderClient } from './zcoder-sdk';

const client = new ZCoderClient({
  apiKey: process.env.ZCODER_API_KEY!,
  baseUrl: 'https://api.zcoder.internal',
});

async function run() {
  const job = await client.submitJob({
    projectId: 'proj_frontend',
    taskDescription: 'Fix navigation regression on mobile viewport',
  });
  console.log(`Job Created: ${job.id}`);
}

run().catch(console.error);
```

---

## 4. Webhook Subscriptions & Verification

zcoder can deliver real-time notifications on job completion or failure.

### 4.1 HMAC-SHA256 Signature Verification
Each webhook delivery includes a signature header `X-ZCoder-Signature`:

```python
import hmac
import hashlib


def verify_signature(payload_bytes: bytes, secret: str, received_signature: str) -> bool:
    expected = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, received_signature)
```

### 4.2 SSRF Protection
Outbound webhook dispatchers enforce strict validation:
- RFC 1918 private IPv4/IPv6 ranges blocked unless explicitly whitelisted in local dev.
- Cloud metadata endpoints (`169.254.169.254`) unconditionally blocked.
