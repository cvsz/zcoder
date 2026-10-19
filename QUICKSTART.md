# Quickstart

## Run from source

```bash
./setup.sh              # macOS/Linux — creates venv, installs deps, makes .env
# or setup.bat on Windows

# edit .env and set ANTHROPIC_API_KEY

source venv/bin/activate
python main.py -p "Write a function to reverse a string"
```

### Choose the installation directory

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

`--install-dir` installs a regular package rather than an editable checkout,
so the CLI does not depend on keeping the cloned source directory. With no
option, the existing `venv` + editable-install behavior is preserved; the
existing `ZCODER_VENV` environment variable is also supported.

Credentials must be provided through environment variables or an explicitly
configured dotenv workflow when running outside the source checkout. The
setup script never copies credentials into the selected destination.

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

To choose the output directory and avoid overwriting an existing executable:

```bash
./build.sh --dist-dir "$HOME/Downloads/zcoder-release"
"$HOME/Downloads/zcoder-release/zcoder" --version
./build.sh --dist-dir "$HOME/Downloads/zcoder-release" --force  # intentional rebuild
```

```bat
build.bat --dist-dir "D:\Releases\ZCoder"
"D:\Releases\ZCoder\zcoder.exe" --version
```

`--work-dir` and `--build-venv` select intermediate build paths. Environment
overrides `ZCODER_DIST_DIR`, `ZCODER_WORK_DIR` and `ZCODER_BUILD_VENV` remain
available. Builds produce one platform-specific executable; create separate
artifacts on Linux, macOS, and Windows. A standalone build bundles Python,
not an AI model, API credentials, or operating-system libraries like glibc.
macOS notarization, Windows code signing and release attestations are separate
release requirements.

## Free-tier and local inference endpoints

The `--provider` flag applies to the **multi-agent router** (`--route`), not
the regular `-p` generation command or every other CLI feature.

```bash
export GROQ_API_KEY="your-groq-key"
zcoder --route "Review this function" --provider groq --model "openai/gpt-oss-20b"

export OPENROUTER_API_KEY="your-openrouter-key"
zcoder --route "Explain this diff" --provider openrouter --model "openrouter/free"

zcoder --route "Review this function" --provider openai_compatible \
  --base-url http://localhost:1234/v1 --model "my-loaded-model"
```

See [Free provider endpoint catalog](docs/guides/FREE-PROVIDER-ENDPOINTS.md)
for exact URLs, required keys, pricing caveats, and local alternatives.

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
