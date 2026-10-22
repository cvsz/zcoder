# Local GGUF mode for ZCoder prompt CLI

The normal `zcoder -p`, `zcoder --agent ... -p`, multi-agent router, and web
chat paths use a **loopback-only** llama.cpp chat completion server by default.
Inference transports are restricted to local model endpoints. Legacy
administrative, compliance, managed-agent, and model-specific commands remain
present for compatibility, but are unavailable in this local-only build.

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
must **never** fall back to an external provider. Legacy cloud providers are
not selectable from the inference router.
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
that relied on the old implicit PROVIDER_CREDENTIAL_OR_CONFIG mock. Those tests must explicitly
request their intended legacy provider or be migrated. Do not merge until
the full suite and independent review pass.

**Limit:** Legacy provider modules and model metadata have not been deleted.
Those features are unavailable until replaced with local implementations. The
SDK dependency remains for compatibility, while its application client factory
uses a transport that refuses network requests. This is runtime enforcement,
not source-code eradication.
