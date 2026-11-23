# Local Inference Configuration

ZCoder's default prompt client sends chat-completion requests to a local
Ollama server (http://127.0.0.1:11434). The client requires a loopback HTTP endpoint and rejects
redirects.

## Run Ollama on the host

Models are stored in `/zdata/models/`. Ollama serves them on loopback:

```bash
ollama serve
```

Available models read from `/zdata/models/`:
- `zcoder-flash` (`zcoder-flash.gguf`)
- `zcoder-pro` (`zcoder-pro.gguf`)
- `zcoder-max` (`zcoder-max.gguf`)
- `zcoder-promax` (`zcoder-promax.gguf`)

## Run with Docker Compose

Docker Compose starts a dedicated `ollama` service and runs ZCoder
against it. Copy `.env.example` to `.env`, then confirm the configured
models exist in `/zdata/models/`:

```bash
cp -n .env.example .env
ls -lh /zdata/models/
docker compose config
docker compose run --build --rm zcoder -p "Reply with exactly LOCAL_OK"
docker compose logs -f ollama
```

If `.env` already exists, keep it and update only the required model settings.

The default settings are:

- `ZCODER_MODELS_DIR=/zdata/models`
- `ZCODER_MODEL=zcoder-pro`
- `ZCODER_BASE_URL=http://127.0.0.1:11434/v1`
- `OLLAMA_BASE_URL=http://127.0.0.1:11434`
- `ZCODER_PROVIDER=ollama`
- `ZCODER_CTX_SIZE=32768`

## Configure ZCoder when running from source

```bash
export ZCODER_BASE_URL=http://127.0.0.1:11434/v1
export OLLAMA_BASE_URL=http://127.0.0.1:11434
export ZCODER_MODEL=zcoder-pro
export ZCODER_PROVIDER=ollama
zcoder -p "Review the supplied source code"
```

The model identifier is a local request label. The weights come from the GGUF
loaded by the server. `ZCODER_BASE_URL` may omit `/v1`; the CLI adds it for
the chat-completions path.

## Verification

```bash
# ตรวจสอบ Ollama (port 11434)
curl --fail http://127.0.0.1:11434/api/version
# รัน ZCoder test prompt
zcoder -p "Reply with exactly LOCAL_OK"
```

For Docker, run the CLI smoke test above; the inference endpoint is intentionally
not exposed on the host, so a host-side `curl` to port 11434 from outside the container
is not expected to work unless port-mapped.

Do not bind the model server to a public interface unless a separately
reviewed authentication and network policy protects it. Local inference uses
the machine's compute, memory, and storage resources.

## Routing scope

The default `-p`, `-f`, interactive, and route flows use the local model
gateway. Some specialized legacy operations are still being migrated; they
must be converted or disabled before describing every ZCoder feature as
local-only.
