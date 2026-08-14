# Upgrade v1.40.0 — Compliance Local Sessions & Model Registry Health Audit

**Audit Date:** August 13, 2026
**Project Baseline:** ZCoder v1.39.0 -> v1.40.0
**Status:** COMPLETE & PASSING (523 tests passing)

---

## 1. Sources Checked

1. **Anthropic Official Documentation & Guides:**
   - Platform Overview & Release Notes (`platform.claude.com/docs`)
   - Models Overview (`platform.claude.com/docs/en/about-claude/models/overview`)
   - Model Deprecations & Retirements (`platform.claude.com/docs/en/about-claude/model-deprecations`)
   - Data Residency / Inference Geography (`platform.claude.com/docs/en/manage-claude/data-residency`)
   - Compliance API Specification (`platform.claude.com/docs/en/manage-claude/compliance-api`)
   - Managed Agents Documentation & Changelog (`platform.claude.com/docs/en/agent-frameworks/managed-agents`)
   - Claude Enterprise & Workspaces API (`platform.claude.com/docs/en/manage-claude/enterprise`)

---

## 2. Dates Checked

- **Current Audit Execution Date:** 2026-08-13
- **Latest Anthropic Release Notes Checked:** August 2026 (including Aug 7 Managed Agents budgets, Aug 5 Opus 4.1 retirement, Aug 7 Sonnet 5 price stabilization, and August Compliance API local sessions expansion)

---

## 3. Complete Candidate-Feature Matrix

| Feature / Area | Anthropic Platform State (Aug 2026) | ZCoder Baseline (v1.39.0) | Audit Finding / Disposition | Action in v1.40.0 |
|---|---|---|---|---|
| **Compliance Local Sessions** | `GET /v1/compliance/apps/sessions/local` + `{id}` + `{id}/messages` for Cowork & Claude Code local sessions | Not implemented (only chats/projects/orgs) | **P0 GAP** — Public beta for enterprise auditability | **IMPLEMENTED** in `claude_compliance_api.py` and wired to CLI (`main.py`) |
| **Opus 5 `inference_geo`** | `inference_geo="us"` is supported on `claude-opus-5` (1.1x pricing multiplier) | Marked as "unconfirmed" in `claude_opus5.py` and omitted from `INFERENCE_GEO_SUPPORTED` | **P0 GAP** — Confirmed supported in live documentation | **IMPLEMENTED** — added to `INFERENCE_GEO_SUPPORTED` and updated `claude_opus5.py` |
| **Opus 4.1 Retirement** | `claude-opus-4-1-20250805` retirement scheduled date was `2026-08-05` (passed) | Listed in `DEPRECATED_MODELS` (still callable) | **P0 GAP** — Retirement date passed; API returns errors | **IMPLEMENTED** — promoted to `RETIRED_MODELS` in `claude_models.py` |
| **Sonnet 5 Pricing** | $3/$15 per MTok standard price is permanent (Sep 1 price increase was cancelled) | Code contained date-conditional logic claiming $2/$10 intro ending Aug 31 | **P1 GAP** — Stale promo date comparison | **IMPLEMENTED** — updated `claude_sonnet5.py` and `claude_models.py` to permanent standard pricing |
| **Managed Agents Session Budgets** | Hard spend budget in USD cents on `create_session` and `update_session_budget` | Fully implemented in v1.39.0 | Confirmed COMPLETE | Verified & tested |
| **Managed Agents `inference_geo`** | `inference_geo` supported in agent model configuration | Fully implemented in v1.39.0 | Confirmed COMPLETE | Verified & tested |
| **Managed Agents Advisor Roster** | Multiagent roster advisor configuration supported | Implemented in v1.39.0 | Confirmed COMPLETE | Verified & tested |
| **`anthropic-workspace-id`** | AWS Platform request header scoping requests to workspace | Handled via `ANTHROPIC_AWS_WORKSPACE_ID` and WIF | Confirmed NON-GAP (request header, not response metadata) | Documented |
| **AI Content Marking / Provenance** | Machine-readable provenance signals in generated files | Artifact system records generation metadata | Confirmed NON-GAP | Documented |

