#!/usr/bin/env bash
set -euo pipefail

# Start an approved local llama.cpp server; never downloads or contacts a cloud provider.
MODEL_DIR="${ZCODER_GGUF_DIR:-/home/cvsz/zgpu}"
SIZE="${1:-7b}"
case "$SIZE" in
  7b) MODEL="$MODEL_DIR/qwen-7b-q4km.gguf"; ALIAS="zcoder-qwen2.5-coder-7b" ;;
  1.5b) MODEL="$MODEL_DIR/qwen-1.5b-q4km.gguf"; ALIAS="zcoder-qwen2.5-coder-1.5b" ;;
  *) echo "Usage: $0 [7b|1.5b]" >&2; exit 2 ;;
esac

if [[ ! -f "$MODEL" ]]; then
  echo "Missing local GGUF: $MODEL" >&2
  exit 1
fi
if ! command -v llama-server >/dev/null 2>&1; then
  echo "llama-server is not installed or not on PATH" >&2
  exit 1
fi
export ZCODER_PROVIDER=llama_cpp
export ZCODER_BASE_URL=http://127.0.0.1:8080
exec llama-server --model "$MODEL" --alias "$ALIAS" --host 127.0.0.1 --port 8080 --ctx-size 4096
