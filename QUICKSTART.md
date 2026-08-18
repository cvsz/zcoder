# Quickstart

## Run from source

```bash
./setup.sh              # macOS/Linux — creates venv, installs deps, makes .env
# or setup.bat on Windows

# edit .env and set ANTHROPIC_API_KEY

source venv/bin/activate
python main.py -p "Write a function to reverse a string"
```

## Run without an API key (offline / local mode)

Set `ZCODER_LOCAL_MODE=1` (or `true`/`yes`) to run the CLI with no
`ANTHROPIC_API_KEY` at all — generation, git helpers, live mode, and
prompt optimization switch to deterministic offline synthesis with no
network calls:

```bash
export ZCODER_LOCAL_MODE=1
python main.py -p "Write a function to reverse a string"
# -> [zCoder local offline response] ...
```

Outside local mode, a missing key is a hard error (`[ERROR] No API key
configured...`) — the CLI never silently pretends to generate. Local mode
does not require Ollama or any other model engine; it is a pure
synthesis fallback for trying the CLI, running the test suite, or
air-gapped smoke tests.

## Build a standalone executable

No local Python needed to *run* the result — only to build it:

```bash
./build.sh               # macOS/Linux — produces dist/zcoder
# or build.bat on Windows — produces dist\zcoder.exe

export ANTHROPIC_API_KEY=sk-ant-...
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

# Real hosted Claude Managed Agents (cloud sandbox, not local)
python main.py --agent-managed-run "Set up a FastAPI project with tests"

# Embeddings (needs VOYAGE_API_KEY — see .env.example)
python main.py --embed-similarity "cat" "kitten"

# Everything else
python main.py --help
```

If you have an Admin API key or Compliance Access Key (org-level,
different from a regular `ANTHROPIC_API_KEY`), `--usage-report`,
`--admin-list-keys`, and `--compliance-activities` are the entry points
into that surface — see `README.md`'s "New in v1.15.0" / "New in
v1.16.0" sections before using them, since a few of those flags
(`--compliance-*-delete`) are permanent, org-wide deletes.

See `README.md` for the full feature list and `docs/` for the detailed,
dated history of what was added, changed, or fixed in each release.
