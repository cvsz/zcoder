# SUPER ULTRA AI ORC — ARCHITECTURE AUDIT REPORT

**Audit Date:** 2026-11-04
**Commit:** fffcf08
**Version:** 1.60.0
**Scope:** Provider-Neutral AI Runtime & Model Registry (Section 5-6 of full-master-aee.md)

---

## CURRENT STATE ANALYSIS

### 5. PROVIDER-NEUTRAL AI RUNTIME — GAP ANALYSIS

#### Existing Implementation
- `src/zcoder/agent/orchestration/providers.py` — Partial provider abstraction with:
  - Provider choice enumeration (gemini, xai, groq, openrouter, cerebras, nvidia, openai_compatible, ollama, local)
  - Provider defaults with base URLs, paths, env keys, auth schemes
  - Base URL validation (scheme-checked, file/ftp rejected)
  - Local stub mode for testing
  - NVIDIA model chain parsing
- `src/zcoder/core/provider_policy.py` — Local-only policy enforcement:
  - `local_only_enabled()` check
  - `ensure_anthropic_api_allowed()` — fails in local-only mode
  - `enforce_outbound_url_policy()` — blocks hosted model APIs
  - `create_anthropic_client()` — conditional client creation
- `src/zcoder/agent/capabilities/` — Capability modules exist but are provider-specific:
  - `code.py` — Claude Code compatible agent loop with tools
  - `embeddings.py` — Voyage AI embeddings (not Anthropic)
  - `stream.py` — Fine-grained tool streaming
  - `thinking.py` — Thinking configurations
- `src/zcoder/enterprise/local_ai_stack.py` — Hardware profiler and local adapters:
  - `HardwareProfiler` — CPU, RAM, GPU detection
  - `ModelFitEstimator` — FITS/MAYBE/DOES_NOT_FIT classification
  - `OllamaAdapter` (planned), `VLLMAdapter` (planned), `GenericOpenAIAdapter` (planned)

#### Gaps Against Document Requirements

| Requirement | Status | Evidence |
|---|---|---|
| Provider abstraction supporting native APIs | Partial | Missing: Anthropic, Gemini, Ollama full adapters |
| Provider abstraction supporting OpenAI-compatible APIs | Partial | openai_compatible provider exists but minimal |
| Provider abstraction supporting Anthropic-compatible APIs | Partial | Anthropic conformance file exists but limited |
| Provider abstraction supporting Gemini APIs | None | Not implemented |
| Provider abstraction supporting Ollama | Partial | Mentioned in defaults but no adapter |
| Provider abstraction supporting llama.cpp | None | Not implemented |
| Provider abstraction supporting vLLM | Partial | Mentioned in local_ai_stack.py but not in providers.py |
| Provider abstraction supporting NVIDIA NIM | None | Not implemented |
| Configurable self-hosted gateways | Partial | openai_compatible is generic but minimal |
| Separate: Provider, Model, Runtime, Capability, Credential, Pricing, Routing policy, Execution policy | Not done | All conflated in current implementation |
| Normalized capability contract | Not done | Capabilities are feature-specific, not contract-driven |
| Capability contract: text_generation | Partially | Via provider calls but not normalized |
| Capability contract: code_generation | Partially | Via code agent but not contract-driven |
| Capability contract: reasoning | Not done | No standardized contract |
| Capability contract: streaming | Partial | stream.py exists but limited |
| Capability contract: tool_calling | Partial | Via MessagingCapability protocol |
| Capability contract: structured_output | Not done | No standardized contract |
| Capability contract: image_input | Partial | vision.py exists for Anthropic only |
| Capability contract: image_generation | None | Not implemented |
| Capability contract: audio_input | None | Not implemented |
| Capability contract: audio_generation | None | Not implemented |
| Capability contract: speech_to_text | None | Not implemented |
| Capability contract: text_to_speech | None | Not implemented |
| Capability contract: realtime_audio | None | Not implemented |
| Capability contract: video_input | None | Not implemented |
| Capability contract: video_generation | None | Not implemented |
| Capability contract: video_editing | None | Not implemented |
| Capability contract: embeddings | Partial | voyageai.py exists but provider-specific |
| Capability contract: reranking | None | Not implemented |
| Capability contract: computer_use | None | Not implemented |
| Capability contract: long_context | Partial | Context windows in MODEL_CATALOG but not contract-driven |
| Capabilities have evidence and confidence metadata | Not done | No metadata framework |
| Distinguish: Native/Adapter/Experimental/Unsupported/Unknown | Not done | No classification system |

#### Key Findings

1. **Provider abstraction is incomplete** — Only has base URL/defaults, no actual API client implementations for most providers
2. **No capability contract** — Capabilities are implemented per-feature without a normalized contract
3. **Model registry is insufficient** — MODEL_CATALOG has basic metadata but missing many fields required by the document
4. **No routing policy** — No hardware-aware, cost-aware, or reliability-aware routing
5. **Local-only enforcement exists** but could be strengthened (no silent paid fallback)
6. **Hardware profiler exists** but not integrated with routing decisions
7. **No evidence/confidence metadata** on capabilities

#### Priority Actions

