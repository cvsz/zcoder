# Local GGUF mode for ZCoder prompt CLI

The normal `zcoder -p`, `zcoder --agent ... -p`, multi-agent router, and web
chat paths use a **loopback-only** llama.cpp chat completion server by default.
Anthropic egress is disabled across the shared URL transports and every
in-repository Anthropic SDK client factory. Legacy administrative, compliance,
managed-agent, and model-specific commands remain present for compatibility,
but fail closed before opening a network connection.

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

The model server listens on `127.0.0.1:8080` only. No API key is required for
local generation. Requests fail closed if the local server is missing; they
must **never** fall back to a paid external provider. Legacy provider routing
rejects `anthropic` as a selectable provider, and API requests to any
`*.anthropic.com` host are blocked by the shared transport boundary.
The public model identifiers are `zcoder-qwen2.5-coder-7b` and
`zcoder-qwen2.5-coder-1.5b`; the launcher configures the matching llama.cpp
server alias.

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

**Limit:** Anthropic-specific modules and model metadata have not been deleted.
Their outbound requests are blocked, so those features are unavailable until
they are replaced with local or other explicitly supported providers. The
Anthropic SDK remains an installed dependency for compatibility and test
fixtures; its production client factory uses a transport that refuses network
requests. This is runtime egress prevention, not source-code eradication.
