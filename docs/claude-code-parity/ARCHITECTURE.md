# ZCoder Architecture for Claude Code Parity

**Version:** 1.60.0  
**Date:** 2026-11-13  
**Reference:** FEATURE-PARITY-MATRIX.md, BASELINE.md

---

## 1. Architectural Principles

### Core Philosophy
- **Preserve ZCoder's native Python architecture** — no TypeScript/Node.js runtime
- **Local-first, zero-cost inference** — llama.cpp/Ollama/vLLM on loopback
- **Enterprise-grade security** — SEC-001 through SEC-011, deny-by-default
- **Clean Architecture** — Dependency direction: Domain → Services → Interfaces → Infrastructure
- **Provider-neutral** — 9+ LLM providers behind unified abstraction

### Non-Goals
- ❌ Do not port Claude Code TypeScript line-by-line
- ❌ Do not introduce Node.js runtime
- ❌ Do not replace existing ZCoder subsystems (TUI, GUI, Web, API, DB)
- ❌ Do not silently fall back to paid providers

---

## 2. Current Architecture Map

```
┌─────────────────────────────────────────────────────────────────┐
│                    INTERFACES LAYER                              │
├─────────────┬─────────┬──────────┬─────────────┬───────────────┤
│    CLI      │   TUI   │   GUI    │  Web Console │   REST API    │
│ (argparse)  │(Textual)│ (Native) │  (FastAPI)   │  (FastAPI)    │
└──────┬──────┴────┬────┴────┬─────┴──────┬──────┴──────┬────────┘
       │           │         │            │             │
       ▼           ▼         ▼            ▼             ▼
┌─────────────────────────────────────────────────────────────────┐
│                  APPLICATION SERVICES LAYER                      │
├─────────────┬──────────────┬──────────┬────────────────────────┤
│ Agent       │ Session      │ Tool     │ Hook        │ Command  │
│ Orchestrator│ Manager      │ Runtime  │ Engine      │ Registry │
├─────────────┼──────────────┼──────────┼─────────────┼──────────┤
│ Prompt      │ Permission   │ Plugin   │ UI State    │ Skill    │
│ Engine      │ Engine       │ Manager  │ Manager     │ Engine   │
└──────┬──────┴──────┬──────┴──────┬────┴────────┬─────┴────────┘
       │             │             │             │
       ▼             ▼             ▼             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      DOMAIN / CORE LAYER                         │
├─────────────┬──────────────┬──────────┬────────────────────────┤
│ Agents      │ Sessions     │ Perms    │ Policies   │ Tool       │
│             │              │          │            │ Contracts  │
├─────────────┼──────────────┼──────────┼────────────┼────────────┤
│ Plugin      │ Lifecycle    │ Model    │ Cost       │ Security   │
│ Contracts   │ Events       │ Routing  │ Classification          │
└──────┬──────┴──────┬──────┴──────┬────┴────────┬────┴──────────┘
       │             │             │             │
       ▼             ▼             ▼             ▼
┌─────────────────────────────────────────────────────────────────┐
│                  INFRASTRUCTURE ADAPTERS                         │
├─────────────┬──────────────┬──────────┬────────────────────────┤
│ SQLite      │ PostgreSQL   │ Filesys  │ Process    │ HTTP       │
│ (local)     │ (enterprise) │ tem      │ Runtime    │ Runtime    │
├─────────────┼──────────────┼──────────┼────────────┼────────────┤
│ Clock       │ Secret Store │ MCP      │ LLM        │ Telemetry  │
│             │              │ (stdio+HTTP)│ Providers │ (Prom+OTel)│
└─────────────┴──────────────┴──────────┴────────────┴────────────┘
```

---

## 3. Key Existing Components

