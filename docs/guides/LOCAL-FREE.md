# Local GGUF Inference

This guide configures the primary ZCoder prompt workflow to use a local
GGUF model through llama.cpp. It does not require a hosted model credential.

## Prerequisites

- Python 3.10 or later and the ZCoder development dependencies.
- `llama-server` built with support for the target hardware.
- A local GGUF file, for example:
  - `/home/cvsz/zgpu/qwen-7b-q4km.gguf`
  - `/home/cvsz/zgpu/qwen-1.5b-q4km.gguf`

## Start the model server

```bash
llama-server \
  --model /home/cvsz/zgpu/qwen-7b-q4km.gguf \
  --host 127.0.0.1 \
  --port 8080 \
  --ctx-size 4096
```

Keep the server bound to loopback. To use the smaller model, change the model
path to `qwen-1.5b-q4km.gguf`.

## Configure and run ZCoder

```bash
cd ~/zcoder
make setup
export ZCODER_BASE_URL=http://127.0.0.1:8080/v1
export ZCODER_MODEL=zqwen2.5-coder-7b-instruct-q4_k_m
zcoder -p "Review this source file" --file src/example.py
```

The model name is a local request label; llama.cpp serves the GGUF file loaded
at startup. To verify the CLI, run `zcoder -p "Reply with LOCAL_OK"` and
confirm that the response comes from the loaded model.

## Runtime behavior and limits

- `zcoder -p`, `--file`, `--interactive`, and `--route` use the local model
  client by default.
- The local client accepts only loopback HTTP URLs and refuses HTTP redirects.
- A running llama.cpp server and a readable GGUF file are required. Missing
  local inference dependencies return an error; they do not produce a
  synthetic coding answer.
- Some specialized legacy CLI features are still being migrated. Their
  availability is documented in the main README and release notes; do not
  assume every optional feature uses this local path yet.
- Local inference still consumes CPU/GPU, memory, electricity, and disk space.

## Local persistence

- SQLite is the default for a single-user installation.
- PostgreSQL-backed commands use the shared Docker container `zPostgreSQL`
  and the isolated `zcoder_db` database.
- Local artifacts and runtime state are stored under the configured ZCoder
  data directory.
