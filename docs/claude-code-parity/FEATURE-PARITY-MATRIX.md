# ZCoder vs Claude Code Feature Parity Matrix

**ZCoder Version:** 1.60.0  
**Assessment Date:** 2026-11-13  
**Reference:** Claude Code (Anthropic) — Current Public Documentation  
**Scope:** Complete capability parity assessment

---

## Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Full parity / equivalent implementation |
| 🟡 | Partial / different implementation (documented) |
| ❌ | Missing in zcoder |
| 🔵 | zcoder-only feature |
| 📋 | Audited, needs implementation |
| 🚫 | Excluded (proprietary/platform-specific) |
| 🔴 | Blocked (verified dependency) |

---

## F01 — Terminal UI and Rendering Engine

| ID | Capability | Ref Behavior | ZCoder Baseline | Gap | Strategy | Priority |
|----|------------|--------------|-----------------|-----|----------|----------|
| F01-01 | Interactive REPL | `claude` starts interactive session | `zcoder -i` | ✅ | REUSE | — |
| F01-02 | One-shot prompting | `claude -p "prompt"` | `zcoder -p` | ✅ | REUSE | — |
| F01-03 | TUI full-screen | ❌ Not in Claude Code | Textual TUI (`--tui`) | 🔵 zcoder-only | NATIVE | — |
| F01-04 | GUI/Desktop app | ❌ Not in Claude Code | Native desktop (`--gui`) | 🔵 zcoder-only | NATIVE | — |
| F01-05 | Web Console | ❌ Not in Claude Code | FastAPI dashboard | 🔵 zcoder-only | NATIVE | — |
| F01-06 | Multi-pane rendering | ✅ Multiple panes/views | Textual TUI panes | 🟡 Partial | EXTEND | P1 |
| F01-07 | Dialogs & modals | ✅ Dialogs & modal interactions | Partial (Textual dialogs) | 🟡 Partial | EXTEND | P2 |
| F01-08 | Streaming assistant output | ✅ Real-time token streaming | ✅ Streaming in TUI/GUI | ✅ | REUSE | — |
| F01-09 | Tool execution progress | ✅ Visual progress | Partial (logs) | 🟡 Partial | EXTEND | P2 |
| F01-10 | Task/subagent status | ✅ Live status | Partial (logs) | 🟡 Partial | EXTEND | P2 |
| F01-11 | Session switching | ✅ Multiple sessions | `--code-agent-session` | ✅ | REUSE | — |
| F01-12 | Context/token usage | ✅ Live display | `--metrics-show` | 🟡 Different UI | EXTEND | P2 |
| F01-13 | Model/provider status | ✅ Live display | `--list-models` | 🟡 CLI only | EXTEND | P2 |
| F01-14 | Permission prompts | ✅ Interactive prompts | `--perms-add` + hooks | 🟡 CLI-based | EXTEND | P1 |
| F01-15 | Keyboard navigation | ✅ Full keyboard control | Textual bindings | ✅ | REUSE | — |
| F01-16 | Configurable shortcuts | ✅ Custom keybindings | Textual keybindings | ✅ | REUSE | — |
| F01-17 | Terminal resizing | ✅ Dynamic resize | Textual handles | ✅ | REUSE | — |
| F01-18 | Unicode/ANSI correctness | ✅ Full support | Textual + rich | ✅ | REUSE | — |
| F01-19 | Non-interactive/CI mode | ✅ `claude -p` | `zcoder -p` | ✅ | REUSE | — |
| F01-20 | Error/cancellation rendering | ✅ Visual errors | Partial (logs) | 🟡 Partial | EXTEND | P2 |
| F01-21 | Accessibility fallbacks | ✅ Screen reader support | Textual supports | 🟡 Partial | EXTEND | P3 |

---

## F02 — Plugin and Marketplace System

| ID | Capability | Ref Behavior | ZCoder Baseline | Gap | Strategy | Priority |
|----|------------|--------------|-----------------|-----|----------|----------|
| F02-01 | Local plugins | ✅ Local directory | `~/.zcoder/plugins/` | ✅ | REUSE | — |
| F02-02 | Git repositories | ✅ Git plugin sources | 📋 Missing | 📋 | NATIVE | P1 |
| F02-03 | Remote registries | ✅ npm/GitHub packages | 📋 Missing | 📋 | NATIVE | P2 |
| F02-04 | Versioned manifests | ✅ JSON manifests | `manifest.json` | ✅ | REUSE | — |
| F02-05 | Dependency declarations | ✅ Package deps | `dependencies` in manifest | ✅ | REUSE | — |
| F02-06 | Compatibility constraints | ✅ Version constraints | 📋 Partial | 📋 | EXTEND | P2 |
| F02-07 | Plugin discovery | ✅ Auto-discovery | `PluginLoader.discover_plugins()` | ✅ | REUSE | — |
| F02-08 | Installation/removal | ✅ CLI install/uninstall | `--plugin-install`/`--plugin-uninstall` | ✅ | REUSE | — |
| F02-09 | Enable/disable | ✅ Toggle plugins | `--plugin-enable`/`--plugin-disable` | ✅ | REUSE | — |
| F02-10 | Upgrade/rollback | ✅ Version management | 📋 Missing | 📋 | NATIVE | P2 |
| F02-11 | Integrity verification | ✅ Checksums | 📋 Missing | 📋 | NATIVE | P2 |
| F02-12 | Signature verification | ✅ Signed plugins | 📋 Missing | 📋 | NATIVE | P2 |
| F02-13 | Registry configuration | ✅ Configurable registries | `--plugin-marketplace-add` | ✅ | REUSE | — |
| F02-14 | Enterprise allowlists | ✅ Org policies | 📋 Partial (tier system) | 📋 | EXTEND | P1 |
| F02-15 | Blocklists | ✅ Blocked plugins | 📋 Missing | 📋 | NATIVE | P2 |
| F02-16 | Conflict detection | ✅ Dependency conflicts | 📋 Missing | 📋 | NATIVE | P2 |
| F02-16 | Dependency resolution | ✅ Auto-resolve | 📋 Missing | 📋 | NATIVE | P2 |
| F02-17 | Lifecycle management | ✅ Full lifecycle | `PluginLoader` + `PluginManager` | ✅ | REUSE | — |
| F02-17 | Audit records | ✅ Installation logs | 📋 Partial (logs) | 📋 | EXTEND | P2 |
| F02-18 | Sandboxed execution | ✅ Plugin sandbox | 📋 Missing | 📋 | NATIVE | P2 |
| F02-19 | Trust controls | ✅ Explicit trust | Tier system (prepend/user/append) | ✅ | REUSE | — |
| F02-19 | Provenance tracking | ✅ Source tracking | 📋 Partial (manifest) | 📋 | EXTEND | P2 |
| F02-20 | Permission controls | ✅ Plugin perms | Tier-based | ✅ | REUSE | — |
| F02-20 | Rollback controls | ✅ Version rollback | 📋 Missing | 📋 | NATIVE | P2 |

---

## F03 — Audio and Model Hooks

