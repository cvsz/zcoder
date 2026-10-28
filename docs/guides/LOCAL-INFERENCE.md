# Local Inference Configuration

ZCoder's default prompt client sends chat-completion requests to a local
llama.cpp server. The client requires a loopback HTTP endpoint and rejects
redirects.

## Run llama.cpp on the host

```bash
llama-server \
  --model /home/cvsz/zcoder/models/qwen-7b-q4km.gguf \
  --host 127.0.0.1 \
  --port 8080 \
  --ctx-size 4096
```

For lower memory use, load
`/home/cvsz/zcoder/models/qwen-1.5b-q4km.gguf` instead. The GGUF must exist
and be readable by the server process.

## Run with Docker Compose

Docker Compose starts a dedicated `llama-server` service and runs ZCoder
against it. Copy `.env.example` to `.env`, then confirm the configured
model file exists in the configured models directory:

```bash
cp -n .env.example .env
ls -lh models/qwen-7b-q4km.gguf
docker compose config
docker compose run --build --rm zcoder -p "Reply with exactly LOCAL_OK"
```

If `.env` already exists, keep it and update only the required model settings.

The default settings are:

- `ZCODER_MODELS_DIR=./models`
- `ZCODER_GGUF_FILE=qwen-7b-q4km.gguf`
- `ZCODER_MODEL=qwen-7b-q4km`
- `ZCODER_CTX_SIZE=4096`

To use the smaller model, set `ZCODER_GGUF_FILE=qwen-1.5b-q4km.gguf` and
`ZCODER_MODEL=qwen-1.5b-q4km` in `.env`. The selected GGUF is mounted
read-only at `/models`; weights are not copied into the ZCoder image or
committed to Git. The model service listens on loopback and publishes no host
port. ZCoder shares that service's network namespace, preserving the client's
loopback-only URL validation without allowing arbitrary Compose hostnames.

The first run downloads the llama.cpp image and builds the ZCoder image. Model
loading can take time; Compose waits for the model server health check before
running ZCoder. Use `docker compose logs -f llama-server` to inspect loading
and `docker compose down` to stop the server and remove the Compose network.

## Configure ZCoder when running from source

```bash
export ZCODER_BASE_URL=http://127.0.0.1:8080/v1
export ZCODER_MODEL=qwen-7b-q4km
zcoder -p "Review the supplied source code"
```

The model identifier is a local request label. The weights come from the GGUF
loaded by the server. `ZCODER_BASE_URL` may omit `/v1`; the CLI adds it for
the chat-completions path.

## Verification

```bash
curl --fail http://127.0.0.1:8080/health
zcoder -p "Reply with exactly LOCAL_OK"
```

For Docker, run the CLI smoke test above; the inference endpoint is intentionally
not exposed on the host, so a host-side `curl` to port 8080 is not expected to
work.

Do not bind the model server to a public interface unless a separately
reviewed authentication and network policy protects it. Local inference uses
the machine's compute, memory, and storage resources.

## Routing scope

The default `-p`, `-f`, interactive, and route flows use the local model
gateway. Some specialized legacy operations are still being migrated; they
must be converted or disabled before describing every ZCoder feature as
local-only.
