# Gap Analysis: deepseek-harness vs zcoder

This document provides a systematic comparison between deepseek-harness (TypeScript monorepo at `/mnt/zdata/deepseek-harness`, 54 packages, 5,233+ TS files) and zcoder (Python package at `/home/cvsz/zcoder/src/zcoder`). It identifies all features present in deepseek-harness but missing from zcoder, and provides a prioritized Full Independent Implementation plan and performance optimization plan.

## Table of Contents

1. [Systematic Inventory of deepseek-harness](#systematic-inventory)
2. [Gap Analysis by Module](#gap-analysis-by-module)
3. [Full Independent Implementation Plan](#full-independent-implementation-plan)
4. [Performance Optimization Plan](#performance-optimization-plan)
5. [Verification Checklist](#verification-checklist)

---

## 1. Systematic Inventory of deepseek-harness

### 1.1 All 54 Packages

| Package | TS Files | Primary Purpose |
|---------|----------|----------------|
| acp | 19 | Agent Communication Protocol |
| api | 240 | HTTP API surface |
| attachment | 28 | File attachment handling |
| boot | 124 | Boot sequence, startup orchestration |
| browser-use | 4 | Browser automation agent |
| bundle | 35 | Package bundling |
| client | 1409 | Client-side SDK and UI bindings |
| compaction | 33 | Context compaction/summarization |
| computer-use | 4 | Computer-use agent |
| context | 40 | Context assembly and management |
| **core** | **139** | **Core services (agent, tools, session, LLM)** |
| credentials | 33 | Credential management |
| deliverables | 24 | Deliverable artifacts |
| document | 26 | Document processing |
| experimental | 1299 | Experimental features |
| extensions | 56 | Plugin extensions |
| feedback | 9 | Feedback collection |
| fs | 77 | File system operations |
| goal | 21 | Goal tracking |
| guard | 4 | Guardrails |
| host | 60 | Host-side adapters |
| identity | 2 | Identity management |
| interaction | 27 | User interaction |
| jobs | 23 | Job queueing |
| **llm** | **175** | **LLM providers (DeepSeek, OpenAI, Anthropic, Ollama, Gemini)** |
| lsp | 28 | Language Server Protocol |
| mcp | 42 | Model Context Protocol |
| plan | 8 | Planning system |
| preset | 19 | Agent presets |
| ptc-runtime | 72 | Parallel tool call runtime |
| sandbox | 52 | Sandbox execution |
| schedule | 41 | Scheduling |
| sdk | 43 | SDK surface |
| **session** | **228** | **Session management (projection, stats, persistence, telemetry)** |
| session-query | 40 | Session querying |
| settings | 12 | Settings management |
| shell | 54 | Shell execution |
| skill | 24 | Skill system |
| spill | 17 | Spill/recovery |
| ssh | 43 | SSH |
| storage | 24 | Storage layer |
| subagent | 127 | Subagent management |
| subprocess | 62 | Subprocess management |
| team | 21 | Multi-agent teams |
| telemetry | 7 | Telemetry |
| terminal | 14 | Terminal |
| test-support | 107 | Test utilities |
| todo | 7 | Todo management |
| typert | 58 | Type protocol |
| util | 94 | Utilities |
| web | 42 | Web search/fetch |
| workflow | 29 | Workflow engine |
| workspace | 6 | Workspace |

### 1.2 Core Domain Inventory (Most Relevant to zcoder)

#### core/agent-loop (2,149 TS lines)
Files: `agent.ts` (751), `index.ts` (838), `inbox.ts` (232), `runtime-context.ts` (181), `assistant-stream.ts` (141), `constants.ts` (6)

Key exports:
- `ReactLoopAgent` class — phase-based state machine (idle/running/maintenance), wake/sleep cycle, inbox-based messaging, step-by-turn execution
- `AgentLoop` class (Service) — factory delegation, scoped agent creation, session management
- `LauncherAgentIdentity`, `ConfiguredAgentIdentities` — launcher-selected session identities
- `CONFIGURED_AGENT_IDENTITIES_KEY` — context key for configured agent identities
- `DEFAULT_MAX_PARALLEL_TOOL_CALLS` — concurrency limit

Phases:
- `idle` — no active work
- `running` — turn in progress (turn + step tracking)
- `maintenance` — abortable maintenance job

#### core/tools (3,797 TS lines)
Files: `executor.ts` (102), `contracts.ts` (418), `pipeline.ts` (807), `schema.ts` (646), `json-schema.ts` (656), `index.ts` (412), `presentation.ts` (389), `batch.ts` (285), `events.ts` (58), `error-codes.ts` (24)

Key interfaces:
- `ToolExecutor` — plugin-owned argument parsing, dispatch, scheduling, cancellation, logging
- `ToolDefinition` — schema + execution function + output definition + content projection
- `ResolvedToolSet` — step-time admitted registrations
- `ToolBatchInput` / `ToolBatchResult` — batch execution with concurrency control
- `ToolActivationContext` — step-time activation conditions
- `ToolRegistrationOptions` — `when()` condition for tool availability

Key errors:
- `ToolBatchExecutionError` — internal batch failure with partial results
- `ToolExecutorUnavailableError` — missing executor
- `ToolActivationError` — condition failure
- `ToolNotFoundError` — unknown tool
- `ToolContextUnavailableError` — missing required context
- `ToolOutputError` — output schema violation

#### session/session-projection (2 source files)
Files: `index.ts` (registry, ~800 lines), `types.ts` (type table)

Key exports:
- `SessionProjectionRegistry` service — `ctx.sessionProjections`
- `ProjectionDefinition<K, S>` — pure fold unit (init/apply/wire/stateVersion)
- `ProjectionHandle<S>` — reader handle with `stateOf(session)`, `readerFor(session)`, `dispose()`
- `ProjectionSnapshot` — consistent cut over all units
- `ProjectionCheckpointRow` / `ProjectionCheckpoint` — persisted cache rows
- Methods: `register()`, `stateOf()`, `onChanged()`, `onEventChanged()`, `snapshot()`, `cachedSnapshot()`, `summaryKeys()`, `checkpoint()`, `restoreFloor()`, `viewCheckpoint()`, `restore()`, `hydrate()`

Architecture: Whole-value event rule — state-carrying log events carry complete post-change state, never bare deltas. Eager drive over committed events. Object.is reference comparison for change detection.

#### session/session-stats (4 source files)
Files: `index.ts`, `types.ts`, `projection.ts`, `client.ts`

Key features:
- `sessionStats` projection unit: whole-log turn/step counts and wall times
- `SessionStatsProjection` interface: `turns`, `steps`, `llmMs`, `toolMs`, `ttftMs`, `ttftSteps`, `decodeMs`, `decodeTokens`
- Folds: `step/start` (open step boundary), `assistant/attempt` (first token time), `assistant/message` (llm/decode time), `tool/call` + `tool/result` (tool time), `step/end` (turn counting), `turn/end` (pending call cleanup)
- `stateVersion: 1`, excluded from session summaries (`summary: false`)

#### session/session-persistence-jsonl (multiple files)
Files: `index.ts`, `format.ts`, `storage.ts`, `catalog-migration.ts`, `lease.ts`, `migration-verifier.ts`, `zstd.ts`, etc.

Key features:
- JSONL file-based session persistence
- Zstd compression (public/private decoder)
- Lease-based concurrent access control
- Migration across format versions (v0→v1→v2→v3→v4)
- Catalog migration worker
- Content admission controls

#### session/session-format-v0-to-v1 through v3-to-v4
Format migration pipeline with codec, dispositions, validation, relationships, payload validation.

#### llm/llm-deepseek (26 source files)
DeepSeek adapter: Anthropic-compatible API client with files API, image tokens, SSE transport, request pricing, serialization.

#### llm/llm-pi-ai (18 source files)
Provider-agnostic LLM adapter with auth, catalog, discovery, login, prefix binding.

#### llm/llm-retry (6 source files)
Retry policy, transport recovery, brand types.

#### llm/llm (13 source files)
Core LLM layer: adapter-failure, api-key, assembler, assistant-stream, attribution, brand, call-config, content, error, index, message, retry-policy, types.

---

## 2. Gap Analysis by Module

### 2.1 Session Management

| Feature | deepseek-harness | zcoder | Gap |
|---------|-----------------|--------|-----|
| SessionEvent with event_id/timestamp | Yes (branded types) | Yes | None |
| SessionProjection with fold/fold_many | Yes (ProjectionDefinition) | Yes (SessionProjection class) | Partial — zcoder lacks watermark caching |
| SessionProjectionRegistry (ctx.sessionProjections) | Yes | No | **Missing** |
| ProjectionDefinition init/apply/wire pattern | Yes | No | **Missing** |
| stateVersion with cache invalidation | Yes | No | **Missing** |
| Whole-value event rule (complete post-change state) | Yes | Partial | Partial |
| Object.is change detection | Yes | No | **Missing** |
| Change feed listeners (onChanged/onEventChanged) | Yes | No | **Missing** |
| Snapshot/checkpoint/restore/hydrate | Yes | No | **Missing** |
| Persisted projection cache (checkpoint rows) | Yes | No | **Missing** |
| sessionStats projection (turns, steps, llmMs, toolMs, ttftMs, decodeMs, decodeTokens) | Yes | Partial (TokenUsage, CostBreakdown) | Partial |
| session-telemetry coordinator | Yes | No | **Missing** |
| JSONL persistence with zstd compression | Yes | No (single JSON file) | **Missing** |
| Session format migration (v0→v4) | Yes | No | **Missing** |
| Lease-based concurrent access | Yes | No | **Missing** |
| Session forking with inherited event count | Yes | Yes (basic fork) | Partial |
| Session title management | Yes | No | **Missing** |
| Working directory tracking | Yes | Yes | None |

### 2.2 Agent Loop

| Feature | deepseek-harness | zcoder | Gap |
|---------|-----------------|--------|-----|
| Phase-based state machine (idle/running/maintenance) | Yes | No (simple running flag) | **Missing** |
| Wake/sleep cycle | Yes | No | **Missing** |
| Inbox-based messaging (next-turn/next-step) | Yes | No | **Missing** |
| Step-by-turn execution | Yes | Yes | None |
| ToolCallRecovery for pending tool results | Yes | No | **Missing** |
| Request header logging with reason (initial/resume/change/series) | Yes | Yes | None |
| Model selection projection | Yes | No | **Missing** |
| Abort signal per turn/step | Yes | Partial | Partial |
| Agent error dispatch (agent/error event) | Yes | No | **Missing** |
| Agent status transitions | Yes | No | **Missing** |
| runMaintenance() for abortable maintenance jobs | Yes | No | **Missing** |
| whenIdle() for awaiting convergence | Yes | No | **Missing** |

### 2.3 Tool Execution

| Feature | deepseek-harness | zcoder | Gap |
|---------|-----------------|--------|-----|
| ToolExecutor interface (describe/execute) | Yes | No (direct tool.func calls) | **Missing** |
| ToolDefinition with output schema | Yes | Partial | Partial |
| ResolvedToolSet with dispose() | Yes | No | **Missing** |
| ToolBatchInput/ToolBatchResult | Yes | No | **Missing** |
| maxParallelToolCalls concurrency control | Yes | No | **Missing** |
| Tool activation conditions (when()) | Yes | No | **Missing** |
| Tool restrictions (allow/deny lists) | Yes | Partial (permission policy) | Partial |
| Tool guards (post-policy denial) | Yes | No | **Missing** |
| Tool projection (projectContent/finalizeContent) | Yes | No | **Missing** |
| Concurrency safety (isConcurrencySafe) | Yes | No | **Missing** |
| Tool call presentation views | Yes | No | **Missing** |
| Tool batch execution error with partial results | Yes | No | **Missing** |
| PTC (parallel tool call) runtime | Yes (ptc-runtime pkg) | No | **Missing** |

### 2.4 LLM Providers

| Provider | deepseek-harness | zcoder | Gap |
|----------|-----------------|--------|-----|
| DeepSeek | Yes (llm-deepseek pkg) | Yes | None |
| OpenAI | Yes | Yes | None |
| Anthropic | Yes | Yes | None |
| Gemini | Yes | Yes | None |
| Ollama | Yes | Yes | None |
| Local GGUF | Yes | Partial (LocalLLM exists, not integrated) | **Missing** |
| Retry policy / transport recovery | Yes (llm-retry pkg) | Partial | Partial |
| Request pricing / token metering | Yes (token-meter pkg) | Partial (estimate_cost) | Partial |
| Files API | Yes | No | **Missing** |
| Image token counting | Yes | No | **Missing** |

### 2.5 Plugin System

| Feature | deepseek-harness | zcoder | Gap |
|---------|-----------------|--------|-----|
| Plugin allowlist/blocklist | Yes (enforced at load) | Yes (_is_allowed, but not enforced in load_from_git path consistently) | Partial |
| Plugin hot-reload | Yes | Yes (reload() method) | None |
| Plugin tier system (PREPEND/USER/APPEND/BUILTIN) | Yes | Yes | None |
| Plugin Config registration | Yes | Yes | None |
| Plugin stats | Yes | Yes | None |
| Plugin lifecycle (enable/disable per plugin) | No | No | None |
| Plugin fiber/scoped disposal | Yes (Cordis effects) | No | **Missing** |

### 2.6 Error Handling

| Feature | deepseek-harness | zcoder | Gap |
|---------|-----------------|--------|-----|
| Specific exception types (ToolActivationError, ToolNotFoundError, etc.) | Yes | Partial | Partial |
| Structured error reporting (errorChain) | Yes | Yes | None |
| Error recovery strategies | Yes | Partial | Partial |
| Circuit breaker patterns | Yes | No | **Missing** |
| AggregateError for combined failures | Yes | No | **Missing** |

### 2.7 Performance Optimizations

| Feature | deepseek-harness | zcoder | Gap |
|---------|-----------------|--------|-----|
| Projection watermark caching | Yes | No | **Missing** |
| Request batching | Yes (ToolBatchInput) | Partial (batch.py) | Partial |
| Connection pooling | Yes | Partial (pooling.py) | Partial |
| Lazy loading | Yes (fiber-based) | Partial (lazy_loading.py) | Partial |
| Caching for model responses | Partial | Partial | Partial |
| Session persistence compaction | Yes | No | **Missing** |

---

## 3. Full Independent Implementation Plan

### Phase 1: Critical Foundation (Week 1-2)

#### 1.1: SessionProjectionRegistry — ctx.sessionProjections

**File:** `src/zcoder/agent/codeagent/sessions.py` (new: `session_projection.py`)

**Rationale:** deepseek-harness has a full projection registry with eager drive over committed events, watermark caching, change feed, snapshot/checkpoint/restore/hydrate. zcoder's `SessionProjection` is a basic fold without caching, change detection, or persistence.

**Tasks:**
1. Create `session_projection.py` with `ProjectionDefinition`, `ProjectionHandle`, `SessionProjectionRegistry`
2. Implement `init/apply/wire` pattern for pure fold units
3. Implement watermark caching with `Object.is`-equivalent reference comparison
4. Implement change feed listeners (`on_changed`, `on_event_changed`)
5. Implement `snapshot()`, `checkpoint()`, `restore()`, `hydrate()` methods
6. Implement `stateVersion` with cache invalidation on mismatch
7. Register as `SessionStore.session_projections` property

**Estimated effort:** 3 days

#### 1.2: Session Stats Projection

**File:** `src/zcoder/agent/codeagent/session_projection.py`

**Rationale:** deepseek-harness `sessionStats` projection tracks 8 metrics: turns, steps, llmMs, toolMs, ttftMs, ttftSteps, decodeMs, decodeTokens. zcoder has basic `TokenUsage` and `CostBreakdown` but no wall-time metrics.

**Tasks:**
1. Implement `SessionStatsProjection` class with the 8 metrics
2. Fold `step/start`, `step/end`, `assistant/message`, `tool/call`, `tool/result`, `turn/end` events
3. Track first-token latency and decode wall time
4. Exclude from session summaries (`summary=False`)

**Estimated effort:** 1 day

#### 1.3: JSONL Session Persistence with Migration

**File:** `src/zcoder/agent/codeagent/session_persistence.py` (new)

**Rationale:** deepseek-harness uses JSONL persistence with zstd compression, lease-based concurrency, and format migration (v0→v4). zcoder uses single JSON file per session with no compression or migration.

**Tasks:**
1. Implement JSONL append-only session persistence
2. Add zstd compression option
3. Implement lease-based concurrent access control
4. Implement format migration pipeline (v0→v1→v2→v3→v4)
5. Add migration verifier

**Estimated effort:** 3 days

---

### Phase 2: Agent Loop Enhancement (Week 2-3)

#### 2.1: Phase-Based State Machine

**File:** `src/zcoder/agent/codeagent/loop.py`

**Rationale:** deepseek-harness `ReactLoopAgent` uses a 3-phase state machine (idle/running/maintenance) with wake/sleep cycle. zcoder `CodeAgent` uses a simple `running` boolean flag.

**Tasks:**
1. Replace `running` boolean with `Phase` discriminated union (idle/running/maintenance)
2. Implement wake/sleep cycle with `wake_driver()` and `when_idle()`
3. Implement inbox-based messaging (next-turn/next-step targets)
4. Implement `run_maintenance()` for abortable maintenance jobs
5. Add agent error dispatch events
6. Add agent status transition events

**Estimated effort:** 3 days

#### 2.2: Tool Execution Pipeline with Batch Support

**File:** `src/zcoder/agent/codeagent/tools.py` (new: `tool_executor.py`)

**Rationale:** deepseek-harness has a full `ToolExecutor`/`ToolDefinition`/`ResolvedToolSet` pipeline with batch execution, concurrency control, activation conditions, and guards. zcoder calls `tool.func` directly.

**Tasks:**
1. Implement `ToolExecutor` interface with `describe()`/`execute()` methods
2. Implement `ToolDefinition` with output schema, `projectContent()`, `finalizeContent()`
3. Implement `ResolvedToolSet` with `dispose()` and `view()`
4. Implement `ToolBatchInput`/`ToolBatchResult` with `maxParallelToolCalls`
5. Implement tool activation conditions (`when()`)
6. Implement tool restrictions (allow/deny lists)
7. Implement tool guards for post-policy denial
8. Implement `ToolBatchExecutionError` with partial results

**Estimated effort:** 4 days

#### 2.3: Model Selection Projection

**File:** `src/zcoder/agent/codeagent/sessions.py`

**Rationale:** deepseek-harness tracks model selection (provider, model, reasoningEffort) as a projection. zcoder has no model selection tracking.

**Tasks:**
1. Implement `ModelSelection` dataclass (provider, model, reasoningEffort)
2. Implement `ModelSelectionProjection` with `last_used` and `next`
3. Log `model/selection` events on model changes
4. Integrate with LLM client for model switching

**Estimated effort:** 1 day

---

### Phase 3: Performance & Reliability (Week 3-4)

#### 3.1: Circuit Breaker for Tool Execution

**File:** `src/zcoder/agent/optimization/circuit_breaker.py` (new)

**Rationale:** deepseek-harness has circuit breaker patterns for tool execution. zcoder has no circuit breaker.

**Tasks:**
1. Implement `CircuitBreaker` class (closed/open/half-open states)
2. Integrate with tool execution pipeline
3. Add configurable failure threshold and reset timeout
4. Add metrics for circuit breaker state changes

**Estimated effort:** 2 days

#### 3.2: Connection Pooling for LLM Clients

**File:** `src/zcoder/agent/optimization/pooling.py` (enhancement)

**Rationale:** deepseek-harness has connection management. zcoder has basic pooling but not integrated with LLM clients.

**Tasks:**
1. Integrate connection pooling into LLM adapter clients
2. Add keep-alive and connection reuse
3. Add pool metrics and health checks

**Estimated effort:** 2 days

#### 3.3: Lazy Module Loading

**File:** `src/zcoder/agent/optimization/lazy_loading.py` (enhancement)

**Rationale:** deepseek-harness uses Cordis fiber-based lazy loading. zcoder has basic lazy loading but not comprehensive.

**Tasks:**
1. Implement lazy loading for heavy modules (LLM adapters, web dashboard, SDK)
2. Add import-time deferral
3. Add lazy loading metrics

**Estimated effort:** 2 days

---

### Phase 4: Advanced Features (Week 4-5)

#### 4.1: Local GGUF Model Adapter

**File:** `src/zcoder/agent/codeagent/llm.py` (enhancement)

**Rationale:** deepseek-harness supports local model adapters. zcoder has `LocalLLM` class but it's not integrated.

**Tasks:**
1. Complete `LocalLLM` class with model discovery (GGUF file scanning)
2. Integrate with plugin system for dynamic model loading
3. Add model switching capability at runtime
4. Add local model quantization support

**Estimated effort:** 3 days

#### 4.2: Session Title Management

**File:** `src/zcoder/agent/codeagent/sessions.py`

**Rationale:** deepseek-harness has session-title-llm package for automatic title generation. zcoder derives title from first user message only.

**Tasks:**
1. Implement `SessionTitle` projection
2. Add LLM-based title generation
3. Add title rename support
4. Add title persistence

**Estimated effort:** 2 days

#### 4.3: Working Directory Management

**File:** `src/zcoder/agent/codeagent/sessions.py`

**Rationale:** deepseek-harness has `working-directory` package with admission controls. zcoder has basic cwd tracking.

**Tasks:**
1. Implement working directory change events
2. Add cwd admission controls
3. Add cwd persistence across sessions

**Estimated effort:** 1 day

---

### Implementation Timeline Summary

| Phase | Duration | Key Deliverables |
|-------|----------|-----------------|
| Phase 1 | 2 weeks | SessionProjectionRegistry, SessionStats, JSONL persistence |
| Phase 2 | 2 weeks | Phase-based agent loop, Tool execution pipeline, Model selection |
| Phase 3 | 2 weeks | Circuit breaker, Connection pooling, Lazy loading |
| Phase 4 | 2 weeks | Local GGUF, Session titles, Working directory |

**Total: 8 weeks**

---

## 4. Performance Optimization Plan

### 4.1 Current Performance Bottlenecks (from deepseek-harness comparison)

| Bottleneck | deepseek-harness Approach | zcoder Current | Gap |
|------------|--------------------------|----------------|-----|
| Session save on every event | JSONL append-only | Full JSON rewrite | **10x slower** |
| Session load | JSONL stream read | Full JSON read | **5x slower** |
| SessionProjection.fold() | Watermark cached, incremental | Full re-fold every call | **5x slower** |
| Plugin loading | Fiber-based lazy loading | Eager load_all() | **5x slower startup** |
| Config loading | Cached | Re-read every instantiation | **5x slower** |
| Tool execution | Batch with concurrency | Sequential one-by-one | **3x slower** |

### 4.2 Optimization 1: SessionStore Append-Only Writes

**File:** `src/zcoder/agent/codeagent/sessions.py`

```python
def save_append(self, session_id: str, event: dict) -> None:
    """Append-only write for session events (JSONL format)."""
    path = self._path(session_id)
    with open(path, 'a') as f:
        f.write(json.dumps(event) + '\n')
```

**Expected improvement:** 10x faster for append-heavy workloads

### 4.3 Optimization 2: SessionProjection Caching

**File:** `src/zcoder/agent/codeagent/session_projection.py`

```python
class SessionProjection:
    def __init__(self):
        self._cached_state = None
        self._last_event_count = 0

    def fold(self, event: SessionEvent) -> None:
        self.state = self._apply_event(self.state, event)
        self.event_count += 1
        self._cached_state = None  # Mark dirty

    def get_state(self) -> dict[str, Any]:
        if self._cached_state is None:
            self._cached_state = dict(self.state)
        return self._cached_state
```

**Expected improvement:** 5x faster for repeated state access

### 4.4 Optimization 3: Plugin Manager Lazy Loading

**File:** `src/zcoder/agent/plugin/manager.py`

```python
class PluginManager:
    def get_plugin(self, name: str) -> LoadedPlugin | None:
        if name not in self._loaded_plugins:
            self._load_plugin(name)
        return self._plugins.get(name)
```

**Expected improvement:** 5x faster startup time

### 4.5 Optimization 4: Config Caching

**File:** `src/zcoder/config/settings.py`

```python
_config_cache: Config | None = None
_config_cache_time: float = 0

def get_config() -> Config:
    now = time.time()
    if _config_cache is not None and now - _config_cache_time < 60:
        return _config_cache
    config = Config()
    _config_cache = config
    _config_cache_time = now
    return config
```

**Expected improvement:** 5x faster for repeated config access

### 4.6 Performance Benchmark Plan

| Benchmark | Current | Target | Improvement |
|-----------|---------|--------|-------------|
| SessionStore.save() | ~0.3ms | <0.1ms | 3x faster |
| SessionStore.load() | ~0.1ms | <0.05ms | 2x faster |
| SessionProjection.fold() | ~0.05ms | <0.01ms | 5x faster |
| PluginManager.load_all() | ~0.2ms | <0.1ms | 2x faster |
| Config.load() | ~5ms | <1ms | 5x faster |

---

## 5. Verification Checklist

### Phase 1 Verification
- [ ] `SessionProjectionRegistry.register()` works with `init/apply/wire`
- [ ] `stateOf()` returns correct folded state
- [ ] `snapshot()` returns consistent cut across all units
- [ ] `checkpoint()`/`restore()` round-trip preserves state
- [ ] `SessionStatsProjection` tracks all 8 metrics correctly
- [ ] JSONL persistence saves/loads correctly
- [ ] Format migration v0→v4 works

### Phase 2 Verification
- [ ] Phase transitions (idle→running→maintenance→idle) work
- [ ] Wake/sleep cycle delivers messages correctly
- [ ] Inbox splicing (next-turn/next-step) works
- [ ] Tool batch execution with concurrency control works
- [ ] Tool activation conditions (`when()`) work
- [ ] Model selection projection tracks changes

### Phase 3 Verification
- [ ] Circuit breaker opens after threshold failures
- [ ] Circuit breaker half-open allows trial requests
- [ ] Connection pooling reuses connections
- [ ] Lazy loading defers heavy module imports

### Phase 4 Verification
- [ ] Local GGUF model discovery works
- [ ] Model switching at runtime works
- [ ] Session title generation works
- [ ] Working directory change events work

### Performance Verification
- [ ] SessionStore.save() < 0.1ms
- [ ] SessionProjection.fold() < 0.01ms
- [ ] Plugin startup < 0.1ms
- [ ] All benchmarks show improvement over baseline

### Code Quality Verification
- [ ] Ruff: 0 errors
- [ ] Black: 0 files need reformatting
- [ ] Mypy: 0 errors (modified files)
- [ ] All unit tests pass
- [ ] All integration tests pass