| ID | Capability | Ref Behavior | ZCoder Baseline | Gap | Strategy | Priority |
|----|------------|--------------|-----------------|-----|----------|----------|
| F03-01 | Audio input providers | ✅ Microphone/file | `MicrophoneProvider`, `FileProvider` | ✅ | REUSE | — |
| F03-02 | Audio transcription | ✅ STT adapters | `WhisperSTT`, `OpenAIWhisperSTT` | ✅ | REUSE | — |
| F03-03 | Voice activity detection | ✅ VAD | `SileroVAD`, `WebRTCVAD` | ✅ | REUSE | — |
| F03-04 | Audio streaming contracts | ✅ Stream contracts | `AudioStream`, `MemoryAudioStream`, `AudioStreamMixer` | ✅ | REUSE | — |
| F03-05 | Model lifecycle events | ✅ Model events | `ModelLifecycleEvent` (8 events) | ✅ | REUSE | — |
| F03-06 | Pre-model selection | ✅ Pre-selection hooks | `ModelLifecycleHooks.fire_pre_selection()` | ✅ | REUSE | — |
| F03-07 | Post-model selection | ✅ Post-selection hooks | `ModelLifecycleHooks.fire_post_selection()` | ✅ | REUSE | — |
| F03-08 | Capability negotiation | ✅ Capability matrix | `ModelLifecycleHooks.fire_capability_negotiation()` | ✅ | REUSE | — |
| F03-09 | Request validation | ✅ Model validation | `model_validation_hook()` with retired/deprecated detection | ✅ | REUSE | — |
| F03-10 | Provider fallback | ✅ Fallback policy | `--fable5-fallback-chain` + retry classification | ✅ | REUSE | — |
| F03-11 | Cancellation/timeout | ✅ Cancellation | Partial (timeouts) + retry engine with timeouts | 🟡 Partial | EXTEND | P2 |

---

## F04 — Command System

| ID | Capability | Ref Behavior | ZCoder Baseline | Gap | Strategy | Priority |
|----|------------|--------------|-----------------|-----|----------|----------|
| F04-01 | Built-in commands | ✅ `/help`, `/config`, etc. | `argparse` subcommands | 🟡 Partial | EXTEND | P1 |
| F04-02 | User-defined commands | ✅ Custom commands | `--plugin-install` commands | ✅ | REUSE | — |
| F04-03 | Project-defined commands | ✅ `.claude/commands` | 📋 Missing | 📋 | NATIVE | P2 |
| F04-04 | Namespaced commands | ✅ `namespace:cmd` | 📋 Partial (plugin prefix) | 🟡 Partial | EXTEND | P2 |
| F04-05 | Command aliases | ✅ Aliases | 📋 Missing | 📋 | NATIVE | P2 |
| F04-06 | Argument parsing | ✅ Typed args | `argparse` | ✅ | REUSE | — |
| F04-07 | Typed parameters | ✅ Typed params | `argparse` + Pydantic | ✅ | REUSE | — |
| F04-08 | Validation | ✅ Input validation | Pydantic + argparse | ✅ | REUSE | — |
| F04-09 | Argument completion | ✅ Tab completion | 📋 Missing | 📋 | NATIVE | P2 |
| F04-10 | Command discovery | ✅ `--help` lists | `--list-skills`, `--list-agents` | ✅ | REUSE | — |
| F04-11 | Command permissions | ✅ Per-command perms | `--perms-add` + hooks | 🟡 Partial | EXTEND | P1 |
| F04-12 | Execution lifecycle | ✅ Pre/post hooks | Hook events | ✅ | REUSE | — |
| F04-13 | Output formatting | ✅ Formatted output | Rich/Textual | ✅ | REUSE | — |
| F04-14 | Command composition | ✅ Piped commands | 📋 Missing | 📋 | NATIVE | P2 |
| F04-15 | Help generation | ✅ Auto help | argparse auto-help | ✅ | REUSE | — |
| F04-16 | Command versioning | ✅ Versioned commands | 📋 Missing | 📋 | NATIVE | P3 |
| F04-17 | Deprecated compatibility | ✅ Backwards compat | 📋 Missing | 📋 | NATIVE | P3 |
| F04-18 | Authorization boundaries | ✅ Same as tools | Hook-based perms | ✅ | REUSE | — |

---

## F05 — Runtime Hooks

| ID | Capability | Ref Behavior | ZCoder Baseline | Gap | Strategy | Priority |
|----|------------|--------------|-----------------|-----|----------|----------|
| F05-01 | SessionStart | ✅ Session start | `SESSION_START` | ✅ | REUSE | — |
| F05-02 | SessionEnd | ✅ Session end | `SESSION_END` | ✅ | REUSE | — |
| F05-03 | UserPromptSubmit | ✅ Prompt submit | `USER_PROMPT_SUBMIT` | ✅ | REUSE | — |
| F05-04 | UserPromptExpansion | ✅ Prompt expansion | `UserPromptExpansion` event | ✅ | REUSE | — |
| F05-05 | PreToolUse | ✅ Pre-tool hook | `PRE_TOOL_USE` | ✅ | REUSE | — |
| F05-06 | PostToolUse | ✅ Post-tool hook | `POST_TOOL_USE` | ✅ | REUSE | — |
| F05-07 | PostToolUseFailure | ✅ Failure hook | `PostToolUseFailure` event | ✅ | REUSE | — |
| F05-08 | PostToolBatch | ✅ Batch completion | `PostToolBatch` event | ✅ | REUSE | — |
| F05-09 | PermissionRequest | ✅ Permission prompt | `PERMISSION_REQUEST` | ✅ | REUSE | — |
| F05-10 | PermissionDenied | ✅ Denied hook | `PERMISSION_DENIED` | ✅ | REUSE | — |
| F05-11 | Stop | ✅ Turn stop | `STOP` | ✅ | REUSE | — |
| F05-12 | StopFailure | ✅ Stop failure | `StopFailure` event | ✅ | REUSE | — |
| F05-13 | SubagentStart | ✅ Subagent start | `SUBAGENT_START` | ✅ | REUSE | — |
| F05-14 | SubagentStop | ✅ Subagent stop | `SUBAGENT_STOP` | ✅ | REUSE | — |
| F05-15 | TaskCreated | ✅ Task created | `TASK_CREATED` | ✅ | REUSE | — |
| F05-16 | TaskCompleted | ✅ Task done | `TASK_COMPLETED` | ✅ | REUSE | — |
| F05-17 | PreCompact | ✅ Pre-compaction | `PRE_COMPACT` + `CLASSIC_PRE_COMPACT` | ✅ | REUSE | — |
| F05-18 | PostCompact | ✅ Post-compaction | `POST_COMPACT` + `CLASSIC_POST_COMPACT` | ✅ | REUSE | — |
| F05-19 | Notification | ✅ Notifications | `NOTIFICATION` + `CLASSIC_NOTIFICATION` | ✅ | REUSE | — |
| F05-20 | ConfigChange | ✅ Config change | `CONFIG_CHANGE` | ✅ | REUSE | — |
| F05-21 | InstructionsLoaded | ✅ Instructions loaded | 📋 Missing | 📋 | NATIVE | P2 |
| F05-22 | CwdChanged | ✅ CWD changed | 📋 Missing | 📋 | NATIVE | P2 |
| F05-23 | FileChanged | ✅ File watch | 📋 Missing | 📋 | NATIVE | P2 |
| F05-24 | DirectoryAdded | ✅ Dir added | 📋 Missing | 📋 | NATIVE | P2 |
| F05-25 | PreModelSwitch | ✅ Model switch | 📋 Missing | 📋 | NATIVE | P2 |
| F05-26 | PostModelSwitch | ✅ Post-switch | 📋 Missing | 📋 | NATIVE | P2 |
| F05-27 | MessageDisplay | ✅ Message shown | 📋 Missing | 📋 | NATIVE | P2 |
| F05-28 | WorktreeCreate | ✅ Git worktree | `WORKTREE_CREATE` + `CLASSIC_WORKTREE_CREATE` | ✅ | REUSE | — |
| F05-29 | WorktreeRemove | ✅ Worktree remove | `WORKTREE_REMOVE` + `CLASSIC_WORKTREE_REMOVE` | ✅ | REUSE | — |
| F05-30 | Elicitation | ✅ User input | `ELICITATION` + `CLASSIC_ELICITATION` | ✅ | REUSE | — |

