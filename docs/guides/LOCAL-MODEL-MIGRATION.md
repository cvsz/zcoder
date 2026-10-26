# Local Model Migration Status

## Default prompt and routing

The normal prompt path and default router use the local llama.cpp chat
endpoint at `127.0.0.1:8080`. The request model label defaults to
`zqwen2.5-coder-7b-instruct-q4_k_m` and can be overridden with
`ZCODER_MODEL`.

The local client requires loopback HTTP and rejects redirects. The model
server must already be running with a readable GGUF model loaded.

## Migrated call paths

- One-shot prompt and file generation.
- Interactive command-line chat.
- `--live` REPL generation with ambient context and local conversation history.
- Default multi-agent routing, including local classifier and specialist
  generation through `Coder` (no local-mode stub response).
- Git commit message, pull request text, changelog, review, and blame
  generation.
- GitHub review, issue triage, commit summary, and pull request description
  generation. GitHub REST data access still uses its separate GitHub token.
- Prompt optimization, prompt scoring, and A/B evaluation.
- Retrieval-augmented answer generation.
- `--cite` and `--rag` answer generation from local source files, with source IDs validated locally.
- `--structured`, `--structured-analyse`, and `--structured-extract` use the
  local model; schema validation remains client-side and currently checks
  required fields.
- `--advisor` performs one local guidance generation followed by a local
  executor generation. Extra provider tools are rejected explicitly.
- Commands that still instantiate provider-specific SDK clients or call
  provider-only endpoints fail closed under local provider settings instead
  of silently sending requests to Anthropic. This includes advanced thinking,
  fine-grained provider tool streaming, web search, remote files, hosted
  batch/agent operations, and account admin or compliance commands. These
  features remain unavailable until they gain
  local implementations. `ZCODER_LOCAL_MODE=1` takes precedence over
  `--provider` and `ZCODER_PROVIDER`, including stale or invalid values.
- Web-console chat and streaming send requests only to the configured
  loopback llama-server. The frontend does not collect or persist model API
  keys; legacy request `api_key` fields are ignored. Its model selector lists
  only `ZCODER_MODEL`, not the remote provider catalog.
- Evaluation case generation and local judging.
- `--stream` uses loopback SSE text streaming and requests usage accounting.
  It rejects non-loopback URLs, blocks redirects, and sends no provider
  credentials. Provider-specific `--stream-tools` and advanced thinking
  remain unavailable in local-only mode.
- `--code-agent` uses the configured loopback OpenAI-compatible
  `/v1/chat/completions` endpoint. It converts tool schemas and history to
  local function-call format, and accepts constrained JSON tool-call
  envelopes when the model does not emit native `tool_calls`. API-key values
  are ignored; remote MCP tunneling remains unavailable in local-only mode.

## Remaining work

An inventory on 2026-10-26 found hosted model-provider URL or client references
in 28 source modules. The web server has one upstream model route, and it is
loopback-only. The remaining references include model-specific generation,
capabilities, admin and compliance operations, remote files, identity federation,
and orchestration. Each path must be migrated to a local implementation or
removed with an explicit unsupported result before a complete local-only
release can be claimed. This CLI audit did not prove that every module is
reachable from supported commands, so the references require a call-path
review. Reproduce the inventory with:

```bash
rg -l 'api\.anthropic\.com|anthropic\.Anthropic|AsyncAnthropic|messages\.create|api\.voyageai\.com|generativelanguage\.googleapis\.com|api\.x\.ai|api\.groq\.com|openrouter\.ai|api\.cerebras\.ai' src/zcoder --glob '*.py'
```

`--live` previously created an Anthropic SDK client using a placeholder key
and generated fabricated offline replies. It now calls the loopback client;
focused tests confirm both normal and `ZCODER_LOCAL_MODE` paths. Each
remaining feature needs behavior-specific acceptance tests; replacing
endpoint strings alone is insufficient for streaming, tool use, remote file
storage, administration, or compliance operations.

The local code-agent path has unit coverage for loopback URL enforcement,
credential omission, native and JSON tool-call conversion, history conversion,
and zero-cost accounting. A CPU smoke run using
`qwen-1.5b-q4km.gguf` completed a real `Read` tool call against `README.md`
and returned `LOCAL_AGENT_READ_OK`. This verifies one model and one read-only
tool flow; edit, shell, MCP, and other model behavior still need dedicated
acceptance coverage.

The `--stream` CLI path has a local SSE unit suite and a CPU smoke run against
`qwen-1.5b-q4km.gguf`; it returned `LOCAL_STREAM_OK` and reported usage from
the server. The loopback server was stopped after the run.

The local-only CLI guard test exercises all 150 direct-provider CLI
destinations through argument parsing and `main()` dispatch, confirming each
fails closed before its provider-specific handler is reached.

`ZCODER_LOCAL_MODE=1` blocks Anthropic SDK client construction and the known
hosted model API domains used by the repository (Anthropic, Voyage, Gemini,
xAI, Groq, OpenRouter, Cerebras, and OpenAI) at the shared outbound HTTP
boundaries. This applies to library entry points as well as CLI dispatch;
GitHub and unrelated non-model integrations remain available. The guard does
not establish a local implementation for every feature listed above.

## Acceptance checks

```bash
python -m pytest tests/unit
ruff check .
black --check .
zcoder --health-check
zcoder -p "Reply with exactly LOCAL_OK"
```

Real model acceptance requires running these commands against each supported
GGUF file on the target operating system and hardware.

On 2026-10-25, a CPU-only smoke inference with
`/home/cvsz/zgpu/qwen-7b-q4km.gguf` returned the requested `LOCAL_OK` through
`127.0.0.1:8080`. This confirms one local generation path; it does not cover
other models, operating systems, hardware offload, or representative task
quality.
