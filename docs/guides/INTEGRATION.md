# Integration Guide

This guide covers integrating ZCoder into other systems, applications, and
workflows. It describes the public API, CLI surface, configuration options, and
embedding patterns.

## Overview

ZCoder is a local-first coding agent CLI with a Python library surface, an
OpenAI-compatible local inference endpoint, an MCP server, and a TUI/web
frontend. It can be used as:

- A CLI tool (`zcoder` command)
- A Python library (`import zcoder`)
- An MCP server (for IDE/agent integrations)
- A Docker container (for self-contained deployments)

## 1. CLI Integration

### Basic usage

```bash
# One-shot prompt
zcoder -p "Refactor this function to use async/await"

# Analyze a file
zcoder -f src/main.py -p "Find performance issues"

# Interactive TUI
zcoder --tui

# Health check
zcoder --health-check
```

### Common options

| Option | Description |
|--------|-------------|
| `-p, --prompt` | Send a prompt and exit |
| `-f, --file` | Attach a file to the prompt |
| `--tui` | Start the text user interface |
| `--model` | Override the default model |
| `--base-url` | Override the LLM server URL |
| `--health-check` | Run local liveness checks |
| `--help` | Show all options |

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ZCODER_BASE_URL` | `http://127.0.0.1:8080/v1` | Local inference server URL |
| `ZCODER_MODEL` | `zcoder-flash` | Default model name |
| `ZCODER_CTX_SIZE` | `4096` | Context window size |
| `ZCODER_LOCAL_MODE` | unset | Block remote API calls when set |
| `ZCODER_MODELS_DIR` | `/zdata/models` | GGUF models directory |
| `ZCODER_POSTGRES_HOST` | `zpostgresql` | PostgreSQL host |
| `ZCODER_POSTGRES_PORT` | `5432` | PostgreSQL port |
| `ZCODER_POSTGRES_DB` | `zcoder_db` | PostgreSQL database |
| `ZCODER_REDIS_HOST` | `zredis` | Redis host |
| `ZCODER_REDIS_PORT` | `6379` | Redis port |

## 2. Python Library Integration

ZCoder can be used as a Python library:

```python
from zcoder.main import main

# Run zcoder programmatically
import sys
sys.argv = ["zcoder", "-p", "Write a hello world function"]
main()
```

### Using the agent loop directly

```python
from zcoder.agent.codeagent.loop import CodeAgent
from zcoder.agent.codeagent.llm import LocalLLM
from zcoder.agent.codeagent.workspace import Workspace
from zcoder.agent.codeagent.permissions import PermissionPolicy

workspace = Workspace(Path("/path/to/project"))
llm = LocalLLM(model="zcoder-pro")
policy = PermissionPolicy(workspace=workspace)
agent = CodeAgent(llm=llm, workspace=workspace, policy=policy)

import asyncio

async def run():
    async for event in agent.run("Create a README.md file"):
        from zcoder.agent.codeagent.events import TextDelta, TurnDone
        if isinstance(event, TextDelta):
            print(event.text, end="", flush=True)
        elif isinstance(event, TurnDone):
            break

asyncio.run(run())
```

### Using session management

```python
from zcoder.agent.codeagent.sessions import SessionStore, new_session_id

store = SessionStore(directory=Path("/path/to/sessions"))
session_id = new_session_id()
store.save(session_id, "/path/to/project", messages, usage={"prompt": 100, "completion": 50})

# Later: resume
doc = store.load(session_id)
```

### Session projection and analytics

```python
from zcoder.agent.codeagent.sessions import SessionProjection, SessionEvent

projection = SessionProjection()
for event in session_events:
    projection.fold(event)

summary = projection.get_session_summary()
# Returns: turn_count, message_count, tool_call_count, total_tokens, total_cost, etc.

tokens = projection.get_token_usage()
# Returns: total_input_tokens, total_output_tokens, by_key breakdown

tools = projection.get_tool_statistics()
# Returns: per-tool call counts, success rates, token usage

cost = projection.get_cost_breakdown()
# Returns: input_cost, output_cost, total_cost

analytics = projection.get_session_analytics()
# Returns: duration, messages_per_turn, cost_per_turn, etc.
```

## 3. MCP Server Integration

ZCoder includes an MCP (Model Context Protocol) server that exposes its tools
to MCP-compatible clients (IDE extensions, other agents, etc.).

### Starting the MCP server

```bash
zcoder --mcp-server
# or
python -m zcoder.agent.codeagent.mcp_server
```

### MCP server configuration

```json
{
  "mcpServers": {
    "zcoder": {
      "command": "zcoder",
      "args": ["--mcp-server"],
      "env": {
        "ZCODER_BASE_URL": "http://127.0.0.1:8080/v1",
        "ZCODER_MODEL": "zcoder-pro"
      }
    }
  }
}
```

### Available MCP tools

The MCP server exposes ZCoder's built-in tools: Read, Write, Edit, Grep, Glob,
LS, Bash, TodoWrite, and more.

## 4. Docker Integration

### Using Docker Compose

```yaml
services:
  zcoder:
    image: zcoder:latest
    environment:
      ZCODER_BASE_URL: http://llama-server:8080/v1
      ZCODER_MODEL: qwen-7b-q4km
      ZCODER_POSTGRES_HOST: zpostgresql
      ZCODER_REDIS_HOST: zredis
    depends_on:
      - llama-server
      - zpostgresql
      - zredis
```

### Building the image

```bash
docker compose build zcoder
docker compose up -d
```

## 5. Configuration

ZCoder reads configuration from:

1. Command-line arguments (highest precedence)
2. Environment variables (`ZCODER_*`)
3. `~/.zcoder-config.json` (lowest precedence)

Create a `.env` file for local development:

```bash
cp .env.example .env
# Edit .env with your settings
```

## 6. Authentication and Credentials

ZCoder uses local inference by default and does not require API keys. Credential
management is handled through the credential seam:

```python
from zcoder.credentials.credential_seam import CredentialRef, credentialRef

ref = credentialRef("MY_API_KEY")
# Resolve at runtime through the credential provider
```

See `docs/API_REFERENCE.md` for the complete credential management API.

## 7. Performance Tuning

- Use `zcoder-flash` for fast, low-cost operations
- Use `zcoder-pro` for complex reasoning tasks
- Enable PostgreSQL for durable session storage: `ZCODER_POSTGRES_HOST=zpostgresql`
- Enable Redis for caching: `ZCODER_REDIS_HOST=zredis`
- Adjust context window: `ZCODER_CTX_SIZE=32768`

See `docs/performance-optimization.md` for detailed performance guidance.

## 8. CI/CD Integration

### GitHub Actions example

```yaml
name: zcoder-review
on: [pull_request]
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run ZCoder review
        run: |
          zcoder -p "Review this pull request for bugs and improvements"
```

### Pre-commit hook example

```yaml
# .pre-commit-config.yaml
- repo: local
  hooks:
    - id: zcoder-review
      name: ZCoder code review
      entry: zcoder -p "Review this change for issues"
      language: system
      files: \.py$
```

## Next Steps

- Read `docs/API_REFERENCE.md` for the complete API reference
- Read `docs/guides/TROUBLESHOOTING.md` for common issues
- Read `docs/performance-optimization.md` for performance tuning
- Run `zcoder --health-check` to verify your installation