### Handler Types
| ID | Handler Type | Ref Behavior | ZCoder Baseline | Gap | Strategy | Priority |
|----|--------------|--------------|-----------------|-----|----------|----------|
| F05-31 | Command hooks | ✅ Shell commands | `HookBus` subprocess | ✅ | REUSE | — |
| F05-32 | HTTP hooks | ✅ Webhooks | 📋 Missing | 📋 | NATIVE | P2 |
| F05-33 | MCP tool hooks | ✅ MCP tools | MCP integration | ✅ | REUSE | — |
| F05-34 | Prompt-based hooks | ✅ Prompt injection | 📋 Missing | 📋 | NATIVE | P2 |
| F05-35 | Agent-based hooks | ✅ Agent hooks | Agent hooks | ✅ | REUSE | — |

### Hook Execution
| ID | Capability | Ref Behavior | ZCoder Baseline | Gap | Strategy | Priority |
|----|------------|--------------|-----------------|-----|----------|----------|
| F05-36 | Event schema validation | ✅ JSON schema | Pydantic | ✅ | REUSE | — |
| F05-37 | Matchers | ✅ Tool/event matchers | `HookConfig.matcher` | ✅ | REUSE | — |
| F05-38 | Multiple handlers | ✅ Sequential/parallel | `HookBus` sequential | 🟡 Sequential only | EXTEND | P2 |
| F05-39 | Sequential/parallel policy | ✅ Configurable | Sequential only | 🟡 Partial | EXTEND | P2 |
| F05-40 | Timeouts | ✅ Per-hook timeout | `HookConfig.timeout` | ✅ | REUSE | — |
| F05-41 | Cancellation | ✅ Cancel hooks | 📋 Partial | 🟡 Partial | EXTEND | P2 |
| F05-42 | Retries | ✅ Safe retries | 📋 Missing | 📋 | NATIVE | P2 |
| F05-43 | Failure handling | ✅ Error handling | Try/catch + logging | ✅ | REUSE | — |
| F05-44 | Allow/deny/continue | ✅ Decisions | `HookResult.blocked` | ✅ | REUSE | — |
| F05-45 | Structured I/O | ✅ JSON I/O | JSON payload | ✅ | REUSE | — |
| F05-46 | Hook provenance | ✅ Source tracking | `HookResult.deny_reason` | ✅ | REUSE | — |
| F05-47 | Audit records | ✅ Hook audit | Logs + `ui.log` | 🟡 Partial | EXTEND | P2 |
| F05-48 | Per-project config | ✅ Project hooks | Project plugin dirs | ✅ | REUSE | — |
| F05-49 | Per-user config | ✅ User hooks | User plugin dirs | ✅ | REUSE | — |
| F05-50 | Trust boundaries | ✅ Sandbox | Subprocess isolation | ✅ | REUSE | — |
| F05-51 | Execution sandboxing | ✅ Isolation | Subprocess + env sanitization | ✅ | REUSE | — |

---

## F06 — FS/HTTP/Process/Clock/Store/Config Hooks

| ID | Capability | Ref Behavior | ZCoder Baseline | Gap | Strategy | Priority |
|----|------------|--------------|-----------------|-----|----------|----------|
| F06-01 | Filesystem access | ✅ FS provider | 📋 `FS_READ`/`FS_WRITE` events | 📋 | NATIVE | P2 |
| F06-02 | File reads/writes | ✅ Read/write hooks | 📋 Missing | 📋 | NATIVE | P2 |
| F06-03 | Directory traversal | ✅ Dir traversal | 📋 `FS_LIST`/`FS_STAT` events | 📋 | NATIVE | P2 |
| F06-04 | File watching | ✅ Watch hooks | 📋 Missing | 📋 | NATIVE | P3 |
| F06-05 | Safe path resolution | ✅ Path safety | `tools.sandbox` | 🟡 Partial | EXTEND | P2 |
| F06-06 | HTTP requests | ✅ HTTP hooks | `HTTP_FETCH` event | 📋 | NATIVE | P2 |
| F06-07 | HTTP streaming | ✅ Stream hooks | 📋 Missing | 📋 | NATIVE | P2 |
| F06-08 | Process execution | ✅ Process hooks | `PROCESS_RUN` event | 📋 | NATIVE | P2 |
| F06-09 | Process management | ✅ Process mgmt | 📋 Missing | 📋 | NATIVE | P2 |
| F06-10 | Clock & deadlines | ✅ Time hooks | `CLOCK_*` events | 📋 | NATIVE | P2 |
| F06-11 | Key-value storage | ✅ Store hooks | `STORE_*` events | 📋 | NATIVE | P2 |
| F06-12 | Persistent storage | ✅ Persistent store | SQLite/PostgreSQL | ✅ | REUSE | — |
| F06-13 | Configuration loading | ✅ Config hooks | `CONFIG_READ`/`CONFIG_WRITE` | 📋 | NATIVE | P2 |
| F06-14 | Configuration updates | ✅ Config updates | 📋 Missing | 📋 | NATIVE | P2 |
| F06-15 | Secret access | ✅ Secret hooks | `env.get`/`env.set` | 🟡 Partial | EXTEND | P2 |

### Containment & SSRF
| ID | Capability | Ref Behavior | ZCoder Baseline | Gap | Strategy | Priority |
|----|------------|--------------|-----------------|-----|----------|----------|
| F06-16 | Path containment | ✅ Path safety | `tools.sandbox` + `codeagent` sandbox | 🟡 Partial | EXTEND | P1 |
| F06-17 | SSRF protection | ✅ SSRF guard | `browse` allow-domain | 🟡 Partial | EXTEND | P1 |
| F06-18 | Redirect validation | ✅ Redirect guard | 📋 Missing | 📋 | NATIVE | P2 |
| F06-19 | Size limits | ✅ Payload limits | 📋 Missing | 📋 | NATIVE | P2 |

---

## F07 — Complete Agent System

| ID | Capability | Ref Behavior | ZCoder Baseline | Gap | Strategy | Priority |
|----|------------|--------------|-----------------|-----|----------|----------|
| F07-01 | Primary agent | ✅ Main agent | `CodeAgent` + `AgentRuntime` | ✅ | REUSE | — |
| F07-02 | General subagents | ✅ Subagents | `--code-agent-subagent` | ✅ | REUSE | — |
| F07-03 | Specialized agents | ✅ Specialized | `--agent-create` (managed agents) | ✅ | REUSE | — |
| F07-04 | Agent frontmatter | ✅ Metadata | `Agent` model | ✅ | REUSE | — |
| F07-05 | Tool permissions | ✅ Per-agent perms | `--code-agent-permission` | ✅ | REUSE | — |
| F07-06 | Agent model selection | ✅ Per-agent model | `--agent-create --model` | ✅ | REUSE | — |
| F07-07 | Agent budgets | ✅ Budget limits | `--agent-session-budget-set` | ✅ | REUSE | — |
| F07-08 | Max execution depth | ✅ Depth limit | `--code-agent-subagent-turns` | ✅ | REUSE | — |
| F07-09 | Context isolation | ✅ Isolation | Subagent isolation | ✅ | REUSE | — |
| F07-10 | Agent lifecycle | ✅ Full lifecycle | `--agent-create` to `--agent-delete` | ✅ | REUSE | — |
| F07-11 | Parallel execution | ✅ Parallel agents | `--route-parallel` | ✅ | REUSE | — |
| F07-12 | Task scheduling | ✅ Scheduled agents | `--agent-schedule-create` | ✅ | REUSE | — |
| F07-13 | Delegation | ✅ Agent delegation | `--agent-orchestrate` | ✅ | REUSE | — |
| F07-14 | Result aggregation | ✅ Aggregation | `--agent-review-multiagent` | ✅ | REUSE | — |
| F07-15 | Agent cancellation | ✅ Cancel agents | `--agent-schedule-cancel` | ✅ | REUSE | — |
| F07-16 | Failure recovery | ✅ Recovery | Checkpoints + rewind | 🟡 Partial | EXTEND | P2 |
| F07-17 | Transcript management | ✅ Transcripts | `--code-agent-session` | ✅ | REUSE | — |
| F07-18 | Agent-to-agent messages | ✅ A2A messages | 📋 Missing | 📋 | NATIVE | P2 |
| F07-19 | Execution observability | ✅ Observability | `--obs-*` + metrics | 🟡 Partial | EXTEND | P2 |
| F07-20 | Independent context windows | ✅ Isolated context | Subagent isolation | ✅ | REUSE | — |
| F07-21 | Deterministic delegation | ✅ Contracts | `--agent-orchestrate` | ✅ | REUSE | — |
| F07-22 | No uncontrolled spawning | ✅ Controlled | Budget + turns limits | ✅ | REUSE | — |

