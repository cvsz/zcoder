# Quickstart

## Run from source

```bash
./setup.sh              # macOS/Linux — creates venv, installs deps, makes .env
# or setup.bat on Windows

# edit .env and set ANTHROPIC_API_KEY

source venv/bin/activate
python main.py -p "Write a function to reverse a string"
```

## Build a standalone executable

No local Python needed to *run* the result — only to build it:

```bash
./build.sh               # macOS/Linux — produces dist/ai-coder
# or build.bat on Windows — produces dist\ai-coder.exe

export ANTHROPIC_API_KEY=sk-ant-...
./dist/ai-coder -p "Create a Flask REST API"
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

# Native memory tool (persists across runs, in ~/.ai-coder/memory)
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
