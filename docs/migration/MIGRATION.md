# Migration Guide

This guide covers migrating to and from ZCoder, including upgrading between
versions, migrating from other coding agents, and migrating data.

## 1. Upgrading ZCoder

### From ZCoder 1.x to 2.x

ZCoder 2.x introduces several breaking changes:

#### Default model change
The default model changed from `qwen-7b-q4km` to `zcoder-flash`. Update your
environment variables:

```bash
# Old
export ZCODER_MODEL=qwen-7b-q4km
export ZCODER_GGUF_FILE=qwen-7b-q4km.gguf

# New
export ZCODER_MODEL=zcoder-flash
export ZCODER_GGUF_FILE=zcoder-pro.gguf
```

#### Models directory change
The default models directory changed from `./models` to `/zdata/models`:

```bash
# Old
export ZCODER_MODELS_DIR=./models

# New
export ZCODER_MODELS_DIR=/zdata/models
```

#### PostgreSQL host name fix
A typo in the PostgreSQL host name was fixed:

```bash
# Old (typo)
export ZCODER_POSTGRES_HOST=zpostgressql

# New (correct)
export ZCODER_POSTGRES_HOST=zpostgressql
```

### Checking compatibility

```bash
zcoder --health-check
zcoder -p "Reply with exactly LOCAL_OK"
```

## 2. Migrating from other coding agents

### From Claude Code

ZCoder is designed to be a local-first alternative to Claude Code. Key
differences:

| Feature | Claude Code | ZCoder |
|---------|-------------|--------|
| Model provider | Anthropic API | Local Ollama (default) |
| API key required | Yes | No (local inference) |
| Data privacy | Sends code to Anthropic | Stays local |
| Session storage | Cloud | Local files/PostgreSQL |
| MCP support | Yes | Yes |

#### Migration steps

1. Install ZCoder:
   ```bash
   pip install -e .
   ```

2. Start local Ollama:
   ```bash
   ollama serve
   ```

3. Configure ZCoder:
   ```bash
   cp .env.example .env
   # Edit .env with your model settings
   ```

4. Use ZCoder:
   ```bash
   zcoder -p "Your coding task"
   ```

### From other agents

ZCoder accepts prompts in natural language. Any prompt that works with another
coding agent should work with ZCoder:

```bash
zcoder -p "Your prompt here"
```

Sessions can be exported from other agents and imported into ZCoder:

```bash
# Export from another agent (format-dependent)
# Import into ZCoder
zcoder --import-session path/to/session.json --new-id my-session
```

Or programmatically:

```python
from zcoder.agent.codeagent.sessions import SessionStore

store = SessionStore()
new_id = store.import_session("path/to/session.json", new_id="my-session")
```

## 3. Data migration

### Session data

ZCoder stores sessions as JSON files in `~/.zcoder/sessions/` by default.
Each session file contains:

```json
{
  "id": "20260115-120000-abc123",
  "cwd": "/path/to/project",
  "title": "Session title",
  "updated": 1736942400.0,
  "usage": {"prompt": 100, "completion": 50},
  "messages": [
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hi there"}
  ]
}
```

To migrate session data from another system, convert it to this format and
use `SessionStore.import_session()`:

```python
from zcoder.agent.codeagent.sessions import SessionStore

store = SessionStore()
new_id = store.import_session("path/to/foreign-session.json")
```

### Configuration migration

ZCoder reads configuration from:

1. Command-line arguments (highest precedence)
2. Environment variables (`ZCODER_*`)
3. `~/.zcoder-config.json`

To migrate configuration from another system, create a `~/.zcoder-config.json`:

```json
{
  "model": "zcoder-flash",
  "base_url": "http://127.0.0.1:11434/v1",
  "max_tokens": 8192,
  "context_window": 32768,
  "sandbox_enabled": true,
  "allow_network": true
}
```

## 4. Docker migration

### From standalone Docker to Docker Compose

If you were running ZCoder as a standalone container:

```bash
# Old
docker run --rm zcoder:latest -p "Your prompt"

# New
docker compose up -d
docker compose run --rm zcoder -p "Your prompt"
```

### Updating docker-compose.yml

If you have an existing `docker-compose.yml`, update it to match the current
format:

```yaml
services:
  zpostgressql:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: zcoder
      POSTGRES_PASSWORD_FILE: /run/secrets/zcoder_postgres_password
      POSTGRES_DB: zcoder_db
    ...
  zredis:
    image: redis:7-alpine
    ...
  ollama:
    image: ollama/ollama:latest
    ...
  zcoder:
    image: zcoder:latest
    environment:
      ZCODER_BASE_URL: http://127.0.0.1:11434/v1
      ZCODER_MODEL: ${ZCODER_MODEL:-zcoder-pro}
      ZCODER_POSTGRES_HOST: zpostgressql
      ...
    depends_on:
      - ollama
      - zpostgressql
      - zredis
```

## 5. Breaking changes by version

### v1.60.0
- Default model changed to `zcoder-flash`
- Default models directory changed to `/zdata/models`
- PostgreSQL host configured as `zpostgressql`
- Added Delete tool
- Added DatabaseQuery and APICall tools
- Added session projection features (token usage, cost tracking, analytics)
- Added Anthropic, Gemini, and Ollama LLM provider adapters

### Earlier versions
Check `docs/FINAL-REPORT.md` and `docs/audit/FINAL-REPORT.md` for historical
release notes.

## 6. Rollback

If you encounter issues after upgrading:

```bash
# Revert to the previous version
git checkout <previous-version>
pip install -e .

# Or reinstall the previous Docker image
docker compose pull zcoder:previous-tag
docker compose up -d
```

## 7. Support

If you encounter issues during migration:

1. Run `zcoder --health-check`
2. Check `docs/guides/TROUBLESHOOTING.md`
3. Search existing issues: https://github.com/cvsz/zcoder/issues
4. Create a new issue with your migration details