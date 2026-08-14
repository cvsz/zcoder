# UPGRADE-12: Public REST API v1, TypeScript SDK & Rate Limiting

## Overview
Upgrade-12 introduces the stable external developer integration surface:

1. **Public REST API v1 (`/api/v1/`):**
   - Endpoints for organizations, projects, jobs, webhooks, and entitlements.
   - Comprehensive OpenAPI v3 specification snapshot.

2. **Idempotency & Rate Limiting:**
   - Standard `Idempotency-Key` caching and sliding-window rate limiting (`X-RateLimit-*` headers).

3. **TypeScript SDK (`zcoder-sdk.ts`):**
   - Type-safe client library for Node.js, Deno, and browser runtimes.
