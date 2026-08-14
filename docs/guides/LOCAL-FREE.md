# Running zcoder 100% Free & Offline (Local Guide)

This guide walks you through setting up and running **zcoder** entirely locally with zero API keys, zero cloud costs, and full privacy.

---

## 1. Prerequisites

1. **Python 3.9+** installed.
2. **Local Model Engine** (e.g., [Ollama](https://ollama.ai/)):
   ```bash
   ollama pull qwen2.5-coder:7b
   ```

---

## 2. Quick Setup

1. Clone and install `zcoder`:
   ```bash
   git clone https://github.com/cvsz/zcoder.git
   cd zcoder
   pip install -e .
   ```

2. Verify local execution without any `ANTHROPIC_API_KEY`:
   ```bash
   zcoder --version
   ```

---

## 3. Running Coding Tasks with Local Models

Use the `--local-model` flag or set your local model configuration:

```bash
zcoder --local-model ollama/qwen2.5-coder:7b "Refactor utils.py to use pathlib"
```

### 3.1 Custom Local Endpoints
If running vLLM or llama.cpp:
```bash
zcoder \
  --openai-base-url http://localhost:8000/v1 \
  --model custom-local-model \
  "Add unit tests for security.py"
```

---

## 4. Local Persistence & Storage

- **Database:** Local SQLite database at `~/.zcoder/engineering.db` with WAL mode enabled.
- **Artifacts:** Saved locally in `./artifacts` or `~/.zcoder/storage`.
- **Telemetry:** Stored in local SQLite file or stdout; no third-party tracking.