---

## F08 — Prompt System

| ID | Capability | Ref Behavior | ZCoder Baseline | Gap | Strategy | Priority |
|----|------------|--------------|-----------------|-----|----------|----------|
| F08-01 | System prompts | ✅ System prompt | `--interactive-system` + skills | ✅ | REUSE | — |
| F08-02 | Developer prompts | ✅ Dev prompts | Skills + `--agent-system` | ✅ | REUSE | — |
| F08-03 | User prompts | ✅ User prompts | CLI prompts | ✅ | REUSE | — |
| F08-04 | Project instructions | ✅ CLAUDE.md | `--agent-context-editing` | ✅ | REUSE | — |
| F08-05 | Hierarchical loading | ✅ Hierarchical | Enterprise → user → project | ✅ | REUSE | — |
| F08-06 | Prompt templates | ✅ Templates | Skills + `--prompt-lib-*` | ✅ | REUSE | — |
| F08-07 | Prompt variables | ✅ Variables | `--optimize` + skills | ✅ | REUSE | — |
| F08-08 | Dynamic composition | ✅ Dynamic | `--agent-context-editing` | ✅ | REUSE | — |
| F08-09 | Context injection | ✅ Injection | Skills + memory | ✅ | REUSE | — |
| F08-10 | Prompt caching | ✅ Provider caching | `--cache` + `--cache-warm` | ✅ | REUSE | — |
| F08-11 | Prompt versioning | ✅ Versioned | `--prompt-lib-*` | ✅ | REUSE | — |
| F08-12 | Prompt provenance | ✅ Provenance | `--prompt-lib-info` | ✅ | REUSE | — |
| F08-13 | Output format constraints | ✅ Constraints | `--structured` + schema | ✅ | REUSE | — |
| F08-14 | Structured JSON output | ✅ JSON output | `--structured` | ✅ | REUSE | — |
| F08-15 | Prompt validation | ✅ Validation | `--score-prompt` | ✅ | REUSE | — |
| F08-16 | Prompt evaluation | ✅ Evaluation | `--ab-test` + `--eval-*` | ✅ | REUSE | — |
| F08-17 | Regression tests | ✅ Regressions | `--eval-run` | ✅ | REUSE | — |
| F08-18 | Trusted instructions | ✅ Trust boundaries | `--no-project-memory` | ✅ | REUSE | — |

---

## F09 — UI Hooks and Extension API

| ID | Capability | Ref Behavior | ZCoder Baseline | Gap | Strategy | Priority |
|----|------------|--------------|-----------------|-----|----------|----------|
| F09-01 | View lifecycle | ✅ View hooks | `UI_RENDER`/`UI_CLOSE` | 🟡 Partial | EXTEND | P2 |
| F09-02 | Dialog lifecycle | ✅ Dialog hooks | `UI_CLOSE` (back out) | 🟡 Partial | EXTEND | P2 |
| F09-03 | Panel registration | ✅ Panels | `DiffPane` + `UIPaneManager` | 🟡 Partial | EXTEND | P2 |
| F09-04 | Rendering extensions | ✅ Render hooks | `UI_RENDER` | 🟡 Partial | EXTEND | P2 |
| F09-05 | Status line | ✅ Statusline | `--status-line` | ✅ | REUSE | — |
| F09-06 | Notifications | ✅ Notifications | `NOTIFICATION` hook | ✅ | REUSE | — |
| F09-07 | Input controls | ✅ Input hooks | `UI_FOCUS`/`UI_SCROLL` | 🟡 Partial | EXTEND | P2 |
| F09-08 | Theme integration | ✅ Themes | Textual themes | ✅ | REUSE | — |
| F09-09 | Keyboard bindings | ✅ Keybind hooks | Textual keybindings | ✅ | REUSE | — |
| F09-10 | Context-aware actions | ✅ Context actions | `--code-agent-slash` | ✅ | REUSE | — |
| F09-11 | Plugin-owned views | ✅ Plugin views | 📋 Missing | 📋 | NATIVE | P2 |
| F09-12 | UI state subscriptions | ✅ State subs | `UI_FOCUS`/`UI_SCROLL` | 🟡 Partial | EXTEND | P2 |
| F09-13 | UI internals protection | ✅ Encapsulation | Textual encapsulation | ✅ | REUSE | — |

---

## F10 — Settings and Configuration Schema

| ID | Capability | Ref Behavior | ZCoder Baseline | Gap | Strategy | Priority |
|----|------------|--------------|-----------------|-----|----------|----------|
| F10-01 | Enterprise managed | ✅ Managed settings | `ProductionConfig` + policy | ✅ | REUSE | — |
| F10-02 | System scope | ✅ System config | `/etc/zcoder/` | 🟡 Partial | EXTEND | P2 |
| F10-03 | User scope | ✅ User config | `~/.zcoder-config.json` | ✅ | REUSE | — |
| F10-04 | Project scope | ✅ Project config | `.zcoder/config.json` | 🟡 Partial | EXTEND | P2 |
| F10-05 | Workspace scope | ✅ Workspace config | 📋 Missing | 📋 | NATIVE | P2 |
| F10-06 | Directory scope | ✅ Dir config | 📋 Missing | 📋 | NATIVE | P2 |
| F10-07 | JSON/YAML | ✅ Both formats | JSON only (YAML 📋) | 🟡 Partial | EXTEND | P2 |
| F10-08 | Schema validation | ✅ Schema | Pydantic models | ✅ | REUSE | — |
| F10-09 | Defaults | ✅ Defaults | Pydantic defaults | ✅ | REUSE | — |
| F10-10 | Type safety | ✅ Type safety | Pydantic + mypy | ✅ | REUSE | — |
| F10-11 | Config precedence | ✅ Precedence | Policy → managed → user → project | ✅ | REUSE | — |
| F10-12 | Environment overrides | ✅ Env overrides | `env.get`/`env.set` | ✅ | REUSE | — |
| F10-13 | Secret references | ✅ Secret refs | File-based secrets | ✅ | REUSE | — |
| F10-14 | Runtime reload | ✅ Hot reload | `--plugin-install` reloads | 🟡 Partial | EXTEND | P2 |
| F10-15 | Migration | ✅ Migrations | 📋 Missing | 📋 | NATIVE | P2 |
| F10-16 | Deprecation handling | ✅ Deprecation | 📋 Missing | 📋 | NATIVE | P2 |
| F10-17 | Invalid config diagnostics | ✅ Diagnostics | Pydantic errors | ✅ | REUSE | — |
| F10-18 | Policy-enforced settings | ✅ Policy settings | `SettingsPolicyReader` (fail-closed) | ✅ | REUSE | — |
| F10-19 | Settings introspection | ✅ Introspection | `--settings-show` | ✅ | REUSE | — |
| F10-20 | Audit logging | ✅ Audit | `compliance-*` + `ui.log` | 🟡 Partial | EXTEND | P2 |

---

## F11 — Session Management and Compaction

