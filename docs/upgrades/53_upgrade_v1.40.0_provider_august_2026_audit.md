# Upgrade v1.40.0 — Compliance Local Sessions & Model Registry Health Audit

**Audit Date:** August 13, 2026
**Project Baseline:** ZCoder v1.39.0 -> v1.40.0
**Status:** COMPLETE & PASSING (523 tests passing)

---

## 1. Sources Checked

1. **PROVIDER_CREDENTIAL_OR_CONFIG Official Documentation & Guides:**
   - Platform Overview & Release Notes (`platform.provider.com/docs`)
   - Models Overview (`platform.provider.com/docs/en/about-provider/models/overview`)
   - Model Deprecations & Retirements (`platform.provider.com/docs/en/about-provider/model-deprecations`)
   - Data Residency / Inference Geography (`platform.provider.com/docs/en/manage-provider/data-residency`)
   - Compliance API Specification (`platform.provider.com/docs/en/manage-provider/compliance-api`)
   - Managed Agents Documentation & Changelog (`platform.provider.com/docs/en/agent-frameworks/managed-agents`)
   - provider Enterprise & Workspaces API (`platform.provider.com/docs/en/manage-provider/enterprise`)

---

## 2. Dates Checked

- **Current Audit Execution Date:** 2026-08-13
- **Latest PROVIDER_CREDENTIAL_OR_CONFIG Release Notes Checked:** August 2026 (including Aug 7 Managed Agents budgets, Aug 5 Opus 4.1 retirement, Aug 7 Sonnet 5 price stabilization, and August Compliance API local sessions expansion)

---

## 3. Complete Candidate-Feature Matrix

| Feature / Area | PROVIDER_CREDENTIAL_OR_CONFIG Platform State (Aug 2026) | ZCoder Baseline (v1.39.0) | Audit Finding / Disposition | Action in v1.40.0 |
|---|---|---|---|---|
| **Compliance Local Sessions** | `GET /v1/compliance/apps/sessions/local` + `{id}` + `{id}/messages` for Cowork & external coding assistant local sessions | Not implemented (only chats/projects/orgs) | **P0 GAP** — Public beta for enterprise auditability | **IMPLEMENTED** in `provider-specific module` and wired to CLI (`main.py`) |
| **Opus 5 `inference_geo`** | `inference_geo="us"` is supported on `provider model ID` (1.1x pricing multiplier) | Marked as "unconfirmed" in `provider-specific module` and omitted from `INFERENCE_GEO_SUPPORTED` | **P0 GAP** — Confirmed supported in live documentation | **IMPLEMENTED** — added to `INFERENCE_GEO_SUPPORTED` and updated `provider-specific module` |
| **Opus 4.1 Retirement** | `provider model ID` retirement scheduled date was `2026-08-05` (passed) | Listed in `DEPRECATED_MODELS` (still callable) | **P0 GAP** — Retirement date passed; API returns errors | **IMPLEMENTED** — promoted to `RETIRED_MODELS` in `provider-specific module` |
| **Sonnet 5 Pricing** | $3/$15 per MTok standard price is permanent (Sep 1 price increase was cancelled) | Code contained date-conditional logic claiming $2/$10 intro ending Aug 31 | **P1 GAP** — Stale promo date comparison | **IMPLEMENTED** — updated `provider-specific module` and `provider-specific module` to permanent standard pricing |
| **Managed Agents Session Budgets** | Hard spend budget in USD cents on `create_session` and `update_session_budget` | Fully implemented in v1.39.0 | Confirmed COMPLETE | Verified & tested |
| **Managed Agents `inference_geo`** | `inference_geo` supported in agent model configuration | Fully implemented in v1.39.0 | Confirmed COMPLETE | Verified & tested |
| **Managed Agents Advisor Roster** | Multiagent roster advisor configuration supported | Implemented in v1.39.0 | Confirmed COMPLETE | Verified & tested |
| **`PROVIDER_CREDENTIAL_OR_CONFIG-workspace-id`** | AWS Platform request header scoping requests to workspace | Handled via `PROVIDER_CREDENTIAL_OR_CONFIG` and WIF | Confirmed NON-GAP (request header, not response metadata) | Documented |
| **AI Content Marking / Provenance** | Machine-readable provenance signals in generated files | Artifact system records generation metadata | Confirmed NON-GAP | Documented |

