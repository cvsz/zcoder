# Local Inference with Ollama

This guide configures the primary ZCoder prompt workflow to use a local
model through Ollama. It does not require a hosted model credential.

## Prerequisites

- Python 3.12 or later and the ZCoder development dependencies.
- `ollama` running locally on loopback (`http://127.0.0.1:11434`).
- Local GGUF models stored in `/zdata/models/`:
  - `zcoder-flash.gguf`
  - `zcoder-pro.gguf`
  - `zcoder-max.gguf`
  - `zcoder-promax.gguf`

## Configure and run ZCoder

```bash
cd ~/zcoder
make setup
export ZCODER_BASE_URL=http://127.0.0.1:11434/v1
export OLLAMA_BASE_URL=http://127.0.0.1:11434
export ZCODER_PROVIDER=ollama
export ZCODER_MODEL=zcoder-pro
zcoder -p "Review this source file" --file src/example.py
```

## Runtime behavior and limits

- `zcoder -p`, `--file`, `--interactive`, and `--route` use the local Ollama
  client by default.
- The local client accepts only loopback HTTP URLs and refuses HTTP redirects.
- A running Ollama service is required. Missing
  local inference dependencies return an error; they do not produce a
  synthetic coding answer.
- Some specialized legacy CLI features are still being migrated. Their
  availability is documented in the main README and release notes; do not
  assume every optional feature uses this local path yet.
- Local inference still consumes CPU/GPU, memory, electricity, and disk space.

## Local persistence

- SQLite is the default for a single-user installation.
- PostgreSQL-backed commands use the shared Docker container `zpostgressql`
  and the isolated `zcoder_db` database.
- Local artifacts and runtime state are stored under the configured ZCoder
  data directory.
