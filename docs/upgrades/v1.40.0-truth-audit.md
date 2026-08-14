# Forensic Truth Audit for ZCoder v1.40.0

**Audit Date:** August 13, 2026
**Auditor:** ZCoder Truth & Conformance Audit
**Authoritative Sources:**
- Claude Platform Release Notes (latest entry: 2026-08-11)
- Anthropic Models Overview & Pricing (verified: 2026-08-13)
- Anthropic Managed Agents Specification (verified: 2026-08-07)
- Anthropic Compliance API Specification (verified: 2026-08-11)

---

## 1. Previous Gate Claims Disproved

| Claim | Previous Status | Authoritative Reality | Code Impact | Fixed |
|---|---|---|---|---|
| **Claude Sonnet 5 Standard Price** | Claimed $3.00 in / $15.00 out standard price | On August 10, 2026, Anthropic announced that the planned price increase to $3/$15 for September 1 was cancelled. The introductory rate of **$2.00 / $10.00** per MTok is now the permanent standard price. | `claude_sonnet5.py`, `claude_models.py`, `claude_cost_optimizer.py`, `claude_metrics.py`, `claude_tokens.py` previously held $3/$15. | Fixed across all modules to $2.00/$10.00. |
| **`anthropic-workspace-id` Header Role** | Treated purely as a request header for AWS WIF | `anthropic-workspace-id` is an official Claude API **response header** returned by Anthropic on all Messages/API endpoints to identify the workspace resolving the request. | `resilience.py` and response handling did not parse or surface `anthropic-workspace-id`. | Added `extract_response_metadata` in `resilience.py` to capture `workspace_id`, `request_id`, and rate limits. |

---

## 2. Previous Gate Claims Verified

- **Compliance API Local Sessions (`GET /v1/compliance/apps/sessions/local`):** Verified released on 2026-08-11 (public beta for Claude Enterprise).
- **Claude Opus 4.1 Retirement:** Verified deprecated/retired on 2026-08-05.
- **Claude Opus 5 Data Residency (`inference_geo`):** Verified supported with 1.1x multiplier.
- **Managed Agents Spend Cap:** Verified released on 2026-08-07 (`budget_usd_cents` and `budget_reached`).

---

## 3. Conformance Manifest

See `anthropic-conformance.yaml` for the canonical machine-readable specification.