---

## 4. Current Repo Status

- **Repository Root:** `/home/cvsz/zcoder`
- **Active Release:** `v1.40.0`
- **Test Suite Results:**
  - `tests/test_provider-specific module`: 34 passed
  - `tests/test_provider-specific module`: 8 passed
  - `tests/test_provider-specific module`: 14 passed
  - `tests/test_provider-specific module`: 12 passed
  - `tests/test_cli_wiring.py`: 74 passed
  - **Full test suite:** 523 passed, 1 skipped (optional textual TUI), 0 failed.

---

## 5. Gaps Found & Implemented

1. **Compliance API Local Session Endpoints:**
   - Added `ComplianceApiClient.list_local_sessions(user_ids, limit, page)`
   - Added `ComplianceApiClient.get_local_session(session_id)`
   - Added `ComplianceApiClient.get_local_session_messages(session_id, limit, page)`
   - Added CLI commands: `--compliance-local-sessions-list`, `--compliance-local-session-info`, `--compliance-local-session-messages`

2. **`provider model ID` Data Residency:**
   - Added `"provider model ID"` to `INFERENCE_GEO_SUPPORTED` in `provider-specific module`.
   - Updated `provider-specific module` module docstring and `validate_inference_geo()` to treat US data residency pinning as confirmed supported.

3. **`provider model ID` Retirement:**
   - Promoted `provider model ID` from `DEPRECATED_MODELS` to `RETIRED_MODELS`.
   - `--model-info provider model ID` now reports the exact retirement date (`2026-08-05`) and recommends `provider model ID`.

4. **provider Sonnet 5 Permanent Pricing:**
   - Updated `provider-specific module` catalog notes.
   - Updated `provider-specific module` `current_pricing()` to return permanent standard pricing ($3 input / $15 output per MTok).

---

## 6. Confirmed Non-Gaps

- **Managed Agents Session Budgets:** Implemented in `provider-specific module` with full hard budget lifecycle support (`create_session(budget_usd_cents=...)`, `update_session_budget()`, `get_session()`).
- **Managed Agents Inference Geo:** Implemented with nested `{model: {inference_geo: "us"}}` encoding.
- **Managed Agents Session Advisor:** Implemented with `build_multiagent_config(..., advisor_model=...)`.
- **Response Workspace Header:** Confirmed that `PROVIDER_CREDENTIAL_OR_CONFIG-workspace-id` is a request header on AWS provider Platform, not a response header from the Messages API.

---

## 7. Tests Added and Updated

- **`tests/test_provider-specific module`:**
  - `test_list_local_sessions_endpoint_and_params`
  - `test_get_local_session_endpoint`
  - `test_get_local_session_messages_endpoint`
  - `test_cmd_compliance_local_sessions_list`
  - `test_cmd_compliance_local_session_info`
  - `test_cmd_compliance_local_session_messages`
- **`tests/test_provider-specific module`:**
  - Updated `test_inference_geo_requested_confirmed_supported`
  - Updated `test_call_geo_sends_payload_cleanly`
- **`tests/test_provider-specific module`:**
  - Updated `test_standard_pricing_always_returned`
  - Updated `test_standard_pricing_ignores_historical_promo_date`
  - Updated `test_estimate_cost_usd_uses_standard_rate`
- **`tests/test_provider-specific module`:**
  - Updated `test_check_retired_opus_4_1`
  - Updated `test_cmd_model_info_warns_on_retired_id`
  - Updated `test_cmd_check_deprecated_reports_retired_hit`
  - Updated `test_upgrade_source_ids_includes_retired`

---

## 8. Migration and Backward Compatibility

- All new Compliance API methods and CLI options are strictly additive.
- The `current_pricing(as_of=...)` function in `provider-specific module` retains its parameter signature for complete backward compatibility.
- The `DEPRECATED_MODELS` dict remains defined and accessible even while empty.