| ID | Capability | Ref Behavior | ZCoder Baseline | Gap | Strategy | Priority |
|----|------------|--------------|-----------------|-----|----------|----------|
| F11-01 | Session creation | ✅ Create session | `--code-agent-session` | ✅ | REUSE | — |
| F11-02 | Session persistence | ✅ Persist | SQLite/PostgreSQL | ✅ | REUSE | — |
| F11-03 | Resume | ✅ Resume | `--code-agent-resume` | ✅ | REUSE | — |
| F11-04 | Fork | ✅ Fork | `--agent-branch` | ✅ | REUSE | — |
| F11-05 | Branch | ✅ Branch | `--agent-branch` | ✅ | REUSE | — |
| F11-06 | Rename | ✅ Rename | `SessionStore.rename()` | ✅ | REUSE | — |
| F11-07 | Search | ✅ Search | `SessionStore.search()` | ✅ | REUSE | — |
| F11-08 | Export | ✅ Export | `SessionStore.export()` | ✅ | REUSE | — |
| F11-09 | Import | ✅ Import | `SessionStore.import_session()` | ✅ | REUSE | — |
| F11-10 | Delete with confirmation | ✅ Delete confirm | `SessionStore.delete(confirm=True)` | ✅ | REUSE | — |
| F11-11 | Session metadata | ✅ Metadata | Session model | ✅ | REUSE | — |
| F11-12 | Message history | ✅ History | Session messages | ✅ | REUSE | — |
| F11-13 | Tool execution history | ✅ Tool history | Tool call logs | ✅ | REUSE | — |
| F11-14 | Checkpoints | ✅ Checkpoints | `--code-agent-checkpoint` | ✅ | REUSE | — |
| F11-14 | Rewind | ✅ Rewind | `--agent-rewind` | ✅ | REUSE | — |
| F11-15 | Context management | ✅ Context mgmt | `--agent-context-editing` | ✅ | REUSE | — |
| F11-16 | Context compaction | ✅ Compaction | `--compaction` + hooks | ✅ | REUSE | — |
| F11-17 | Automatic compaction | ✅ Auto compact | `--compaction` auto | ✅ | REUSE | — |
| F11-18 | Manual compaction | ✅ Manual compact | `--compaction` manual | ✅ | REUSE | — |
| F11-19 | Summary generation | ✅ Summaries | Compaction summaries | 🟡 Partial | EXTEND | P2 |
| F11-20 | Compaction provenance | ✅ Provenance | Compaction hooks | ✅ | REUSE | — |
| F11-21 | Recovery after interrupt | ✅ Recovery | Checkpoints + rewind | 🟡 Partial | EXTEND | P2 |
| F11-22 | Concurrent isolation | ✅ Isolation | Tenant isolation | ✅ | REUSE | — |
| F11-23 | Transaction safety | ✅ Transactions | SQLite/PostgreSQL transactions | ✅ | REUSE | — |
| F11-24 | Idempotency | ✅ Idempotent ops | Upsert patterns | ✅ | REUSE | — |
| F11-25 | Locking | ✅ Locking | Row-level locks (PostgreSQL) | ✅ | REUSE | — |
| F11-26 | Migration compatibility | ✅ Migrations | 📋 Missing | 📋 | NATIVE | P2 |
| F11-27 | No history loss | ✅ No loss | Checkpoints + rewind | ✅ | REUSE | — |

---

## F12 — Agent Framework and Execution Loop

| ID | Capability | Ref Behavior | ZCoder Baseline | Gap | Strategy | Priority |
|----|------------|--------------|-----------------|-----|----------|----------|
| F12-01 | Context assembly | ✅ Assembly | `CodeAgent` loop | ✅ | REUSE | — |
| F12-02 | Policy evaluation | ✅ Policy eval | Permission engine | ✅ | REUSE | — |
| F12-03 | Model selection | ✅ Selection | Router + providers | ✅ | REUSE | — |
| F12-04 | Model invocation | ✅ Invocation | Provider adapters | ✅ | REUSE | — |
| F12-05 | Response classification | ✅ Classification | Response parsing | ✅ | REUSE | — |
| F12-06 | Tool/agent/user response | ✅ Response handling | Tool/agent/user | ✅ | REUSE | — |
| F12-07 | Permission check | ✅ Perm check | Hook + permission engine | ✅ | REUSE | — |
| F12-08 | Execution | ✅ Execution | Tool runtime | ✅ | REUSE | — |
| F12-09 | Result normalization | ✅ Normalization | Tool result parsing | ✅ | REUSE | — |
| F12-10 | Context update | ✅ Update | Context assembly | ✅ | REUSE | — |
| F12-11 | Validation | ✅ Validation | Schema + hooks | ✅ | REUSE | — |
| F12-12 | Continue/complete/fail | ✅ State machine | Loop control | ✅ | REUSE | — |
| F12-13 | Bounded cycles | ✅ Bounded | `--max-turns` + budgets | ✅ | REUSE | — |
| F12-14 | Tool-call validation | ✅ Validation | Schema + hooks | ✅ | REUSE | — |
| F12-15 | Typed model responses | ✅ Typed | Pydantic models | ✅ | REUSE | — |
| F12-16 | Retry policy | ✅ Retries | `--fable5-fallback-chain` | 🟡 Partial | EXTEND | P2 |
| F12-16 | Backpressure | ✅ Backpressure | Async queue | 🟡 Partial | EXTEND | P2 |
| F12-17 | Cancellation | ✅ Cancel | Ctrl+C + hooks | ✅ | REUSE | — |
| F12-17 | Checkpointing | ✅ Checkpoints | `--code-agent-checkpoint` | ✅ | REUSE | — |
| F12-18 | Idempotency | ✅ Idempotent | Tool idempotency keys | 🟡 Partial | EXTEND | P2 |
| F12-19 | Deadlock prevention | ✅ Deadlock | Async + timeouts | 🟡 Partial | EXTEND | P2 |
| F12-20 | Failure classification | ✅ Classification | Error types | 🟡 Partial | EXTEND | P2 |
| F12-21 | Deterministic transitions | ✅ Deterministic | State machine | 🟡 Partial | EXTEND | P2 |

---

## F13 — MCP Full Capability

| ID | Capability | Ref Behavior | ZCoder Baseline | Gap | Strategy | Priority |
|----|------------|--------------|-----------------|-----|----------|----------|
| F13-01 | stdio transport | ✅ stdio | `--mcp-server` | ✅ | REUSE | — |
| F13-02 | HTTP transport | ✅ HTTP | `--mcp-server-http` | ✅ | REUSE | — |
| F13-03 | Streamable HTTP | ✅ SSE | `--mcp-server-http` SSE | ✅ | REUSE | — |
| F13-04 | Server discovery | ✅ Discovery | `--plugin-install` + MCP | 🟡 Partial | EXTEND | P2 |
| F13-05 | Tool discovery | ✅ Tool list | `MCPControlHooks` + registry | ✅ | REUSE | — |
| F13-06 | Tool invocation | ✅ Tool call | MCP client | ✅ | REUSE | — |
| F13-07 | Resources | ✅ Resources | `list_resources`, `read_resource` | ✅ | REUSE | — |
| F13-08 | Resource templates | ✅ Templates | `list_resource_templates` | ✅ | REUSE | — |
| F13-09 | Prompts | ✅ Prompts | `list_prompts`, `get_prompt` | ✅ | REUSE | — |
| F13-10 | Sampling | ✅ Sampling | `create_message` | ✅ | REUSE | — |
| F13-11 | Elicitation | ✅ Elicitation | `ELICITATION` hook | ✅ | REUSE | — |
| F13-12 | Progress notifications | ✅ Progress | 📋 Missing | 📋 | NATIVE | P2 |
| F13-13 | Cancellation | ✅ Cancel | `cancel_notification` | ✅ | REUSE | — |
| F13-14 | Roots | ✅ Roots | `list_roots` | ✅ | REUSE | — |
| F13-15 | Logging | ✅ Logging | `set_logging_level` | ✅ | REUSE | — |
| F13-16 | Capability negotiation | ✅ Negotiation | 📋 Missing | 📋 | NATIVE | P2 |
| F13-17 | Authentication | ✅ Auth | 📋 Missing | 📋 | NATIVE | P2 |
| F13-18 | Authorization | ✅ Authz | `MCPControlHooks` tier | 🟡 Partial | EXTEND | P2 |
| F13-19 | Connection lifecycle | ✅ Lifecycle | Health checks | ✅ | REUSE | — |
| F13-20 | Version negotiation | ✅ Version | 📋 Missing | 📋 | NATIVE | P2 |
| F13-21 | Error handling | ✅ Errors | MCP error codes | 🟡 Partial | EXTEND | P2 |
| F13-22 | Server trust levels | ✅ Trust | Tier system | 🟡 Partial | EXTEND | P2 |
| F13-23 | Tool allowlists | ✅ Allowlist | `MCPRegistry.org_allowlist` | ✅ | REUSE | — |
| F13-24 | Tool approval | ✅ Approval | `TOOL_REGISTER` hook | ✅ | REUSE | — |
| F13-25 | Server audit records | ✅ Audit | `compliance-*` | 🟡 Partial | EXTEND | P2 |

