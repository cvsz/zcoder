# Quickstart

## Run from source with a local GGUF model

Start llama.cpp in a separate terminal:

```bash
llama-server \
  --model /home/cvsz/zcoder/models/qwen-7b-q4km.gguf \
  --host 127.0.0.1 \
  --port 8080 \
  --ctx-size 4096
```

Then install and run ZCoder:

```bash
make setup
export ZCODER_BASE_URL=http://127.0.0.1:8080/v1
export ZCODER_MODEL=qwen-7b-q4km
zcoder -p "Write a function to reverse a string"
```

For lower memory use, load `/home/cvsz/zcoder/models/qwen-1.5b-q4km.gguf` instead.
See [Local inference configuration](docs/guides/LOCAL-INFERENCE.md) for
details and endpoint checks.

## Run with Docker Compose (local GGUF, no Anthropic API key)

Place the model files in the repository's `models/` directory. The expected
default path is `models/qwen-7b-q4km.gguf`; Docker Compose mounts this
directory read-only into the inference container. Model weights are excluded
from Git and the Docker build context.

```bash
cp -n .env.example .env
docker compose config
docker compose run --build --rm zcoder -p "Reply with exactly LOCAL_OK"
```

If `.env` already exists, keep it and update only the required model settings.

The first run downloads the llama.cpp server image and builds the ZCoder image.
The server loads the GGUF before the command runs; the first model load can take
a while. The inference port is not published to the host or LAN. ZCoder shares
the inference service's network namespace and uses its loopback endpoint.

To use the smaller model, edit `.env`:

```dotenv
ZCODER_GGUF_FILE=qwen-1.5b-q4km.gguf
ZCODER_MODEL=qwen-1.5b-q4km
```

Then run the same `docker compose run` command. Ensure the selected GGUF
exists in the configured `ZCODER_MODELS_DIR` (default: `./models`).

Stop the inference service and remove the Compose network when finished:

```bash
docker compose down
```

## Shared PostgreSQL (zPostgreSQL) for Integration Tests

```bash
# Start shared PostgreSQL container
make postgres-setup

# Run integration tests
python scripts/local_postgres.py run -- python -m pytest tests/integration -q

# Run E2E tests
python scripts/local_postgres.py run -- python -m pytest tests/e2e -q

# Check status
make postgres-status
```

The Makefile equivalents are `make docker-build`,
`make docker-run ARGS='-p "Reply with exactly LOCAL_OK"'`,
`make docker-logs`, and `make docker-down`.

## Choose the installation directory

The destination is an exact virtual-environment path, not a parent directory.
Choose it before installation; Python virtual environments are not generally
relocatable after creation. Paths may contain spaces. Explicit relative paths
are resolved against the directory from which you invoke the command.

```bash
./setup.sh --install-dir "$HOME/Apps/zcoder"
"$HOME/Apps/zcoder/bin/zcoder" --version
```

On Windows (Command Prompt):

```bat
setup.bat --install-dir "D:\Apps\ZCoder"
"D:\Apps\ZCoder\Scripts\zcoder.exe" --version
```

With no `--install-dir`, the setup script creates the repository `venv` and
installs an editable package. The `ZCODER_VENV` environment variable is also
supported.

## Build a standalone executable

Python is required to build the executable, but not to run it:

```bash
./build.sh --dist-dir "$HOME/Downloads/zcoder-release"
"$HOME/Downloads/zcoder-release/zcoder" --version
```

On Windows:

```bat
build.bat --dist-dir "D:\Releases\ZCoder"
"D:\Releases\ZCoder\zcoder.exe" --version
```

Builds produce platform-specific executables and do not bundle model weights.
Create and validate separate artifacts on Linux, macOS, and Windows.
Platform signing, notarization, and release attestations are separate release
requirements.

## Basic commands

```bash
# Generate from a prompt
zcoder -p "Write a Python function to reverse a string"

# Analyze a source file
zcoder -f mycode.py -p "Explain this and suggest improvements"

# Start the terminal interface
zcoder --tui

# Run local liveness checks
zcoder --health-check

# Inspect available commands
zcoder --help
```

The prompt, file, interactive, and route flows use the configured local model
server. Some optional legacy operations are still being migrated; their use
does not imply that every ZCoder feature is local-only.