### Plugin System (Phases 1-2 Complete)
```
src/zcoder/agent/plugin/
├── tier.py              # PluginTier enum (PREPEND/USER/APPEND/BUILTIN)
├── manifest.py          # PluginManifest (Pydantic)
├── loader.py            # PluginLoader (discovery + loading)
├── manager.py           # PluginManager (tier ordering + hook/tool/command access)
├── events.py            # HookEvent (StrEnum, 50+ events)
├── hook_bus.py          # HookBus (tier precedence + deny-rules-hold)
├── ui_hooks.py          # DiffPane, UIPaneManager
├── mcp_control.py       # MCPRegistry, tier filtering
├── telemetry.py         # TelemetryPlugin (log/mark with tier gate)
├── settings_policy.py   # SettingsPolicyReader (fail-closed)
├── pinned_env.py        # PinnedEnvManager (19 always-pinned)
├── compaction.py        # CompactionHooks
├── prompt_compose.py    # PromptCompositionHooks
├── performance.py       # LazyPluginManager, OptimizedHookBus
└── __init__.py
```

### Hook System (Phase 2-3 Complete)
- **HookBus**: Tier-precedence event dispatch with deny-rules-hold double-dispatch
- **50+ HookEvent types**: Session, Prompt, Tool, Agent, Command, UI, MCP, Telemetry, Classic
- **BLOCKING_EVENTS**: Events that can block (PreToolUse, UserPromptSubmit, etc.)
- **ORG_CONTROLLED_EVENTS**: Events that continue past user tier
- **Deny-rules-hold**: Double-dispatch ensures org deny rules override user plugins

### Plugin Manager Features
- Tier-precedence ordering: PREPEND (0) > USER (1) > APPEND (2) > BUILTIN (3)
- Lazy loading with `LazyPluginManager` + async initialization
- Hook caching with `OptimizedHookBus` (metrics: dispatch count, time, cache hit rate)
- Tier-filtered tool/command/MCP server access

### CodeAgent (Claude Code Compatible)
```
src/zcoder/agent/codeagent/
├── loop.py              # Main agent loop (bounded cycles)
├── tools.py             # Tool implementations (Read, Write, Edit, Bash, etc.)
├── hooks.py             # Classic hooks (PreToolUse, PostToolUse, etc.)
├── permissions.py       # Permission engine (Allow/Deny/Ask)
├── sessions.py          # Session persistence (SQLite/PostgreSQL)
├── mcp_client.py        # MCP client integration
├── skills.py            # Skills system
├── subagents.py         # Subagent spawning
├── sandbox.py           # Filesystem/network sandbox
├── commands.py          # Slash commands
├── memory.py            # Memory system
└── factory.py           # Agent factory
```

### Enterprise Security (SEC-001 through SEC-011)
- **SEC-001**: Secret management (file-based, never in .env)
- **SEC-002**: Input validation (Pydantic + schema)
- **SEC-003**: Authentication (WIF, OIDC, JWT)
- **SEC-004**: Authorization (RBAC + tier system)
- **SEC-005**: Audit logging (compliance-* commands)
- **SEC-006**: Encryption (TLS + secret redaction)
- **SEC-007**: Multi-tenancy (RLS + tenant boundaries)
- **SEC-008**: Environment isolation (no credential inheritance)
- **SEC-009**: Supply chain (signed commits, SBOM)
- **SEC-010**: DR/Backup (zPITR, pg_dump, restore drills)
- **SEC-011**: Observability security (redacted logs)

### Multi-Provider Routing
| Provider | Flag | Models |
|----------|------|--------|
| Anthropic | `--provider anthropic` | Opus/Sonnet/Haiku |
| Google Gemini | `--provider gemini` | Gemini 1.5/2.0 |
| OpenAI Compatible | `--provider openai_compatible` | Any OpenAI API |
| Ollama | `--provider ollama` | Local models |
| Local (llama.cpp) | `--provider local` | GGUF on loopback |
| xAI Grok | `--provider xai` | Grok |
| Groq | `--provider groq` | Fast inference |
| OpenRouter | `--provider openrouter` | 100+ models |
| Cerebras | `--provider cerebras` | Fast inference |
| NVIDIA NIM | `--provider nvidia` | Multi-model |

---

## 4. Implementation Strategy for Gaps

### Decision Model per Feature

| Decision | When to Use |
|----------|-------------|
| **REUSE** | Existing implementation satisfies contract |
| **EXTEND** | Existing implementation sound but incomplete |
| **ADAPTER** | External protocol/compatibility layer needed |
| **NATIVE** | New Python-native subsystem required |
| **EXTERNAL** | Requires separately deployed service |
| **EXCLUDED** | Proprietary/platform-specific |
| **BLOCKED** | Verified dependency prevents implementation |