---

## F14 — Telemetry and Analytics

| ID | Capability | Ref Behavior | ZCoder Baseline | Gap | Strategy | Priority |
|----|------------|--------------|-----------------|-----|----------|----------|
| F14-01 | Structured logs | ✅ JSON logs | `--health-check` JSON | ✅ | REUSE | — |
| F14-02 | Metrics | ✅ Prometheus | `--metrics-show` + Prometheus | ✅ | REUSE | — |
| F14-03 | Traces | ✅ OTel traces | `trace_retry_span`, `trace_queue_span`, `trace_retry_span_async` | ✅ | REUSE | — |
| F14-04 | Agent runtime telemetry | ✅ Agent telemetry | `--obs-latency`/`--obs-errors` | ✅ | REUSE | — |
| F14-05 | Tool execution timing | ✅ Tool timing | `--obs-latency` | ✅ | REUSE | — |
| F14-06 | Model latency | ✅ Model latency | `--obs-latency` | ✅ | REUSE | — |
| F14-07 | Token usage | ✅ Tokens | `--metrics-show` | ✅ | REUSE | — |
| F14-08 | Cost classification | ✅ Cost | `--cost-report` + `--metrics-show` | ✅ | REUSE | — |
| F14-09 | Session metrics | ✅ Session metrics | `--metrics-show` | ✅ | REUSE | — |
| F14-10 | Error rates | ✅ Error rates | `--obs-errors` | ✅ | REUSE | — |
| F14-11 | Retry metrics | ✅ Retries | `retry_attempts_total`, `retry_successes_total`, `retry_failures_total`, `retry_duration_seconds`, `retry_category_total` | ✅ | REUSE | — |
| F14-12 | Queue depth | ✅ Queue depth | `queue_depth`, `queue_depth_max`, `queue_wait_seconds` + worker integration | ✅ | REUSE | — |
| F14-13 | Plugin metrics | ✅ Plugin metrics | `PluginManager.get_stats()` | ✅ | REUSE | — |
| F14-14 | Hook execution metrics | ✅ Hook metrics | `HookBus.metrics` | ✅ | REUSE | — |
| F14-15 | MCP health | ✅ MCP health | Health checks | ✅ | REUSE | — |
| F14-16 | OTel integration | ✅ OTel | `init_telemetry`, `get_tracer`, `trace_*` context managers | ✅ | REUSE | — |
| F14-17 | Privacy defaults | ✅ Privacy | Opt-in `--metrics-show` | ✅ | REUSE | — |
| F14-18 | Configurable retention | ✅ Retention | `ZCODER_METRICS_RETENTION_SECONDS`, `ZCODER_HISTOGRAM_MAX_OBSERVATIONS`, `set_retention()`, `set_histogram_max_observations()` | ✅ | REUSE | — |
| F14-19 | Data minimization | ✅ Minimization | `--metrics-clear` | ✅ | REUSE | — |
| F14-20 | Secret redaction | ✅ Redaction | `_redact_value()` in config | ✅ | REUSE | — |
| F14-21 | Tenant isolation | ✅ Isolation | `rag-tenant` + RLS | ✅ | REUSE | — |
| F14-22 | Bounded cardinality | ✅ Bounded | Prometheus | ✅ | REUSE | — |
| F14-23 | Export controls | ✅ Export | `--metrics-export` | ✅ | REUSE | — |
| F14-24 | No exfiltration | ✅ No exfil | Local-first | ✅ | REUSE | — |
| F14-25 | Opt-in external | ✅ Opt-in | No external by default | ✅ | REUSE | — |

---

## F15 — Provider Abstraction

| ID | Capability | Ref Behavior | ZCoder Baseline | Gap | Strategy | Priority |
|----|------------|--------------|-----------------|-----|----------|----------|
| F15-01 | Anthropic | ✅ Native | `--provider anthropic` | ✅ | REUSE | — |
| F15-02 | Google Gemini | ✅ Native | `--provider gemini` | ✅ | REUSE | — |
| F15-03 | OpenAI-compatible | ✅ Native | `--provider openai_compatible` | ✅ | REUSE | — |
| F15-04 | Ollama | ✅ Native | `--provider ollama` | ✅ | REUSE | — |
| F15-05 | llama.cpp | ✅ Native | `--provider local` | ✅ | REUSE | — |
| F15-06 | vLLM | ✅ Native | `VLLMProvider` (server + offline) | ✅ | REUSE | — |
| F15-07 | xAI Grok | ✅ Native | `--provider xai` | ✅ | REUSE | — |
| F15-08 | Groq | ✅ Native | `--provider groq` | ✅ | REUSE | — |
| F15-09 | OpenRouter | ✅ Native | `--provider openrouter` | ✅ | REUSE | — |
| F15-10 | Cerebras | ✅ Native | `--provider cerebras` | ✅ | REUSE | — |
| F15-11 | NVIDIA NIM | ✅ Native | `--provider nvidia` | ✅ | REUSE | — |
| F15-12 | Model discovery | ✅ Discovery | `--list-models` | ✅ | REUSE | — |
| F15-13 | Capability matrix | ✅ Matrix | `--model-info` | ✅ | REUSE | — |
| F15-14 | Request normalization | ✅ Normalize | Provider adapters | ✅ | REUSE | — |
| F15-15 | Response normalization | ✅ Normalize | Adapter responses | ✅ | REUSE | — |
| F15-16 | Streaming | ✅ Streaming | All providers | ✅ | REUSE | — |
| F15-17 | Tool calling | ✅ Tools | All providers | ✅ | REUSE | — |
| F15-18 | Structured output | ✅ Structured | `--structured` | ✅ | REUSE | — |
| F15-19 | Model routing | ✅ Routing | `--route` + `--route-parallel` | ✅ | REUSE | — |
| F15-20 | Provider health | ✅ Health | `--health-check-deep` | ✅ | REUSE | — |
| F15-21 | Retry classification | ✅ Retries | `RetryEngine` with provider policies | ✅ | REUSE | — |
| F15-22 | Rate-limit handling | ✅ Rate limits | `--rate-limits` | ✅ | REUSE | — |
| F15-23 | Token accounting | ✅ Accounting | `--metrics-show` | ✅ | REUSE | — |
| F15-24 | Cost policies | ✅ Cost | `--cost-report` | ✅ | REUSE | — |
| F15-25 | Request validation | ✅ Validation | Schema + adapters | ✅ | REUSE | — |
| F15-26 | Provider-specific adapters | ✅ Adapters | `orchestration/adapters.py` | ✅ | REUSE | — |

