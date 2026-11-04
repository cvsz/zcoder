# ZEAZ Docker Models + zcoder GGUF Integration Design for OpenCode-*

## Combined Infrastructure

This design integrates:
1. **OpenCode Zen free models** (via Docker Model Runner)
2. **zcoder existing GGUF models** (Qwen 1.5B and 7B)
3. **Docker Model Runner** for local model execution
4. **zcoder LLM pipeline** for agent operations

## Existing zcoder GGUF Models

The repository already ships with quantized Qwen models:

| Model File | Parameters | Quantization | Description |
|---|---|---|---|
| `models/qwen-1.5b-q4km.gguf` | 1.5B | Q4_K_M | Fast local coding and script generation |
| `models/qwen-7b-q4km.gguf` | 7B | Q4_K_M | Top-tier code intelligence and advanced media scripting |

**Configuration** (`src/zgpu/models_config.json`):
- `qwen2.5-coder-1.5b`: `qwen-1.5b-q4km.gguf`, Q4_K_M
- `qwen2.5-coder-7b`: `qwen-7b-q4km.gguf`, Q4_K_M

## Docker Model Runner Integration

### Pull and Run zcoder Models with DMR

```bash
# Pull models from Hugging Face (via DMR)
docker model pull hf.co/bartowski/Qwen2.5-Coder-1.5B-GGUF
docker model pull hf.co/bartowski/Qwen2.5-Coder-7B-GGUF

# Or tag and use locally
docker model tag hf.co/bartowski/Qwen2.5-Coder-1.5B-GGUF ai/qwen2.5-coder-1.5b
docker model tag hf.co/bartowski/Qwen2.5-Coder-7B-GGUF ai/qwen2.5-coder-7b

# Run interactively
docker model run ai/qwen2.5-coder-1.5b "Write a Python function for Fibonacci"
docker model run ai/qwen2.5-coder-7b "Analyze this codebase for security issues"
```

### DMR with OpenCode Zen Free Models

```bash
# Pull OpenCode Zen free models
docker model pull ai/devstral-small-2        # Fast coding
docker model pull ai/qwen3-coder              # Code generation
docker model pull ai/thoughtworks-qwq-32b     # Reasoning

# List available models
docker model ls
```

## zeaz-* Model Mapping to OpenCode-*

Map the zeaz repository names to actual model configurations:

| zeaz-* | Mapped Model | Provider | Use Case |
|---|---|---|---|
| `zeaz-auto` | `ai/devstral-small-2` | dmr | Auto-coding, task decomposition |
| `zeaz-coder` | `ai/qwen2.5-coder-1.5b` | dmr | Code generation, completion (fast) |
| `zeaz-coder` | `ai/qwen2.5-coder-7b` | dmr | Advanced code intelligence (preferred) |
| `zeaz-free` | Any OpenCode Zen `-free` model | opencode-zen | No-cost inference |
| `zeaz-local` | `ai/qwen2.5-coder-1.5b` (GGUF) | dmr | Local-only, privacy-focused |
| `zeaz-reasoning` | `ai/thoughtworks-qwq-32b` or `nemotron-3.5-lightning-free` | dmr | Complex reasoning, code analysis |

## OpenCode Configuration Design

### 1. DMR Provider Configuration

```json
// ~/.config/opencode/opencode.json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "dmr": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Docker Model Runner",
      "options": {
        "baseURL": "http://localhost:12434/v1"
      },
      "models": {
        "zeaz-auto": {
          "name": "ai/devstral-small-2",
          "max_tokens": 8192,
          "temperature": 0.7
        },
        "zeaz-coder": {
          "name": "ai/qwen2.5-coder-7b",
          "max_tokens": 32768,
          "temperature": 0.3
        },
        "zeaz-free": {
          "name": "deepseek-v4-flash-free",
          "description": "OpenCode Zen free model"
        },
        "zeaz-local": {
          "name": "ai/qwen2.5-coder-1.5b",
          "description": "zcoder GGUF model (local)"
        },
        "zeaz-reasoning": {
          "name": "nemotron-3.5-lightning-free",
          "thinking_budget": "medium"
        }
      }
    }
  }
}
```