1. **HIGH** — Implement normalized capability contract with all 21 capability types
2. **HIGH** — Build model registry with full metadata (provider ID, model ID, display name, family, release date, lifecycle, context window, output tokens, modalities, reasoning, tool calling, streaming, structured output, pricing, rate limits, regional restrictions, data retention, hardware requirements, quantization, deprecation, verification timestamp)
3. **HIGH** — Implement provider adapters for: Gemini, Ollama, vLLM, NVIDIA NIM
4. **MEDIUM** — Implement capability evidence and confidence metadata framework
5. **MEDIUM** — Implement hardware-aware cost-aware reliability-aware routing
6. **LOW** — Remove/advertise only verified capabilities

---

### 6. MODEL REGISTRY AND INTELLIGENT ROUTING — GAP ANALYSIS

#### Existing Implementation
- `src/zcoder/agent/models/registry.py` — Claude model catalog with:
  - MODEL_CATALOG dict with: display_name, tier, context_window, max_output, price_in, price_out, thinking, effort_default, notes
  - RETIRED_MODELS, DEPRECATED_MODELS
  - MODEL_ID_ALIASES
  - list_models(), model_info(), check_deprecated(), flag_retired_deprecated()
  - Account verification via API calls
- `src/zcoder/agent/models/preflight.py` — Model capability resolver:
  - Resolves model metadata via API or offline fallback to MODEL_CATALOG
  - ModelUnavailableError for unknown models
- `src/zcoder/agent/models/sonnet5.py`, `opus5.py`, `fable5.py`, `haiku45.py` — Model-specific implementations

#### Gaps Against Document Requirements

| Requirement | Status | Evidence |
|---|---|---|
| Provider ID per model record | Partial | MODEL_CATALOG has no provider_id field |
| Model ID per model record | Yes | Model IDs are the keys |
| Display name per model record | Yes | In MODEL_CATALOG |
| Model family per model record | Not done | Not in current catalog |
| Release date per model record | Not done | Not in current catalog |
| Availability per model record | Not done | Not in current catalog |
| Lifecycle state per model record | Not done | Not in current catalog |
| Context window per model record | Yes | In MODEL_CATALOG |
| Max output tokens per model record | Yes | In MODEL_CATALOG |
| Input modalities per model record | Not done | Not in current catalog |
| Output modalities per model record | Not done | Not in current catalog |
| Reasoning support per model record | Not done | Not in current catalog |
| Tool calling per model record | Not done | Not in current catalog |
| Streaming per model record | Not done | Not in current catalog |
| Structured output per model record | Not done | Not in current catalog |
| Pricing tiers per model record | Partial | price_in, price_out but no tiers |
| Rate limits per model record | Not done | Not in current catalog |
| Regional restrictions per model record | Not done | Not in current catalog |
| Data retention policy per model record | Not done | Not in current catalog |
| Local hardware requirements per model record | Not done | Not in current catalog |
| Quantization per model record | Not done | Not in current catalog |
| Deprecation date per model record | Partial | DEPRECATED_MODELS, RETIRED_MODELS |
| Verification timestamp per model record | Not done | Not in current catalog |
| Model discovery | Partial | list_models() exists |
| Manual model registration | Not done | No API for manual registration |
| Capability probing | Not done | No systematic capability probing |
| Provider health checks | Not done | No health check framework |
| Model deprecation warnings | Partial | RETIRED_MODELS, DEPRECATED_MODELS |
| Model migration recommendations | Not done | No recommendation system |
| Context-aware routing | Not done | No routing engine |
| Hardware-aware local routing | Partial | HardwareProfiler exists but not integrated |
| Cost-aware routing | Not done | No cost-aware routing |
| Reliability-aware routing | Not done | No reliability-aware routing |
| Tenant-specific model policies | Not done | No tenant policies |

#### Key Findings

1. **Model registry missing critical fields** — Only has ~5 of ~30+ required fields
2. **No provider_id** — Models don't track which provider they belong to
3. **No lifecycle state** — No mechanism for model deprecation/availability tracking
4. **No modality tracking** — Input/output modalities not recorded
5. **No pricing tiers** — Only flat price_in/price_out
6. **No rate limits** — No rate limit metadata
7. **No regional restrictions** — No geographic availability tracking
8. **No data retention policy** — No data handling policy per model
9. **No hardware requirements** — No quantization/context requirements tracking
10. **Routing engine missing** — No context-aware, hardware-aware, cost-aware, reliability-aware routing

#### Priority Actions

1. **HIGH** — Expand model registry with all required metadata fields
2. **HIGH** — Implement model discovery and manual registration
3. **HIGH** — Implement capability probing per model
4. **MEDIUM** — Implement provider health check framework
5. **MEDIUM** — Implement model deprecation warning system
6. **MEDIUM** — Implement migration recommendations
7. **LOW** — Add tenant-specific model policies (future work)

---

## OVERALL RECOMMENDATION

The repository has a foundation for provider-neutral routing and model cataloging, but significant work is needed to:

1. Implement the full normalized capability contract (21 capability types with evidence/confidence metadata)
2. Expand the model registry to include all required fields (30+ fields per model)
3. Build provider adapters for missing providers (Gemini, Ollama, vLLM, NVIDIA NIM)
4. Implement routing policies (hardware-aware, cost-aware, reliability-aware)
5. Create model discovery, health checking, and deprecation management

These improvements should be implemented in dependency order: capability contract → model registry → provider adapters → routing policies.