---

## 4. Current Repo Status

- **Repository Root:** `/home/cvsz/zcoder`
- **Active Release:** `v1.40.0`
- **Test Suite Results:**
  - `tests/test_claude_compliance_api.py`: 34 passed
  - `tests/test_claude_models_deprecation.py`: 8 passed
  - `tests/test_claude_opus5.py`: 14 passed
  - `tests/test_claude_sonnet5.py`: 12 passed
  - `tests/test_cli_wiring.py`: 74 passed
  - **Full test suite:** 523 passed, 1 skipped (optional textual TUI), 0 failed.

---

## 5. Gaps Found & Implemented

1. **Compliance API Local Session Endpoints:**
   - Added `ComplianceApiClient.list_local_sessions(user_ids, limit, page)`
   - Added `ComplianceApiClient.get_local_session(session_id)`
   - Added `ComplianceApiClient.get_local_session_messages(session_id, limit, page)`
   - Added CLI commands: `--compliance-local-sessions-list`, `--compliance-local-session-info`, `--compliance-local-session-messages`

2. **`claude-opus-5` Data Residency:**
   - Added `"claude-opus-5"` to `INFERENCE_GEO_SUPPORTED` in `claude_models.py`.
   - Updated `claude_opus5.py` module docstring and `validate_inference_geo()` to treat US data residency pinning as confirmed supported.

3. **`claude-opus-4-1-20250805` Retirement:**
   - Promoted `claude-opus-4-1-20250805` from `DEPRECATED_MODELS` to `RETIRED_MODELS`.
   - `--model-info claude-opus-4-1-20250805` now reports the exact retirement date (`2026-08-05`) and recommends `claude-opus-4-8`.

4. **Claude Sonnet 5 Permanent Pricing:**
   - Updated `claude_models.py` catalog notes.
   - Updated `claude_sonnet5.py` `current_pricing()` to return permanent standard pricing ($3 input / $15 output per MTok).

---

## 6. Confirmed Non-Gaps

- **Managed Agents Session Budgets:** Implemented in `claude_agents_sdk.py` with full hard budget lifecycle support (`create_session(budget_usd_cents=...)`, `update_session_budget()`, `get_session()`).
- **Managed Agents Inference Geo:** Implemented with nested `{model: {inference_geo: "us"}}` encoding.
- **Managed Agents Session Advisor:** Implemented with `build_multiagent_config(..., advisor_model=...)`.
- **Response Workspace Header:** Confirmed that `anthropic-workspace-id` is a request header on AWS Claude Platform, not a response header from the Messages API.

---

## 7. Tests Added and Updated

- **`tests/test_claude_compliance_api.py`:**
  - `test_list_local_sessions_endpoint_and_params`
  - `test_get_local_session_endpoint`
  - `test_get_local_session_messages_endpoint`
  - `test_cmd_compliance_local_sessions_list`
  - `test_cmd_compliance_local_session_info`
  - `test_cmd_compliance_local_session_messages`
- **`tests/test_claude_opus5.py`:**
  - Updated `test_inference_geo_requested_confirmed_supported`
  - Updated `test_call_geo_sends_payload_cleanly`
- **`tests/test_claude_sonnet5.py`:**
  - Updated `test_standard_pricing_always_returned`
  - Updated `test_standard_pricing_ignores_historical_promo_date`
  - Updated `test_estimate_cost_usd_uses_standard_rate`
- **`tests/test_claude_models_deprecation.py`:**
  - Updated `test_check_retired_opus_4_1`
  - Updated `test_cmd_model_info_warns_on_retired_id`
  - Updated `test_cmd_check_deprecated_reports_retired_hit`
  - Updated `test_upgrade_source_ids_includes_retired`

---

## 8. Migration and Backward Compatibility

- All new Compliance API methods and CLI options are strictly additive.
- The `current_pricing(as_of=...)` function in `claude_sonnet5.py` retains its parameter signature for complete backward compatibility.
- The `DEPRECATED_MODELS` dict remains defined and accessible even while empty.
