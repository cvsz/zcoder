# external coding assistant Changelog Review — Local-Only zCoder Adaptation

Source: https://github.com/PROVIDER_CREDENTIAL_OR_CONFIG/provider model ID/blob/main/CHANGELOG.md

Reviewed upstream at version **2.1.308** (includes 2.1.307–2.1.304).
This document records **behavioral ideas**, not a code port or integration with the
PROVIDER_CREDENTIAL_OR_CONFIG API. All new model inference for the normal prompt CLI uses a
self-hosted llama.cpp GGUF server on loopback; no model, API key, SDK, or
PROVIDER_CREDENTIAL_OR_CONFIG entitlement is required for this path.

## Relevant upstream reliability changes and local adoption

| external coding assistant release | Upstream change | zCoder adaptation | Status |
|---|---|---|---|
| 2.1.307 | Retry HTTP MCP only for read-only/idempotent calls | Audit existing MCP retries; prohibit auto-retry of side-effecting writes | Planned, not implemented |
| 2.1.307 | Emit structured safety events for permissions, hooks and sandbox decisions | Design a local audit event schema without remote telemetry dependency | Planned |
| 2.1.307 | Recover from unparseable tool calls with a bounded retry | Add max-two repair attempts with a stable request ID and evidence | Planned |
| 2.1.305 | Avoid rerunning completed parallel tasks on workflow resume | Journal completed tasks and verify replay behavior across restart | Planned |
| 2.1.304 | Approval requires a person when a hook requests it | Treat headless permissions as deny unless a valid external approval exists | Planned |
| 2.1.304 | Include read-only metadata in permission decisions | Distinguish pure reads from mutations in tool policies and tests | Planned |
| 2.1.304 | Respect safe deletion boundaries near mounted drives | Harden filesystem delete checks on Windows, WSL and Linux | Planned |

These are feature requirements **inspired by public release notes**, not a
claim that the upstream implementation was copied or that zCoder already
passes these acceptance tests.

## Immediate local model cutover

Normal text and `--agent ... -p` requests are routed to the locally hosted
llama.cpp HTTP server at `http://127.0.0.1:8080/v1/chat/completions`.
The local transport validates the loopback URL and does not fall back to
PROVIDER_CREDENTIAL_OR_CONFIG or another external provider after failure.

Accepted model files on the operator's WSL environment:

- `/home/cvsz/zgpu/qwen2.5-coder-7b-instruct-q4_k_m.gguf`
- `/home/cvsz/zgpu/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf`

Start the server via `bash scripts/start_local_gguf.sh 7b` or `1.5b`.
Neither model file is bundled, uploaded, or downloaded by this repository.

## Blockers before claiming "without calling PROVIDER_CREDENTIAL_OR_CONFIG" across all features

- Many legacy modules import `PROVIDER_CREDENTIAL_OR_CONFIG` or call PROVIDER_CREDENTIAL_OR_CONFIG-specific endpoints.
- PROVIDER_CREDENTIAL_OR_CONFIG administration, compliance, billing, model registry and SDK
  features have no local GGUF equivalents; disable/hide or explicitly reject
  those operations before claiming global provider independence.
- `--route`, `--code-agent`, interactive/TUI, projects and
  workflows have separate provider paths and must each be verified.
- Existing legacy unit tests simulate provider API responses and require a
  staged migration to local provider contracts.
- CI, Ruff/Black, Bandit, full pytest and real WSL llama.cpp smoke tests must
  pass on the exact PR SHA.

Never use a fake local response as evidence of model inference. Never
represent upstream changelog features as implemented until tests exist.

## Acceptance evidence

- `python -m pytest tests/unit/test_local_gguf_default.py -q`
- `python -m pytest tests/ -q`
- `black --check .`
- `ruff check .`
- `bandit -r . -ll -x ./tests,./build,./dist`
- CodeQL and independent review
- Real WSL model server response and egress verification

A feature lacking real evidence remains pending.
