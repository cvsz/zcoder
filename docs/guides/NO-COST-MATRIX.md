# Zero-Cost & Offline Capability Matrix

`zcoder` provides a 100% free, offline, and credential-free operational tier. This document catalogs all local capabilities, zero-cost backends, and their runtime characteristics.

---

## 1. Zero-Cost Architecture Overview

The zero-cost architecture allows engineers and air-gapped environments to run autonomous coding workflows with zero commercial API keys and zero cloud dependencies.

```text
 ┌────────────────────────────────────────────────────────┐
 │                   zcoder CLI / SDK                     │
 └───────────────────────────┬────────────────────────────┘
                             │
       ┌─────────────────────┼─────────────────────┐
       ▼                     ▼                     ▼
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│ Local Model  │      │ Local SQLite │      │ Local Object │
│ (Ollama/vLLM)│      │  Task Store  │      │   Storage    │
└──────────────┘      └──────────────┘      └──────────────┘
```

---

## 2. Capability Matrix

| Dimension | Enterprise / Cloud Tier | Zero-Cost / Local Tier |
| :--- | :--- | :--- |
| **LLM Inference** | Anthropic Claude 3.7 / Opus / Sonnet | Ollama / vLLM / llama.cpp / Local OpenAI-compat |
| **Persistence** | Multi-tenant PostgreSQL 16 (HA) | SQLite (WAL mode, crash-consistent) |
| **Object Storage** | AWS S3 / GCS / Azure Blob | Sandboxed Local Filesystem (`~/.zcoder/storage`) |
| **Telemetry** | OpenTelemetry Collector / Datadog | In-Memory / SQLite Local Analytics |
| **Notifications** | SendGrid Email / Slack Webhooks | Console Output / In-App Notification Center |
| **Cost Policy** | Budget caps with paid fallbacks | `CostPolicy.ZERO_COST_ONLY` (Strict zero paid calls) |

---

## 3. Supported Local Model Runtimes

| Runtime | Protocol | Default Endpoint | Recommended Models |
| :--- | :--- | :--- | :--- |
| **Ollama** | OpenAI compatible / Native | `http://localhost:11434/v1` | `qwen2.5-coder:32b`, `deepseek-coder-v2`, `codellama` |
| **vLLM** | OpenAI compatible | `http://localhost:8000/v1` | `Qwen/Qwen2.5-Coder-32B-Instruct`, `Mistral-Small` |
| **llama.cpp** | OpenAI compatible | `http://localhost:8080/v1` | GGUF quantized models (Q4_K_M, Q8_0) |
| **LM Studio** | OpenAI compatible | `http://localhost:1234/v1` | Developer local testing models |

---

## 4. Cost Policy Enforcement

When `--zero-cost` or `CostPolicy.ZERO_COST_ONLY` is enabled:
- Network calls to `api.anthropic.com` or other commercial providers are strictly blocked.
- Any task requesting a paid model will automatically route to the best matching local model or fail fast.
- Billing meters remain inactive and report zero charges.

---

## 5. Offline Synthesis Mode (`ZCODER_LOCAL_MODE`)

Separate from the local-model tier above, `ZCODER_LOCAL_MODE=1` (or
`true`/`yes`) enables a **pure offline synthesis tier with no model
engine at all**:

| Dimension | Local-Model Tier (Ollama/vLLM) | Offline Synthesis Tier |
| :--- | :--- | :--- |
| **Model engine** | Required (downloaded weights) | None — deterministic in-process synthesis |
| **Network** | None | None |
| **API key** | Not required | Not required (`zcoder.main._api_key` returns a placeholder) |
| **Generation** | Real local inference | `[zCoder local offline response]` stub |
| **Git helpers** | Real local inference | Deterministic commit-message/PR/review stubs |
| **Live mode** | Real local inference | Streamed echo fallback |
| **Prompt optimize/score** | Real local inference | Rule-based enhancement / heuristic scoring |
| **Missing-key behavior** | Error outside local mode | Works only when `ZCODER_LOCAL_MODE` is set |

Notes:
- Outside local mode a missing `ANTHROPIC_API_KEY` is a hard error — the
  CLI never silently pretends to generate.
- A network/auth failure in the git helper synthesizes an offline reply
  for that one call only; it does **not** flip the process into local
  mode for every later call.
- Purpose: trying the CLI, running the test suite, air-gapped smoke
  tests, and deterministic CI fixtures.