### 2. zcoder LLM Server Integration

Start the zcoder LLM server with existing GGUF models:

```bash
# Start OpenAI-compatible server with zcoder models
cd /home/cvsz/zcoder
python -m zcoder.scripts.docker_entrypoint.py \
  python -m zcoder.main llm-server \
  --model qwen2.5-coder-7b \
  --quantization Q4_K_M
```

Or use the existing server.py:

```bash
python -m zcoder.src.zgpu.llm.server \
  --model-path models/qwen-7b-q4km.gguf \
  --quantization Q4_K_M \
  --host 0.0.0.0 \
  --port 8000
```

### 3. Docker Compose Setup

```yaml
# docker-compose.yml - ZEAZ models with OpenCode
services:
  model-runner:
    image: docker/model-runner:latest
    environment:
      - DOCKER_MODEL_RUNNER_API_KEY=dmr
    ports:
      - "12434:12434"
    volumes:
      - ./models:/models:ro  # Mount zcoder GGUF models
  
  opencode-agent:
    image: ghcr.io/opencode/opencode:latest
    environment:
      - OPENCODE_API_KEY=${OPENCODE_API_KEY:-}  # optional for free models
      - DMR_BASE_URL=http://host.docker.internal:12434/v1
    depends_on:
      - model-runner
    volumes:
      - ./:/workspace:rw
  
  zcoder-llm:
    build: .
    environment:
      - ZCODER_LLM_MODEL=qwen2.5-coder-7b
      - ZCODER_LLM_QUANTIZATION=Q4_K_M
    depends_on:
      - model-runner
```

## Migration Path from zeaz-platform

The z-platform was extracted from `cvsz/zeaz-platform` with these key integrations:

1. **Model allowlists** - explicit tracking in schemas (already in z-platform)
2. **GGUF model support** - zcoder already ships Qwen GGUF models
3. **Docker Model Runner** - new layer for local model execution
4. **OpenCode Zen gateway** - free model access via API key

### Migration Checklist

- [ ] Pull desired models via `docker model pull`
- [ ] Configure OpenCode with DMR provider
- [ ] Mount GGUF models in Docker Compose (`./models:/models:ro`)
- [ ] Test model routing with `opencode /models`
- [ ] Set up model allowlists in z-platform schemas
- [ ] Implement rollback paths for model version changes
- [ ] Document model dependencies and quantization requirements

## Cost & Performance Considerations

| Model | VRAM Required | Cost | Use Case |
|---|---|---|---|
| `qwen-1.5b-q4km.gguf` | ~2 GB | Free (local) | Fast coding, script generation |
| `qwen-7b-q4km.gguf` | ~14 GB | Free (local) | Top-tier code intelligence |
| `deepseek-v4-flash-free` | ~8 GB | Free (OpenCode Zen) | General coding, chat |
| `devstral-small-2` | ~4 GB | Free (OpenCode Zen) | Fast coding agent |
| `nemotron-3.5-lightning-free` | ~12 GB | Free (OpenCode Zen) | Reasoning, code analysis |

## Quick Start Commands

```bash
# 1. Enable Docker Model Runner in Docker Desktop
# 2. Pull models
docker model pull ai/qwen2.5-coder-7b
docker model pull ai/devstral-small-2
docker model pull deepseek-v4-flash-free

# 3. Mount and run with zcoder models
# Ensure models/ directory is accessible

# 4. Start OpenCode with DMR
opencode

# 5. Select model
# /models → select dmr/zeaz-coder (qwen2.5-coder-7b)
# Or: /models → select dmr/zeaz-free (deepseek-v4-flash-free)

# 6. Or use zcoder local GGUF server
python -m zcoder.src.zgpu.llm.server \
  --model-path models/qwen-7b-q4km.gguf \
  --port 8000
```

## Security & Compliance

1. **Model allowlists** - Tracked in z-platform schemas, enforce in OpenCode config
2. **Tenant isolation** - Separate model pools per workspace/tenant
3. **Data privacy** - GGUF models run entirely locally; no data leaves machine
4. **License compliance** - Qwen models use Apache 2.0; verify OpenCode Zen terms
5. **Rollback paths** - Tag Docker models with version digests for reproducibility