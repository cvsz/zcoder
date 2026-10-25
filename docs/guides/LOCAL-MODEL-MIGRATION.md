# Local Model Migration Status

## Default prompt and routing

The normal prompt path and default router use the local llama.cpp chat
endpoint at `127.0.0.1:8080`. The request model label defaults to
`zqwen2.5-coder-7b-instruct-q4_k_m` and can be overridden with
`ZCODER_MODEL`.

The local client requires loopback HTTP and rejects redirects. The model
server must already be running with a readable GGUF model loaded.

## Migrated call paths

- One-shot prompt and file generation.
- Interactive command-line chat.
- Default multi-agent routing.
- Git commit message, pull request text, changelog, review, and blame
  generation.
- GitHub review, issue triage, commit summary, and pull request description
  generation. GitHub REST data access still uses its separate GitHub token.
- Prompt optimization, prompt scoring, and A/B evaluation.
- Retrieval-augmented answer generation.
- Evaluation case generation and local judging.

## Remaining work

Some optional capability and administration modules still contain direct
remote-client implementations. They must be migrated to local adapters or
disabled before a complete local-only release can be claimed. The active
inventory is available with:

```bash
rg -l 'api\\.anthropic\\.com|anthropic\\.Anthropic' src/zcoder --glob '*.py'
```

Each remaining feature needs behavior-specific acceptance tests; replacing
endpoint strings alone is insufficient for streaming, tool use, remote file
storage, administration, or compliance operations.

## Acceptance checks

```bash
python -m pytest tests/unit
ruff check .
black --check .
zcoder --health-check
zcoder -p "Reply with exactly LOCAL_OK"
```

Real model acceptance requires running these commands against each supported
GGUF file on the target operating system and hardware.
