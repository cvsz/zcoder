# Quickstart

## Run from source

```bash
./setup.sh              # macOS/Linux — creates venv, installs deps, makes .env
# or setup.bat on Windows

source venv/bin/activate
python main.py -p "Write a function to reverse a string"
```

## Run with a local GGUF model

Start llama.cpp with a GGUF model in one terminal:

```bash
llama-server -m ~/zgpu/qwen-7b-q4km.gguf --host 127.0.0.1 --port 8080 --ctx-size 4096
```

Then run ZCoder in another terminal:

```bash
export ZCODER_PROVIDER=llama_cpp
export ZCODER_BASE_URL=http://127.0.0.1:8080
python main.py -p "Write a function to reverse a string"
```

Legacy cloud-specific commands are unavailable in local-only mode; prompt,
agent, router, and web chat paths use local llama.cpp inference.

## Build a standalone executable

No local Python needed to *run* the result — only to build it:

```bash
./build.sh               # macOS/Linux — produces dist/zcoder
# or build.bat on Windows — produces dist\zcoder.exe

./dist/zcoder -p "Create a Flask REST API"
```

## A few places to start

```bash
# Basic generation
python main.py -p "Write a Python function to reverse a string"

# Analyze a file
python main.py -f mycode.py -p "Explain this and suggest improvements"

# List every server tool, and the newer per-tool features (Tool Use
# Examples, Programmatic Tool Calling, task budgets, compaction)
python main.py --list-server-tools

# Agentic tool loop
python main.py --tool-agent -p "Find and fix the bug in app.py"

# Native memory tool (persists across runs, in ~/.zcoder/memory)
python main.py --memory-agent "Remember that this project uses pytest"

# Advisor tool — a stronger model consulted mid-generation
python main.py --advisor "Refactor auth.py to use JWT, then write tests"

# Real hosted provider Managed Agents (cloud sandbox, not local)
python main.py --agent-managed-run "Set up a FastAPI project with tests"

# Embeddings (needs VOYAGE_API_KEY — see .env.example)
python main.py --embed-similarity "cat" "kitten"

# Everything else
python main.py --help
```

PROVIDER_CREDENTIAL_OR_CONFIG Admin and Compliance API commands are unavailable while PROVIDER_CREDENTIAL_OR_CONFIG
egress is disabled. Their local replacements are not implemented yet.

See `README.md` for the full feature list and `docs/` for the detailed,
dated history of what was added, changed, or fixed in each release.
