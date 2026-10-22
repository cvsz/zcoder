# Local GGUF mode for ZCoder prompt CLI

This change makes the normal `zcoder -p` and `zcoder --agent ... -p` path use
a **loopback-only** llama.cpp chat completion server by default. The normal
`Coder` path refuses explicit Anthropic calls. Other legacy
Anthropic-specific CLI features are not yet migrated or disabled and require
a separate audit; do **not** interpret this patch as complete Anthropic removal.

## Model files on the user's Ubuntu/WSL instance

- `/home/cvsz/zgpu/qwen-7b-q4km.gguf`
- `/home/cvsz/zgpu/qwen-1.5b-q4km.gguf`

The Windows `\\wsl.localhost\...` path is **not** an appropriate Linux CLI
path. Do not copy GGUF model files into the repository.

## Prerequisites

Install/build `llama.cpp` separately so `llama-server` is on PATH.
This repository does not download executables or model weights.

In terminal A:

```bash
cd ~/zcoder
bash scripts/start_local_gguf.sh 7b
# For a lower-memory alternative, stop the first server and run:
# bash scripts/start_local_gguf.sh 1.5b
```

In terminal B:

```bash
cd ~/zcoder
export ZCODER_PROVIDER=llama_cpp
export ZCODER_BASE_URL=http://127.0.0.1:8080
zcoder --agent security_auditor -p "Audit cvsz/zgpu source for vulnerabilities; cite files and recommend tests."
```

The model server listens on `127.0.0.1:8080` only. No Anthropic key is
required for this prompt path. Requests fail closed if the local server is
missing; they must **never** fall back to a paid external provider.

The first test should be a short text completion. A prompt containing just
a GitHub repository name does not automatically give ZCoder access to its
source code; inspect or supply files explicitly.

### Developer checks

```bash
ruff check src/zcoder/main.py src/zcoder/services/coder.py tests/unit/test_local_gguf_default.py
ruff format --check src/zcoder/main.py src/zcoder/services/coder.py tests/unit/test_local_gguf_default.py
python -m pytest tests/unit/test_local_gguf_default.py -q
```

Changing the default backend is a compatibility-breaking change for tests
that relied on the old implicit Anthropic mock. Those tests must explicitly
request their intended legacy provider or be migrated. Do not merge until
the full suite and independent review pass.

**Limit:** This is a preliminary cutover for the normal prompt CLI path.
A full repository-wide eradication of Anthropic integrations, SDK imports,
admin/compliance endpoints, and specialized model features is a separate,
potentially breaking migration requiring an audited compatibility matrix.
