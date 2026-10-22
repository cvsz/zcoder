# Free-tier and local model endpoints

Reviewed on **2026-10-19** against provider documentation. This is a curated
list of verified compatible endpoints, not an exhaustive or permanent list of
free API offers. Providers may change quotas, model availability, account
eligibility, geography and prices without notice. **A free account is not a
guarantee that every model or request costs $0.** Check billing settings and
the selected model before enabling outbound inference.

The entries below are available to the ZCoder **multi-agent router** with
`zcoder --route ... --provider ... --model ...`. Other ZCoder CLI features
may still use Anthropic-specific clients. Selecting `--provider` does not
change those clients or automatically enforce `ZCODER_COST_POLICY`.

## Hosted APIs with documented no-charge allowances

| Provider | Router option | POST endpoint | Key variable | No-charge qualification | Official docs |
|---|---|---|---|---|---|
| Google Gemini | `gemini` | `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent` | `GEMINI_API_KEY` or `GOOGLE_API_KEY` | Selected models and supported countries only; free quotas vary | [API](https://ai.google.dev/api/generate-content), [pricing](https://ai.google.dev/gemini-api/docs/pricing) |
| GroqCloud | `groq` | `https://api.groq.com/openai/v1/chat/completions` | `GROQ_API_KEY` | Free-plan model/request/token limits apply | [API](https://console.groq.com/docs/api-reference), [limits](https://console.groq.com/docs/rate-limits) |
| OpenRouter | `openrouter` | `https://openrouter.ai/api/v1/chat/completions` | `OPENROUTER_API_KEY` | Select `openrouter/free` or an eligible `:free` model; other models can charge | [free router](https://openrouter.ai/openrouter/free/apps), [API](https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request) |
| Cerebras | `cerebras` | `https://api.cerebras.ai/v1/chat/completions` | `CEREBRAS_API_KEY` | Model-specific free-tier quotas and context limits | [API](https://inference-docs.cerebras.ai/api-reference/chat-completions), [pricing](https://inference-docs.cerebras.ai/support/pricing) |
| Mistral AI | `openai_compatible` | `https://api.mistral.ai/v1/chat/completions` | `OPENAI_COMPATIBLE_API_KEY` | Studio Free mode offers limited monthly API usage | [API](https://docs.mistral.ai/api), [limits](https://docs.mistral.ai/admin/billing-usage/usage-limits) |
| NVIDIA NIM API Catalog | `openai_compatible` | `https://integrate.api.nvidia.com/v1/chat/completions` | `OPENAI_COMPATIBLE_API_KEY` | Free serverless developer access, subject to program terms and limits; not an enterprise production entitlement | [API](https://docs.api.nvidia.com/nim/reference/llm-apis), [developer access](https://docs.api.nvidia.com/nim/docs/product) |
| Cloudflare Workers AI | `openai_compatible` | `https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1/chat/completions` | `OPENAI_COMPATIBLE_API_KEY` | Workers AI offers an allocation; requires account ID, token and an eligible Workers AI model | [compatibility](https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/), [pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/) |

For Cloudflare, supply the base URL **excluding** `/chat/completions`:

```bash
export OPENAI_COMPATIBLE_API_KEY="your-cloudflare-token"
zcoder --route "Explain this code" --provider openai_compatible \
  --base-url "https://api.cloudflare.com/client/v4/accounts/YOUR_ACCOUNT_ID/ai/v1" \
  --model "@cf/meta/llama-3.1-8b-instruct"
```

The example model is illustrative; verify its current availability and free
allowance before use. Custom gateways are operator-controlled outbound
destinations. Never point to a server you do not trust.

Mistral and NVIDIA use the same generic adapter with their respective base
URLs `https://api.mistral.ai/v1` and
`https://integrate.api.nvidia.com/v1`. Choose a supported model identifier
and set `OPENAI_COMPATIBLE_API_KEY` to that service's credential.

## Locally hosted inference (no provider token charge)

Local inference is not literally costless: it uses your CPU/GPU, memory,
electricity and downloaded model storage. Start the model server and load a
compatible model before routing a request.

| Runtime | Router option | POST endpoint | Base URL to configure | Official docs |
|---|---|---|---|---|
| Ollama (native API) | `ollama` | `http://localhost:11434/api/chat` | `http://localhost:11434` (default) | [API](https://docs.ollama.com/api/chat) |
| LM Studio | `openai_compatible` | `http://localhost:1234/v1/chat/completions` | `http://localhost:1234/v1` | [OpenAI compatibility](https://lmstudio.ai/docs/developer/openai-compat) |
| vLLM | `openai_compatible` | `http://localhost:8000/v1/chat/completions` | `http://localhost:8000/v1` | [Server](https://docs.vllm.ai/en/latest/serving/online_serving/openai_compatible_server/) |
| llama.cpp server | `openai_compatible` | `http://localhost:8080/v1/chat/completions` | `http://localhost:8080/v1` | [Server](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md) |
| ZCoder offline stub | `local` | None — no network request | None | [Quickstart](../../QUICKSTART.md) |

Example LM Studio request (use the actual model identifier reported by your
local server, not the Anthropic default):

```bash
zcoder --route "Review this function" --provider openai_compatible \
  --base-url "http://localhost:1234/v1" --model "my-loaded-model"
```

`openai_compatible` also accepts any explicitly configured HTTP(S) server
that implements non-streaming OpenAI Chat Completions at
`<base-url>/chat/completions`. A bearer token can be passed using `--api-key`
or `OPENAI_COMPATIBLE_API_KEY`; it is optional for local servers.

## Existing providers that are not necessarily free

| Provider | Endpoint | Note |
|---|---|---|
| Anthropic | `https://api.anthropic.com/v1/messages` | Paid API; ZCoder's default provider |
| xAI | `https://api.x.ai/v1/chat/completions` | Verify current offers before use; not classified as free |
| Hugging Face Inference Providers | `https://router.huggingface.co/v1/chat/completions` | Compatible with `openai_compatible`, but [current billing](https://huggingface.co/docs/inference-providers/pricing) should **not** be presumed free |
| SambaNova SambaCloud | `https://api.sambanova.ai/v1/chat/completions` | [SambaNova docs](https://docs.sambanova.ai/docs/en/integrations/vscode) describe free accounts and API setup, but verify the current inference allowance; compatible with `openai_compatible` |
| GitHub Models | Formerly `https://models.github.ai/inference/chat/completions` | **Discontinued**: [GitHub documentation](https://docs.github.com/en/github-models) says its inference API is no longer available; do not use this endpoint |

## Configuration and safe operation

```bash
# Keys apply to their matching --provider when using --route.
export GROQ_API_KEY="your-groq-key"
zcoder --route "Review this patch" --provider groq --model "openai/gpt-oss-20b"

export OPENROUTER_API_KEY="your-openrouter-key"
zcoder --route "Explain this diff" --provider openrouter --model "openrouter/free"

export GEMINI_API_KEY="your-gemini-key"
zcoder --route "Create a test plan" --provider gemini --model "YOUR_FREE_TIER_MODEL"

export CEREBRAS_API_KEY="your-cerebras-key"
zcoder --route "Review the architecture" --provider cerebras --model "YOUR_ELIGIBLE_MODEL"
```

- Explicit `--provider` overrides `ZCODER_PROVIDER`. The default remains
  `anthropic`, and the router does not silently substitute a paid provider.
- Explicit `--base-url` overrides `ZCODER_BASE_URL`; for hosted provider
  presets, overrides replace the host **without changing** that provider's
  endpoint path. For a custom URL ending in `/v1`, use `openai_compatible`.
- Groq, OpenRouter and Cerebras require their API keys before making a request.
  The `local` stub and local-compatible servers require no key.
- Rate limits, quota exhaustion, billing configuration and model-specific
  compatibility errors remain provider responses, not recoverable free traffic.
- Do not commit API keys or copy credentials into a release executable.
