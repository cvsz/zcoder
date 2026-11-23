# ZCoder API Reference

This document describes the public API of the `zcoder` package (v1.60.0).

## Table of Contents

1. [Configuration](#configuration)
2. [Security Primitives](#security-primitives)
3. [Session Management](#session-management)
4. [LLM Client](#llm-client)
5. [Slash Commands](#slash-commands)
6. [Plugin System](#plugin-system)
7. [Credential Management](#credential-management)

---

## Configuration

### `zcoder.config.settings.Config`

Typed configuration for zcoder. Reads from `~/.zcoder-config.json` (or legacy
`~/.ai-coder-config.json`) with environment variable overrides (`ZCODER_*` prefix).

```python
from zcoder.config.settings import Config

config = Config()
config.get("model")              # -> "zcoder-flash" (default)
config.set("model", "custom")    # persists to config file
config.get("max_tokens")         # -> 8192 (default)
```

**Constructor:** `Config()` — loads config from file, applies env overrides.

**Methods:**

| Method | Description |
|--------|-------------|
| `get(key, default=None)` | Get a config value |
| `set(key, value)` | Set and persist a config value |
| `all()` | Return all config as a dict |

**Environment variables:** Any `ZCODER_*` env var is mapped to a config field (e.g.
`ZCODER_MODEL` → `model`, `ZCODER_MAX_TOKENS` → `max_tokens`). Boolean fields accept
`true/false`, `1/0`, `yes/no`, `on/off`.

### `zcoder.config.settings.ConfigFields`

TypedDict defining all configuration fields:

| Field | Type | Default |
|-------|------|---------|
| `provider` | `str` | `"openai_compatible"` |
| `model` | `str` | `"zcoder-flash"` |
| `base_url` | `str` | `"http://localhost:11434"` |
| `api_key` | `str` | `""` |
| `reasoning_effort` | `str` | `"medium"` |
| `max_tokens` | `int` | `8192` |
| `context_window` | `int` | `32768` |
| `max_output_chars` | `int` | `30000` |
| `max_read_bytes` | `int` | `2000000` |
| `max_line_chars` | `int` | `2000` |
| `timeout_ms` | `int` | `60000` |
| `max_steps` | `int` | `40` |
| `context_window_percentage` | `float` | `0.8` |
| `theme` | `str` | `"default"` |
| `show_timestamps` | `bool` | `False` |
| `show_usage` | `bool` | `True` |
| `sandbox_enabled` | `bool` | `True` |
| `allow_network` | `bool` | `True` |
| `allow_file_write` | `bool` | `True` |
| `allow_code_exec` | `bool` | `True` |
| `telemetry_enabled` | `bool` | `False` |
| `observability_endpoint` | `str` | `""` |

---

## Security Primitives

### `zcoder.core.security`

Security functions for branded IDs, credential references, path resolution,
child environments, and input validation.

#### Branded IDs

| Function | Description |
|----------|-------------|
| `brandString(value: str) → str` | Brand a string as a nominal type (compile-time only) |
| `brandNumber(value: float) → float` | Brand a number as a nominal type |
| `brandSessionId(value: str) → SessionId` | Brand a session ID |
| `brandSessionSeq(value: int) → SessionSeq` | Brand a session sequence number |
| `brandToolCallId(value: str) → ToolCallId` | Brand a tool call ID |
| `is_branded(value, brand) → bool` | Check if a value has a brand |

#### Path Resolution

| Function | Description |
|----------|-------------|
| `safe_resolve(path, base) → str` | Resolve `path` within `base`, preventing traversal. Raises `SecurityError` if path escapes base. |

#### Child Environment

| Function | Description |
|----------|-------------|
| `build_child_env(overrides=None) → dict[str, str]` | Build a clean child-process environment (no secret inheritance). |

#### Text / File Utilities

| Function | Description |
|----------|-------------|
| `read_text_prefix(path, max_chars=8000) → str` | Read first `max_chars` of a text file |
| `check_file_size(path_or_file, max_bytes) → None` | Raise `SecurityError` if file exceeds `max_bytes` |

#### Validation

| Function | Description |
|----------|-------------|
| `validate_name(name, field="name") → None` | Validate a safe identifier (letters, digits, `_`, `-`, `.`) |
| `validate_url(url, allowed_schemes=("http","https")) → None` | Validate a URL uses an allowed scheme |

---

## Session Management

### `zcoder.agent.codeagent.sessions`

Persistent, resumable conversations stored as one JSON file per session.

### `SessionStore`

```python
from zcoder.agent.codeagent.sessions import SessionStore

store = SessionStore(directory=Path("/path/to/sessions"))
store.save("20260115-120000-abc123", "/tmp/project", messages)
doc = store.load("20260115-120000-abc123")
```

**Constructor:** `SessionStore(directory: Path | None = None)`

**Methods:**

| Method | Description |
|--------|-------------|
| `save(session_id, cwd, messages, usage=None) → None` | Save a session (atomic write, 0600 permissions) |
| `load(session_id) → dict` | Load a session; raises `KeyError` if not found |
| `list_sessions(cwd=None) → list[SessionInfo]` | List sessions, sorted by updated time descending |
| `delete(session_id, confirm=True) → None` | Delete a session |
| `fork(session_id, *, label=None) → str` | Fork a session, returns new session ID |
| `rename(session_id, new_title) → None` | Rename a session |
| `search(query, cwd=None) → list[SessionInfo]` | Search sessions by title or content |

**Session ID format:** `YYYYMMDD-HHMMSS-XXXXXX` (hex suffix), validated against path traversal.

### `SessionEvent`

```python
from zcoder.agent.codeagent.sessions import SessionEvent

event = SessionEvent(
    kind="user/message",
    data={"content": "Hello"},
    event_id="evt-1",
    timestamp=1000.0,
)
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `kind` | `str` | Event type (turn/start, user/message, tool/call, etc.) |
| `data` | `dict[str, Any]` | Event payload |
| `source_event_seqs` | `list[int] \| None` | Source event sequences |
| `ignorable` | `bool` | Whether event is ignorable by older readers |
| `surface_op` | `str \| None` | Surface operation marker |
| `event_id` | `str` | Event identifier |
| `timestamp` | `float` | Event timestamp |

### `SessionProjection`

Fold committed events into projected state for efficient querying.

```python
projection = SessionProjection()
projection.fold(event)
state = projection.get_state()
summary = projection.get_session_summary()
```

**Methods:**

| Method | Description |
|--------|-------------|
| `fold(event) → None` | Fold one event into projected state |
| `fold_many(events) → None` | Fold multiple events in order |
| `get_state() → dict` | Return current projected state (copy) |
| `get_session_summary() → dict` | Return session summary |

### Event Logging Functions

| Function | Description |
|----------|-------------|
| `log_session_event(store, session_id, kind, data, *, ...) → None` | Log a session event |
| `log_request_header(store, session_id, header, reason, starts_series) → None` | Log a request header |
| `log_turn_start(store, session_id, turn) → None` | Log turn start |
| `log_turn_end(store, session_id, turn, reason) → None` | Log turn end |
| `log_user_message(store, session_id, turn, step, content) → None` | Log a user message |
| `log_assistant_message(store, session_id, turn, step, content) → None` | Log an assistant message |
| `log_tool_call(store, session_id, tool_name, arguments) → None` | Log a tool call |
| `log_tool_result(store, session_id, tool_name, result) → None` | Log a tool result |

### `new_session_id() → str`

Generate a new session ID in `YYYYMMDD-HHMMSS-XXXXXX` format.

---

## LLM Client

### `zcoder.agent.codeagent.llm`

Loopback-only OpenAI-compatible streaming client for a local Ollama server.

### `LocalLLM`

```python
from zcoder.agent.codeagent.llm import LocalLLM

llm = LocalLLM(model="zcoder-pro", base_url="http://127.0.0.1:11434")
async for chunk in llm.stream(messages, tools):
    ...
```

**Constructor:** `LocalLLM(model=None, base_url=None, temperature=0.2, max_tokens=4096, timeout=600)`

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `model` | `str` | Model name |
| `base_url` | `str` | Server URL (loopback-only) |
| `temperature` | `float` | Sampling temperature |
| `max_tokens` | `int` | Max output tokens |
| `timeout` | `float` | Request timeout in seconds |

**Methods:**

| Method | Description |
|--------|-------------|
| `stream(messages, tools) → AsyncGenerator[LLMChunk]` | Stream model response |
| `discover_model() → str \| None` | Ask server which model is loaded |

### `LLMError`

Raised on model-server failure. Has `retryable: bool` attribute for transient errors (429/5xx, connection refused).

### `local_base_url(raw=None) → str`

Return a loopback-only server URL. Rejects non-loopback hosts, HTTPS, credentials, query strings, and fragments.

### `estimate_tokens(text: str) → int`

Token estimate (~4 chars per token, rounded up, minimum 1).

### `render_context_report(rep, model="", live=True) → str`

Render a plain-text context budget report with bar visualizations.

---

## Slash Commands

### `zcoder.agent.codeagent.commands`

Slash command registry and dispatch. Commands are registered with the `@command` decorator.

**Functions:**

| Function | Description |
|----------|-------------|
| `dispatch(agent, line) → CommandResult` | Dispatch a slash command line |
| `list_commands() → list[Command]` | List all registered commands |
| `command_names() → list[str]` | List command names with `/` prefix |

**Registered commands:** `/help`, `/clear`, `/compact`, `/mode`, `/plan`, `/model`, `/cost`, `/todos`, `/diff`, `/review`, `/skills`, `/skill`, `/workflows`, `/effort`, `/mcp`, `/rewind`, `/undo`, `/fork`, `/sessions`, `/resume`, `/init`, `/memory`, `/tools`, `/permissions`, `/status`, `/exit`

### `CommandResult`

| Field | Type | Description |
|-------|------|-------------|
| `output` | `str` | Output text |
| `action` | `str \| None` | Action: clear, exit, prompt, resumed, mode |
| `prompt` | `str \| None` | Text to send to model |
| `is_error` | `bool` | Whether result is an error |

---

## Plugin System

### `zcoder.agent.plugin.manager.PluginManager`

Manages loaded plugins organized by tier, with allowlist/blocklist support.

```python
from zcoder.agent.plugin.manager import PluginManager

manager = PluginManager()
manager.register_config(config)
manager.load_all()
plugins = manager.get_all_plugins_ordered()
hooks = manager.get_hooks_for_event("turn/end")
```

**Methods:**

| Method | Description |
|--------|-------------|
| `register_config(config) → None` | Register a Config instance |
| `get_config() → Config \| None` | Get registered config |
| `load_all() → None` | Discover and load all plugins |
| `reload() → None` | Clear cache and reload all plugins |
| `get_plugins_for_tier(tier) → list` | Get plugins for a tier |
| `get_all_plugins_ordered() → list` | Get plugins in tier precedence order |
| `get_plugin(name) → LoadedPlugin \| None` | Get a plugin by name |
| `get_hooks_for_event(event) → list` | Get hooks for an event, ordered by tier |
| `get_tools(tier_filter=None) → dict` | Get all tools |
| `get_commands(tier_filter=None) → dict` | Get all commands |
| `get_mcp_servers() → dict` | Get all MCP servers |
| `get_plugins_by_tier() → dict` | Get plugins grouped by tier |
| `get_stats() → dict` | Get plugin statistics |
| `load_from_git(url, branch=None, depth=1) → LoadedPlugin \| None` | Load a plugin from git |

**Allowlist/Blocklist:**

```python
manager = PluginManager(allowlist=["good-plugin"], blocklist=["bad-plugin"])
```

### `PluginTier`

| Tier | Value | Description |
|------|-------|-------------|
| `PREPEND` | 0 | Organization prepend (highest precedence) |
| `USER` | 1 | User-installed plugins |
| `APPEND` | 2 | Organization append |
| `BUILTIN` | 3 | Built-in plugins (lowest precedence) |

---

## Credential Management

### `zcoder.credentials.credential_seam`

Credential-reference capability seam for resolving, storing, and managing credentials.

### `CredentialRef`

Branded reference to a credential environment variable name.

```python
from zcoder.credentials.credential_seam import credentialRef, CredentialRef

ref = credentialRef("DEEPSEEK_API_KEY")  # or CredentialRef.parse("DEEPSEEK_API_KEY")
```

### `CredentialKey`

Branded key identifying a stored credential record (`"<scope>/<id>"`).

```python
key = CredentialKey.parse("deepseek/plugin-1")
```

### `CredentialProvider` (Abstract)

Abstract credential service. Implementations must provide:

| Method | Description |
|--------|-------------|
| `resolve(ref) → ResolvedCredential \| None` | Resolve a reference to its value |
| `describe(ref) → CredentialInfo` | Describe a reference without exposing value |
| `set(ref, value) → None` | Durably store a value |
| `unset(ref) → None` | Remove a reference |
| `readRecord(key) → CredentialRecord \| None` | Read a stored record |
| `describeRecord(key) → CredentialRecordInfo` | Describe a record |
| `listRecords() → list[CredentialRecordEntry]` | Enumerate records (values excluded) |
| `modifyRecord(key, mutate) → CredentialRecord \| None` | Serialized read-modify-write |
| `deleteRecord(key) → None` | Remove a record |

### Types

| Type | Description |
|------|-------------|
| `ResolvedCredential(value, source)` | Resolved value and its source layer |
| `CredentialRecord(kind, value=None)` | Stored credential record |
| `CredentialRecordEntry(key, kind)` | Record address (value excluded) |
| `CredentialRecordInfo(configured, kind, writable)` | Record presence/writability facts |
| `CredentialInfo(configured, kind, writable)` | Reference configuration info |

### `is_credential_ref_name(value) → bool`

Check if a string could name a credential reference (matches `^[A-Za-z_][A-Za-z0-9_]*$`).

---

## Error Handling

All modules raise `zcoder.core.exceptions.ZCoderError` or subclasses:

- `SecurityError` — security policy violation
- `ConfigError` — configuration error
- `CredentialError` — credential operation failure
- `ToolError` — tool execution error
- `LLMError` — model server failure (has `retryable` attribute)

---

## Testing

All public APIs have unit and integration tests in `src/zcoder/tests/`. Run with:

```bash
python -m pytest src/zcoder/tests/
```