### Priority Ordering
1. **P0** — Security/Architecture (deny-by-default, SSRF, path containment)
2. **P1** — Core Features (commands, hooks, file access, approval prompts)
3. **P2** — Enhancements (UI hooks, MCP resources, session management)
4. **P3** — Nice-to-have (audio, voice, accessibility)

### Implementation Approach
1. **Audit** — Verify reference behavior from official docs
2. **Inspect** — Check existing ZCoder implementation
3. **Design** — Document strategy, contracts, tests
4. **Implement** — Minimal, focused changes
5. **Test** — Unit + integration + security regression
6. **Verify** — Run full test suite + quality gates
7. **Document** — Update parity matrix, docs, config examples

---

## 5. Extension Points for New Features

### Adding New Hook Events
```python
# 1. Add to src/zcoder/agent/plugin/events.py
class HookEvent(StrEnum):
    NEW_EVENT = "new.event"
    # ...

# 2. Add to BLOCKING_EVENTS or ORG_CONTROLLED_EVENTS if needed
BLOCKING_EVENTS = frozenset({..., HookEvent.NEW_EVENT})

# 3. Add convenience method to HookBus
async def new_event(self, context: HookContext) -> HookResult:
    return await self.fire(HookContext(event=HookEvent.NEW_EVENT, ...))
```

### Adding New Plugin Tier
```python
# In tier.py - NOT RECOMMENDED (breaks precedence)
# Instead use existing tiers with manifest configuration
```

### Adding New Provider
```python
# 1. Create adapter in src/zcoder/agent/orchestration/adapters.py
class NewProviderAdapter(BaseProviderAdapter):
    async def complete(self, request): ...
    async def stream(self, request): ...

# 2. Register in orchestration/providers.py
PROVIDER_ADAPTERS["new_provider"] = NewProviderAdapter

# 3. Add to CLI choices in main.py
```

### Adding New Hook Handler Type
```python
# In hook_bus.py _run_hook method
# Add detection for new handler type and execution logic
```

---

## 6. Data Flow for Key Operations

### Hook Execution Flow
```
CLI/TUI/GUI/API Request
        │
        ▼
HookBus.fire(HookContext)
        │
        ├── Get all hooks for event (cached, tier-sorted)
        │
        ├── For each hook (tier order):
        │   ├── Build sanitized payload
        │   ├── Check if LoadedHook (plugin) or callable (builtin)
        │   ├── Plugin: subprocess with sanitized env
        │   ├── Builtin: direct async call
        │   ├── Collect HookResult
        │   ├── If blocked & blocking event → stop
        │
        ├── Deny-rules-hold: if user-tier rewrote block
        │   ├── Re-run without user tier
        │   ├── If org still blocks → org decision stands
        │
        └── Return aggregated HookResult
```

### Agent Loop Flow
```
User Request
     │
     ▼
Context Assembly (history + tools + skills + memory)
     │
     ▼
Policy Evaluation (permissions + budgets + tenant)
     │
     ▼
Model Selection (router: --route, --route-parallel, or explicit)
     │
     ▼
Model Invocation (provider adapter + streaming)
     │
     ▼
Response Classification (tool call / text / structured)
     │
     ▼
Permission Check (HookBus + PermissionEngine)
     │
     ▼
Execution (Tool Runtime / Subagent / User)
     │
     ▼
Result Normalization (schema + hook post-processing)
     │
     ▼
Context Update (history + checkpoints + memory)
     │
     ▼
Validation (schema + hooks + budgets)
     │
     ▼
Continue / Complete / Fail
```

### Plugin Loading Flow
```
PluginManager.load_all()
     │
     ▼
PluginLoader.discover_plugins()
     │
     ├── ~/.zcoder/plugins/
     ├── /usr/local/share/zcoder/plugins/
     ├── /opt/zcoder/plugins/
     └── builtin (src/zcoder/plugins/)
     │
     ▼
For each plugin dir:
     ├── Load manifest.json (Pydantic validation)
     ├── Add dir to sys.path
     ├── Load hooks.py → HookConfig → LoadedHook
     ├── Load tools.py → ToolConfig → LoadedTool
     ├── Load commands.py → CommandConfig → LoadedCommand
     ├── Load MCP servers from manifest
     │
     ▼
Register by tier (PREPEND/USER/APPEND/BUILTIN)
     │
     ▼
Build hook cache, tool registry, command registry
```