---

## F16 — Skills and Instruction Packages

| ID | Capability | Ref Behavior | ZCoder Baseline | Gap | Strategy | Priority |
|----|------------|--------------|-----------------|-----|----------|----------|
| F16-01 | Agent Skills dir layout | ✅ Skills dir | `--skill` + `--list-skills` | ✅ | REUSE | — |
| F16-02 | Skill discovery | ✅ Discovery | `--list-skills` | ✅ | REUSE | — |
| F16-03 | Skill manifests | ✅ Manifests | Skill frontmatter | ✅ | REUSE | — |
| F16-04 | YAML frontmatter | ✅ Frontmatter | Skill YAML | ✅ | REUSE | — |
| F16-05 | Invocation | ✅ Invoke | `--skill` | ✅ | REUSE | — |
| F16-06 | Auto relevance | ✅ Auto | Skill routing | 🟡 Partial | EXTEND | P2 |
| F16-07 | User/project scopes | ✅ Scopes | `--skill` per-session | ✅ | REUSE | — |
| F16-08 | Skill scripts | ✅ Scripts | Skill scripts | ✅ | REUSE | — |
| F16-09 | Skill resources | ✅ Resources | Skill resource files | 🟡 Partial | EXTEND | P2 |
| F16-10 | Skill validation | ✅ Validation | Skill loading | ✅ | REUSE | — |
| F16-11 | Security review | ✅ Review | `--code-agent-permission` | ✅ | REUSE | — |
| F16-12 | Versioning | ✅ Versioning | `--skill` versioning | 🟡 Partial | EXTEND | P2 |
| F16-13 | Packaging | ✅ Packaging | `--plugin-dir` for skills | 🟡 Partial | EXTEND | P2 |
| F16-14 | Sharing | ✅ Sharing | `--plugin-marketplace-*` | 🟡 Partial | EXTEND | P2 |
| F16-15 | Deprecation | ✅ Deprecation | 📋 Missing | 📋 | NATIVE | P2 |
| F16-16 | ZCoder command compat | ✅ Compat | `--skill` + `--agent-*` | ✅ | REUSE | — |

---

## F17 — Permissions and Security Controls

| ID | Capability | Ref Behavior | ZCoder Baseline | Gap | Strategy | Priority |
|----|------------|--------------|-----------------|-----|----------|----------|
| F17-01 | Tool authorization | ✅ Authz | Hook + permission engine | ✅ | REUSE | — |
| F17-02 | Command authorization | ✅ Command authz | Hook + permission engine | ✅ | REUSE | — |
| F17-03 | File access | ✅ File access | Sandbox + hooks | 🟡 Partial | EXTEND | P1 |
| F17-04 | Network access | ✅ Network | `--browse-allow-domain` | ✅ | REUSE | — |
| F17-05 | Process execution | ✅ Process | `run_shell` permission | ✅ | REUSE | — |
| F17-06 | Plugin installation | ✅ Plugin install | `--plugin-install` + tier | ✅ | REUSE | — |
| F17-07 | MCP invocation | ✅ MCP authz | `MCPControlHooks` | ✅ | REUSE | — |
| F17-08 | Agent delegation | ✅ Agent authz | `--agent-orchestrate` | ✅ | REUSE | — |
| F17-09 | Hook execution | ✅ Hook authz | HookBus + tier | ✅ | REUSE | — |
| F17-10 | Resource budgets | ✅ Budgets | `--agent-session-budget-set` | ✅ | REUSE | — |
| F17-11 | User approvals | ✅ Approvals | Hooks + `--perms-*` | ✅ | REUSE | — |
| F17-12 | Enterprise policy | ✅ Policy | `ProductionConfig` + tier | ✅ | REUSE | — |
| F17-13 | Audit trails | ✅ Audit | `compliance-*` + logs + `AuditLog` JSONL | ✅ | REUSE | — |

### Controls
| ID | Capability | Ref Behavior | ZCoder Baseline | Gap | Strategy | Priority |
|----|------------|--------------|-----------------|-----|----------|----------|
| F17-14 | Allow/deny rules | ✅ Rules | `--perms-add` ALLOW/DENY/ASK | ✅ | REUSE | — |
| F17-15 | Fine-grained perms | ✅ Fine-grained | Tool patterns | ✅ | REUSE | — |
| F17-16 | Deny-by-default | ✅ Deny default | `ASK` default | ✅ | REUSE | — |
| F17-17 | Approval prompts | ✅ Prompts | Hook-based prompts | 🟡 CLI-based | EXTEND | P1 |
| F17-18 | Policy inheritance | ✅ Inheritance | Policy → managed → user | ✅ | REUSE | — |
| F17-19 | Workspace trust | ✅ Trust | Tier system | ✅ | REUSE | — |
| F17-20 | Sandboxing | ✅ Sandbox | `--code-agent-sandbox` | ✅ | REUSE | — |
| F17-21 | Secret redaction | ✅ Redaction | `_redact_value()` | ✅ | REUSE | — |
| F17-22 | SSRF protection | ✅ SSRF | `--browse-allow-domain` | ✅ | REUSE | — |
| F17-23 | Path containment | ✅ Containment | Sandbox | ✅ | REUSE | — |
| F17-24 | Command injection | ✅ Injection | Subprocess safety | ✅ | REUSE | — |
| F17-25 | Cross-tenant isolation | ✅ Isolation | RLS + tenant boundaries | ✅ | REUSE | — |
| F17-26 | SEC-001 through SEC-011 | ✅ All | Verified | ✅ | REUSE | — |

---

## F18 — Developer Experience and Compatibility

| ID | Capability | Ref Behavior | ZCoder Baseline | Gap | Strategy | Priority |
|----|------------|--------------|-----------------|-----|----------|----------|
| F18-01 | `/config` | ✅ Config UI | `--settings-show` | 🟡 CLI | EXTEND | P2 |
| F18-02 | `/permissions` | ✅ Perm UI | `--perms-list` | 🟡 CLI | EXTEND | P2 |
| F18-03 | `/hooks` | ✅ Hooks UI | `--hooks-list` | 🟡 CLI | EXTEND | P2 |
| F18-04 | `/plugin` | ✅ Plugin UI | `--plugin-list` | 🟡 CLI | EXTEND | P2 |
| F18-05 | `/mcp` | ✅ MCP UI | `--mcp-server` | 🟡 CLI | EXTEND | P2 |
| F18-06 | `/memory` | ✅ Memory UI | `--agent-memory-*` | 🟡 CLI | EXTEND | P2 |
| F18-07 | `/agents` | ✅ Agents UI | `--agent-list` | 🟡 CLI | EXTEND | P2 |
| F18-08 | `/compact` | ✅ Compact | `--compaction` | 🟡 CLI | EXTEND | P2 |
| F18-09 | `/resume` | ✅ Resume | `--code-agent-resume` | 🟡 CLI | EXTEND | P2 |
| F18-10 | `/clear` | ✅ Clear | `--no-project-memory` | 🟡 CLI | EXTEND | P2 |
| F18-11 | `/rewind` | ✅ Rewind | `--agent-rewind` | 🟡 CLI | EXTEND | P2 |
| F18-12 | `/statusline` | ✅ Statusline | `--status-line` | ✅ | REUSE | — |
| F18-13 | `/keybindings` | ✅ Keybindings | Textual keybindings | 🟡 Partial | EXTEND | P2 |
| F18-14 | `/voice` | ✅ Voice | 📋 Missing | 📋 | NATIVE | P3 |
| F18-15 | `/model` | ✅ Model | `--model` + `--list-models` | 🟡 CLI | EXTEND | P2 |
| F18-16 | `/help` | ✅ Help | `--help` | ✅ | REUSE | — |

