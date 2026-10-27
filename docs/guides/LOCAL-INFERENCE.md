# Local Inference Configuration

ZCoder's default prompt client sends chat-completion requests to a local
llama.cpp server. The client requires a loopback HTTP endpoint and rejects
redirects.

## Start llama.cpp

```bash
llama-server \
  --model /home/cvsz/zgpu/qwen-7b-q4km.gguf \
  --host 127.0.0.1 \
  --port 8080 \
  --ctx-size 4096
```

For lower memory use, load `/home/cvsz/zgpu/qwen-1.5b-q4km.gguf` instead.
The GGUF must exist and be readable by the server process.

## Configure ZCoder

```bash
export ZCODER_BASE_URL=http://127.0.0.1:8080/v1
export ZCODER_MODEL=zqwen2.5-coder-7b-instruct-q4_k_m
zcoder -p "Review the supplied source code"
```

The model identifier is a local request label. The weights come from the GGUF
loaded by the server. `ZCODER_BASE_URL` may omit `/v1`; the CLI adds it for the
chat-completions path.

## Verification

```bash
curl --fail http://127.0.0.1:8080/health
zcoder -p "Reply with exactly LOCAL_OK"
```

Do not bind the model server to a public interface unless a separately
reviewed authentication and network policy protects it. Local inference uses
the machine's compute, memory, and storage resources.

## Routing scope

The default `-p`, `-f`, interactive, and route flows use the local model
gateway. Some specialized legacy operations are still being migrated; they
must be converted or disabled before describing every ZCoder feature as
local-only.