---

## 7. Security Boundaries

### Tier Precedence Security Model
```
PREPEND (0)     → Organization prepend (outermost, highest privilege)
USER (1)        → User-installed plugins
APPEND (2)      → Organization append
BUILTIN (3)     → Built-in plugins (innermost, lowest privilege)
```

### Hook Execution Security
- **Environment sanitization**: Only `_SAFE_ENV` vars passed to hooks
- **Subprocess isolation**: Each hook runs in separate process
- **Timeout enforcement**: Per-hook configurable timeout (default 30s, max 300s)
- **Deny-rules-hold**: Double-dispatch prevents user-tier override of org deny rules

### Plugin Trust Model
- **PREPEND/APPEND/BUILTIN**: Organization-controlled, full trust
- **USER**: User-installed, restricted by org allowlists
- **MCP Servers**: Tier-filtered registration via `MCPRegistry`

### Data Isolation
- **SQLite**: Single-user, file-per-user
- **PostgreSQL**: RLS + tenant boundaries (`rag-tenant`, `SEC-007`)
- **Multi-tenancy**: Enterprise config with `tenant_id` on all domain objects

---

## 8. Testing Strategy

### Test Layers
| Layer | Scope | Tools |
|-------|-------|-------|
| Unit | Individual functions/classes | pytest + mocks |
| Contract | Interface compliance | pytest + hypothesis |
| Integration | Cross-component | pytest + PostgreSQL |
| Security | Threat modeling | bandit + custom |
| E2E | Full workflows | pytest + CLI |

### Required Test Cases per Feature
- Happy path
- Malformed input
- Missing permissions
- Malicious paths
- Untrusted plugin packages
- Malicious hook outputs
- HTTP redirects/SSRF
- Timeouts/cancellation
- Duplicate execution
- Interrupted persistence
- Concurrent updates
- Database failures
- Provider rate limiting
- Token budget exhaustion
- Cross-tenant access attempts

---

## 9. Migration & Compatibility

### Database Migrations
- SQLite: Default for local/single-user
- PostgreSQL: Enterprise, managed via `scripts/local_postgres.py`
- Every schema change requires: migration + rollback + index analysis + transaction safety

### Backward Compatibility
- CLI flags: Additive only, never remove
- Config: New fields optional with defaults
- Hooks: New events additive, existing events unchanged
- Plugin API: Manifest v1 supported, v2 additive

---

## 10. Open Questions / Decisions Needed

| Question | Status | Impact |
|----------|--------|--------|
| Full MCP Resources/Prompts support? | 📋 Planning | P2 |
| HTTP/Webhook hook handlers? | 📋 Planning | P2 |
| Parallel hook execution? | 📋 Planning | P2 |
| Audio/Voice support? | 📋 Excluded (P3) | P3 |
| Project-defined commands (`.zcoder/commands`)? | 📋 Planning | P2 |
| Workspace/directory config scopes? | 📋 Planning | P2 |
| Config migration system? | 📋 Planning | P2 |
| OTel traces full integration? | 📋 Partial | P2 |

---

## 10. Next Implementation Phase

Based on priority queue in FEATURE-PARITY-MATRIX.md:

**Immediate (P0):**
1. F06-16/F06-17: Path containment + SSRF protection (security)
2. F04-01/F04-11: Built-in commands + command permissions
3. F04-17: Approval prompts (UI)

**Next (P1):**
1. F02-01/F02-14: Git plugins + enterprise allowlists
2. F04-02 to F04-18: Full command system
3. F05 missing events: UserPromptExpansion, PostToolUseFailure, PostToolBatch, StopFailure, etc.
4. F06: FS/HTTP/Process/Clock/Store hooks
5. F07-18/F07-19: Agent-to-agent, execution observability
6. F13: MCP Resources/Prompts/Sampling/Progress/Roots/Logging/Auth

---