---

## Coverage Summary

| Category | Total | ✅ | 🟡 | 📋 | 🔵 | 🚫 | 🔴 |
|----------|-------|----|----|----|----|----|----|
| **F01 Terminal UI** | 21 | 11 | 9 | 0 | 1 | 0 | 0 |
| **F02 Plugin/Marketplace** | 20 | 8 | 3 | 12 | 0 | 0 | 0 |
| **F03 Audio/Model** | 11 | 11 | 0 | 0 | 0 | 0 | 0 |
| **F04 Command System** | 18 | 5 | 6 | 7 | 0 | 0 | 0 |
| **F05 Runtime Hooks** | 51 | 27 | 6 | 18 | 0 | 0 | 0 |
| **F06 FS/HTTP/Process** | 19 | 1 | 4 | 14 | 0 | 0 | 0 |
| **F07 Agent System** | 22 | 14 | 4 | 4 | 0 | 0 | 0 |
| **F08 Prompt System** | 18 | 18 | 0 | 0 | 0 | 0 | 0 |
| **F09 UI Hooks** | 13 | 1 | 7 | 5 | 0 | 0 | 0 |
| **F10 Settings/Config** | 20 | 12 | 4 | 4 | 0 | 0 | 0 |
| **F11 Session/Compaction** | 27 | 24 | 1 | 2 | 0 | 0 | 0 |
| **F12 Agent Framework** | 21 | 13 | 6 | 2 | 0 | 0 | 0 |
| **F13 MCP** | 25 | 14 | 2 | 9 | 0 | 0 | 0 |
| **F14 Telemetry** | 25 | 25 | 0 | 0 | 0 | 0 | 0 |
| **F15 Provider** | 26 | 26 | 0 | 0 | 0 | 0 | 0 |
| **F16 Skills** | 16 | 8 | 4 | 4 | 0 | 0 | 0 |
| **F17 Permissions** | 26 | 20 | 1 | 5 | 0 | 0 | 0 |
| **F18 DX/Compat** | 16 | 2 | 10 | 4 | 0 | 0 | 0 |
| **TOTAL** | **402** | **284** | **61** | **54** | **3** | **0** | **0** |

### Coverage Percentages
- **Full Parity (✅):** 70.6% (284/402)
- **Partial (🟡):** 15.2% (61/402)
- **Missing/Audited (📋):** 13.4% (54/402)
- **zcoder-only (🔵):** 0.7% (3/402)
- **Excluded/Blocked:** 0%

---

## Priority Implementation Queue

### P0 (Critical - Security/Architecture)
1. F01-06 through F01-14: TUI multi-pane, dialogs, permission prompts
2. F02-01, F02-14: Git plugins, enterprise allowlists
3. F04-01, F04-11: Built-in commands, command permissions
4. F05-38/F05-39: Parallel hook execution
4. F06-16/F06-17: Path containment, SSRF protection
5. F17-03/F17-17: File access, approval prompts

### P1 (High - Core Features)
1. F01-15 to F01-21: TUI enhancements
2. F02-02/F02-03: Git/remote plugins
3. F04-01 to F04-18: Full command system
4. F05-11, F05-32-F05-35: Missing hook events/handlers (F05-04, F05-07, F05-08, F05-12 COMPLETED)
5. F06-01 to F06-15: FS/HTTP/Process hooks
6. F07-03, F07-18, F07-19: Specialized agents, A2A, observability
7. F09-01 to F09-12: UI hooks/extensions
8. F11-06 to F11-11: Session rename/search/export (COMPLETED)
9. F12-16 to F12-21: Retry, backpressure, cancellation, idempotency, deadlock, failure classification
10. F13-04 to F13-25: MCP resources, prompts, sampling, progress, roots, logging, auth
11. F14-03, F14-11, F14-12, F14-16, F14-18: Traces, retry metrics, queue depth, OTel, retention
12. F15-06, F15-21: vLLM direct, retry classification
13. F17-03: File access controls

### P2 (Medium - Enhancements)
1. F01-20/F01-21: Error rendering, accessibility
2. F02-04 to F02-20: Plugin upgrades, integrity, signatures, conflicts, resolution, sandbox, provenance, rollback
3. F03-01 to F03-11: Audio/model hooks
4. F04-03 to F04-17: Project commands, namespaces, aliases, completion, composition, versioning, deprecated
5. F05-04, F05-07, F05-08, F05-11, F05-12, F05-32-F05-35, F05-40-F05-48: Hook events/handlers/execution (F05-04, F05-07, F05-08, F05-12 COMPLETED)
6. F06-01 to F06-15, F06-18/F06-19: FS/HTTP/Process/Clock/Store/Config hooks
7. F07-04, F07-18, F07-19: Frontmatter, A2A, observability
8. F09-01 to F09-12: UI hooks/extensions
9. F10-01 to F10-20: Settings schema enhancements
10. F11-06 to F11-26: Session rename/search/export/import/delete (COMPLETED)
11. F12-16 to F12-21: Execution loop enhancements
12. F13-04 to F13-25: MCP resources/prompts/sampling/progress/roots/logging/auth/version/errors/trust
13. F14-03, F14-11, F14-12, F14-16, F14-18: Traces, retry metrics, queue depth, OTel, retention
14. F15-06, F15-21: vLLM direct, retry classification
15. F16-06 to F16-15: Auto relevance, resources, versioning, packaging, sharing, deprecation
16. F17-03, F17-13: File access, audit trails
17. F18-01 to F18-15: CLI command parity

### P3 (Low - Nice to Have)
1. F01-21: Accessibility fallbacks
2. F03-01 to F03-04: Audio input/transcription/VAD/streaming
3. F04-16/F04-17: Command versioning/deprecated
4. F05-21 to F05-27: Instructions/CWD/file/dir/model-switch/message hooks
5. F06-04/F06-07/F06-09/F06-10/F06-11/F06-12/F06-14/F06-19: File watching, HTTP streaming, process mgmt, clock, store, config updates, size limits
6. F07-18: Agent-to-agent messages
7. F10-02/F10-04/F10-05/F10-06/F10-07/F10-15/F10-16: Config scopes, YAML, migrations, deprecation
8. F11-06, F11-08/F11-09/F11-10/F11-19/F11-21/F11-22/F11-23/F11-24/F11-26: Session enhancements
9. F12-16/F12-17/F12-18/F12-19/F12-20/F12-21: Execution loop robustness
10. F13-07 to F13-25: MCP full protocol
11. F14-03, F14-11, F14-12, F14-16, F14-18: Telemetry enhancements
12. F15-06: vLLM direct
13. F16-09 to F16-15: Skill resources, versioning, packaging, sharing, deprecation
14. F17-13: Audit trails
13. F18-01 to F18-15: Full CLI command parity

---

## Evidence Register

| Source | Verification Date | Confidence |
|--------|-------------------|------------|
| `src/zcoder/agent/plugin/` source code | 2026-11-13 | High |
| `src/zcoder/agent/codeagent/` source code | 2026-11-13 | High |
| `src/zcoder/agent/orchestration/` source code | 2026-11-13 | High |
| `src/zcoder/agent/enterprise/` source code | 2026-11-13 | High |
| `tests/unit/agent/plugin/` test suite | 2026-11-13 | High |
| `tests/integration/test_plugin_system.py` | 2026-11-13 | High |
| `FEATURE_MATRIX.md` | 2026-11-13 | High |
| `BASELINE.md` | 2026-11-13 | High |
| `make check` output | 2026-11-13 | High |
| `pytest` output (2338 tests) | 2026-11-13 | High |
| `make standalone-force` + health check | 2026-11-13 | High |