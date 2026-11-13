# claude-code Features Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement all missing claude-code features in zcoder: tiered plugin system, 30+ hook event types, UI pane/dialog hooks, MCP tier control, telemetry plugin, settings policy reads, deny rules hold, pinned environment variables, session compaction hooks, and prompt composition hooks — with enterprise-grade performance optimization.

**Architecture:** Extend zcoder's Python agent framework with a TypeScript-compatible plugin tier system, hook event bus, and policy engine. Maintain clean architecture boundaries: Interfaces → Services → Domain/Core → Infrastructure. All new components follow existing patterns in `src/zcoder/agent/` and `src/zcoder/agent/enterprise/`.

**Tech Stack:** Python 3.12+, asyncio, pydantic, fastapi, psycopg2/psycopg3, textual, click/typer. No new external dependencies beyond existing pyproject.toml.

**Spec:** `/home/cvsz/zcoder/FEATURE_MATRIX.md` (Sections 14-15), `/home/cvsz/claude-code/mods/` (reference implementations)

---

## Global Constraints

- Python >= 3.12 (per pyproject.toml)
- Ruff line-length=110, target-version=py312, select=["E","F","I","B","UP"]
- Black line-length=110, target-version=["py312"]
- mypy python_version=3.12, no_implicit_optional, warn_unused_ignores
- Coverage threshold: 70% (current: 81.68%)
- All tests must pass: 2,225+ tests (unit + integration + e2e)
- SEC-001 through SEC-011 compliance maintained
- GPG-signed commits, multi-account governance (cvsz author / policedbc reviewer / cvsz integrator)
- No breaking changes to existing CLI/API interfaces
- Performance: CLI startup <500ms cold, <100ms warm; job claim <10ms

---

## Review Focus

| Input Class / Failure Mode | Expected Behavior | Owner Task |
|---------------------------|-------------------|------------|
| Malformed plugin manifest | Graceful error, no session crash | Task 1 |
| Hook timeout during tool call | Block tool, return timeout error to model | Task 3 |
| User-tier plugin tries to override org deny rule | Deny rule holds, violation logged | Task 7 |
| Org sets pinned env var, user plugin writes it | Write refused, debug log entry | Task 8 |
| Session compaction with user plugin hook | Compaction runs org/engine version, user hook skipped | Task 9 |

---

## Phase 1: Core Plugin Infrastructure (Tasks 1-4)

### Task 1: Plugin Tier System & Manifest

**Files:**
- Create: `src/zcoder/agent/plugin/tier.py`
- Create: `src/zcoder/agent/plugin/manifest.py`
- Create: `src/zcoder/agent/plugin/loader.py`
- Create: `src/zcoder/agent/plugin/manager.py`
- Create: `src/zcoder/agent/plugin/__init__.py`
- Create: `tests/unit/agent/plugin/test_tier.py`
- Create: `tests/unit/agent/plugin/test_loader.py`
- Create: `tests/unit/agent/plugin/test_manager.py`

**Interfaces:**
- Consumes: None (foundation)
- Produces: `PluginTier` enum, `PluginManifest` class, `PluginLoader` class, `PluginManager` class

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/agent/plugin/test_tier.py
def test_plugin_tier_ordering():
    from zcoder.agent.plugin.tier import PluginTier
    assert PluginTier.PREPEND.value < PluginTier.USER.value < PluginTier.APPEND.value < PluginTier.BUILTIN.value

def test_plugin_tier_from_string():
    from zcoder.agent.plugin.tier import PluginTier
    assert PluginTier.from_string("prepend") == PluginTier.PREPEND
    assert PluginTier.from_string("user") == PluginTier.USER
    assert PluginTier.from_string("append") == PluginTier.APPEND
    assert PluginTier.from_string("builtin") == PluginTier.BUILTIN

# tests/unit/agent/plugin/test_manifest.py
def test_plugin_manifest_validation():
    from zcoder.agent.plugin.manifest import PluginManifest
    manifest = PluginManifest(
        name="test-plugin",
        version="1.0.0",
        tier="user",
        hooks={"tool.call": ["hook1.py"]},
        tools={"my_tool": {"description": "A tool"}},
        commands=["my_cmd"],
        mcp_servers={"server1": {"command": "cmd"}}
    )
    assert manifest.name == "test-plugin"
    assert manifest.tier == "user"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/agent/plugin/test_tier.py tests/unit/agent/plugin/test_manifest.py -v`
Expected: FAIL (modules don't exist)

- [ ] **Step 3: Implement PluginTier enum in `src/zcoder/agent/plugin/tier.py`**

```python
from enum import IntEnum

class PluginTier(IntEnum):
    PREPEND = 0      # Organization prepend (outermost)
    USER = 1         # User-installed plugins
    APPEND = 2       # Organization append
    BUILTIN = 3      # Built-in plugins (innermost)

    @classmethod
    def from_string(cls, s: str) -> "PluginTier":
        mapping = {"prepend": cls.PREPEND, "user": cls.USER, "append": cls.APPEND, "builtin": cls.BUILTIN}
        if s not in mapping:
            raise ValueError(f"Unknown tier: {s}")
        return mapping[s]

    @property
    def can_override_user(self) -> bool:
        return self <= self.USER  # prepend and user can override user
```

- [ ] **Step 4: Implement PluginManifest in `src/zcoder/agent/plugin/manifest.py`**

```python
from dataclasses import dataclass, field
from typing import Any
from pydantic import BaseModel, Field, validator

class HookConfig(BaseModel):
    matcher: str = "*"
    command: str
    timeout: int = 30

class ToolConfig(BaseModel):
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)

class CommandConfig(BaseModel):
    description: str
    handler: str

class MCPServerConfig(BaseModel):
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)

class PluginManifest(BaseModel):
    name: str
    version: str
    tier: str = "user"
    description: str = ""
    author: str = ""
    homepage: str = ""
    hooks: dict[str, list[HookConfig]] = Field(default_factory=dict)
    tools: dict[str, ToolConfig] = Field(default_factory=dict)
    commands: dict[str, CommandConfig] = Field(default_factory=dict)
    mcp_servers: dict[str, MCPServerConfig] = Field(default_factory=dict)
    settings: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)

    @validator("tier")
    def validate_tier(cls, v):
        from zcoder.agent.plugin.tier import PluginTier
        try:
            PluginTier.from_string(v)
        except ValueError:
            raise ValueError(f"Invalid tier: {v}")
        return v
```

- [ ] **Step 5: Implement PluginLoader in `src/zcoder/agent/plugin/loader.py`**

```python
import json
import zipfile
from pathlib import Path
from typing import Optional
from zcoder.agent.plugin.manifest import PluginManifest
from zcoder.agent.plugin.tier import PluginTier

class PluginLoader:
    def __init__(self, plugin_dirs: list[Path] | None = None):
        self.plugin_dirs = plugin_dirs or [
            Path.home() / ".zcoder" / "plugins",
            Path("/usr/local/share/zcoder/plugins"),
            Path(__file__).parent.parent.parent / "plugins"  # builtin
        ]

    def load_manifest(self, plugin_path: Path) -> PluginManifest:
        manifest_path = plugin_path / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found: {manifest_path}")
        with open(manifest_path) as f:
            data = json.load(f)
        return PluginManifest(**data)

    def load_from_directory(self, plugin_path: Path) -> "LoadedPlugin":
        manifest = self.load_manifest(plugin_path)
        hooks = self._load_hooks(plugin_path, manifest.hooks)
        tools = self._load_tools(plugin_path, manifest.tools)
        commands = self._load_commands(plugin_path, manifest.commands)
        return LoadedPlugin(manifest=manifest, hooks=hooks, tools=tools, commands=commands)

    def _load_hooks(self, plugin_path: Path, hook_configs: dict) -> dict:
        # Load hook modules
        return {}

    def _load_tools(self, plugin_path: Path, tool_configs: dict) -> dict:
        # Load tool implementations
        return {}

    def _load_commands(self, plugin_path: Path, command_configs: dict) -> dict:
        # Load command handlers
        return {}

    def discover_plugins(self) -> list[Path]:
        plugins = []
        for plugin_dir in self.plugin_dirs:
            if plugin_dir.exists():
                for item in plugin_dir.iterdir():
                    if item.is_dir() and (item / "manifest.json").exists():
                        plugins.append(item)
        return plugins

@dataclass
class LoadedPlugin:
    manifest: PluginManifest
    hooks: dict
    tools: dict
    commands: dict
```

- [ ] **Step 6: Implement PluginManager in `src/zcoder/agent/plugin/manager.py`**

```python
from dataclasses import dataclass, field
from typing import Any
from zcoder.agent.plugin.loader import PluginLoader, LoadedPlugin
from zcoder.agent.plugin.tier import PluginTier
from zcoder.agent.plugin.manifest import PluginManifest

@dataclass
class PluginManager:
    loader: PluginLoader = field(default_factory=PluginLoader)
    plugins_by_tier: dict[PluginTier, list[LoadedPlugin]] = field(default_factory=dict)
    plugins_by_name: dict[str, LoadedPlugin] = field(default_factory=dict)

    def __post_init__(self):
        for tier in PluginTier:
            self.plugins_by_tier[tier] = []

    def load_all(self) -> None:
        for plugin_path in self.loader.discover_plugins():
            loaded = self.loader.load_from_directory(plugin_path)
            tier = PluginTier.from_string(loaded.manifest.tier)
            self.plugins_by_tier[tier].append(loaded)
            self.plugins_by_name[loaded.manifest.name] = loaded

    def get_plugins_for_tier(self, tier: PluginTier) -> list[LoadedPlugin]:
        return self.plugins_by_tier.get(tier, [])

    def get_all_plugins_ordered(self) -> list[LoadedPlugin]:
        """Return plugins in tier order: prepend -> user -> append -> builtin"""
        result = []
        for tier in PluginTier:
            result.extend(self.plugins_by_tier[tier])
        return result

    def get_plugin(self, name: str) -> LoadedPlugin | None:
        return self.plugins_by_name.get(name)

    def get_hooks_for_event(self, event: str) -> list[tuple[LoadedPlugin, Any]]:
        """Get all hooks for an event, ordered by tier"""
        hooks = []
        for plugin in self.get_all_plugins_ordered():
            if event in plugin.hooks:
                for hook in plugin.hooks[event]:
                    hooks.append((plugin, hook))
        return hooks
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/unit/agent/plugin/test_tier.py tests/unit/agent/plugin/test_manifest.py tests/unit/agent/plugin/test_loader.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/zcoder/agent/plugin/ tests/unit/agent/plugin/
git commit -m "feat(plugin): add tiered plugin system with manifest, loader, and manager"
```

---

### Task 2: Hook Event Bus (30+ Event Types)

**Files:**
- Create: `src/zcoder/agent/plugin/events.py`
- Create: `src/zcoder/agent/plugin/hook_bus.py`
- Create: `src/zcoder/agent/plugin/__init__.py` (update exports)
- Modify: `src/zcoder/agent/codeagent/hooks.py` (integrate)
- Create: `tests/unit/agent/plugin/test_events.py`
- Create: `tests/unit/agent/plugin/test_hook_bus.py`

**Interfaces:**
- Consumes: `PluginManager` from Task 1
- Produces: `HookEvent` enum, `HookBus` class, `HookContext` class

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/agent/plugin/test_events.py
def test_hook_event_comprehensive():
    from zcoder.agent.plugin.events import HookEvent
    # Core session events
    assert HookEvent.SESSION_START
    assert HookEvent.SESSION_END
    assert HookEvent.SESSION_COMPACT
    assert HookEvent.SESSION_RESUME
    # Prompt events
    assert HookEvent.PROMPT_SUBMIT
    assert HookEvent.PROMPT_COMPOSE
    assert HookEvent.PROMPT_SECTION
    assert HookEvent.PROMPT_CONTEXT
    assert HookEvent.PROMPT_ATTACHMENT
    assert HookEvent.PROMPT_FILL
    assert HookEvent.PROMPT_SUGGEST
    assert HookEvent.PROMPT_EDIT
    assert HookEvent.PROMPT_READ
    # Tool events
    assert HookEvent.TOOL_CALL
    assert HookEvent.TOOL_CHECK
    assert HookEvent.TOOL_DESCRIBE
    assert HookEvent.TOOL_REGISTER
    assert HookEvent.TOOL_LIST
    # Agent events
    assert HookEvent.AGENT_OFFER
    assert HookEvent.AGENT_SPAWN
    assert HookEvent.AGENT_REGISTER
    assert HookEvent.AGENT_LIST
    # Command events
    assert HookEvent.COMMAND_RUN
    assert HookEvent.COMMAND_DESCRIBE
    assert HookEvent.COMMAND_REGISTER
    assert HookEvent.COMMAND_LIST
    # UI events
    assert HookEvent.UI_RENDER
    assert HookEvent.UI_SCROLL
    assert HookEvent.UI_FOCUS
    assert HookEvent.UI_CLOSE
    assert HookEvent.UI_LOG
    assert HookEvent.UI_STATUS
    assert HookEvent.UI_OPEN
    assert HookEvent.UI_INVALIDATE
    assert HookEvent.UI_RESOLVE
    # Skill events
    assert HookEvent.SKILL_PROMPT
    # Attribution
    assert HookEvent.ATTRIBUTION_TEXT
    # Settings
    assert HookEvent.SETTINGS_READ
    # Env
    assert HookEvent.ENV_GET
    assert HookEvent.ENV_SET
    # Plugin
    assert HookEvent.PLUGIN_REGISTER
    # MCP
    assert HookEvent.MCP_CALL
    # Telemetry
    assert HookEvent.TELEMETRY_LOG
    assert HookEvent.TELEMETRY_MARK
    # Config
    assert HookEvent.CONFIG_READ
    assert HookEvent.CONFIG_WRITE
    # FS/HTTP/Process/Clock/Store/Model/Audio
    assert HookEvent.FS_READ
    assert HookEvent.HTTP_FETCH
    assert HookEvent.PROCESS_RUN
    assert HookEvent.CLOCK_AFTER
    assert HookEvent.STORE_GET
    assert HookEvent.MODEL_CALL
    assert HookEvent.AUDIO_CALL

def test_hook_event_blocking():
    from zcoder.agent.plugin.events import HookEvent, BLOCKING_EVENTS
    assert HookEvent.TOOL_CHECK in BLOCKING_EVENTS
    assert HookEvent.PROMPT_SUBMIT in BLOCKING_EVENTS
    assert HookEvent.ENV_SET in BLOCKING_EVENTS
    assert HookEvent.TOOL_REGISTER in BLOCKING_EVENTS
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/agent/plugin/test_events.py -v`
Expected: FAIL

- [ ] **Step 3: Implement HookEvent enum in `src/zcoder/agent/plugin/events.py`**

```python
from enum import Enum

class HookEvent(str, Enum):
    # Session lifecycle
    SESSION_START = "session.start"
    SESSION_END = "session.end"
    SESSION_COMPACT = "session.compact"
    SESSION_RESUME = "session.resume"
    SESSION_APPEND = "session.append"

    # Prompt composition
    PROMPT_SUBMIT = "prompt.submit"
    PROMPT_COMPOSE = "prompt.compose"
    PROMPT_SECTION = "prompt.section"
    PROMPT_CONTEXT = "prompt.context"
    PROMPT_ATTACHMENT = "prompt.attachment"
    PROMPT_FILL = "prompt.fill"
    PROMPT_SUGGEST = "prompt.suggest"
    PROMPT_EDIT = "prompt.edit"
    PROMPT_READ = "prompt.read"

    # Tool operations
    TOOL_CALL = "tool.call"
    TOOL_CHECK = "tool.check"
    TOOL_DESCRIBE = "tool.describe"
    TOOL_REGISTER = "tool.register"
    TOOL_LIST = "tool.list"

    # Agent operations
    AGENT_OFFER = "agent.offer"
    AGENT_SPAWN = "agent.spawn"
    AGENT_REGISTER = "agent.register"
    AGENT_LIST = "agent.list"

    # Command operations
    COMMAND_RUN = "command.run"
    COMMAND_DESCRIBE = "command.describe"
    COMMAND_REGISTER = "command.register"
    COMMAND_LIST = "command.list"

    # UI rendering
    UI_RENDER = "ui.render"
    UI_SCROLL = "ui.scroll"
    UI_FOCUS = "ui.focus"
    UI_CLOSE = "ui.close"
    UI_LOG = "ui.log"
    UI_STATUS = "ui.status"
    UI_OPEN = "ui.open"
    UI_INVALIDATE = "ui.invalidate"
    UI_RESOLVE = "ui.resolve"

    # Skill integration
    SKILL_PROMPT = "skill.prompt"

    # Attribution
    ATTRIBUTION_TEXT = "attribution.text"

    # Settings
    SETTINGS_READ = "settings.read"

    # Environment
    ENV_GET = "env.get"
    ENV_SET = "env.set"

    # Plugin management
    PLUGIN_REGISTER = "plugin.register"

    # MCP
    MCP_CALL = "mcp.call"

    # Telemetry
    TELEMETRY_LOG = "telemetry.log"
    TELEMETRY_MARK = "telemetry.mark"

    # Config
    CONFIG_READ = "config.read"
    CONFIG_WRITE = "config.write"

    # FS/HTTP/Process/Clock/Store/Model/Audio
    FS_READ = "fs.read"
    FS_WRITE = "fs.write"
    FS_LIST = "fs.list"
    FS_STAT = "fs.stat"
    HTTP_FETCH = "http.fetch"
    PROCESS_RUN = "process.run"
    CLOCK_AFTER = "clock.after"
    CLOCK_EVERY = "clock.every"
    CLOCK_NOW = "clock.now"
    CLOCK_SLEEP = "clock.sleep"
    STORE_GET = "store.get"
    STORE_SET = "store.set"
    STORE_DELETE = "store.delete"
    MODEL_CALL = "model.call"
    AUDIO_CALL = "audio.call"

    # Classic hooks (backward compat)
    CLASSIC_PRE_TOOL_USE = "classic.pre_tool_use"
    CLASSIC_POST_TOOL_USE = "classic.post_tool_use"
    CLASSIC_NOTIFICATION = "classic.notification"
    CLASSIC_STOP = "classic.stop"
    CLASSIC_SUBAGENT_START = "classic.subagent_start"
    CLASSIC_SUBAGENT_STOP = "classic.subagent_stop"
    CLASSIC_PRE_COMPACT = "classic.pre_compact"
    CLASSIC_POST_COMPACT = "classic.post_compact"
    CLASSIC_WORKTREE_CREATE = "classic.worktree_create"
    CLASSIC_WORKTREE_REMOVE = "classic.worktree_remove"
    CLASSIC_ELICITATION = "classic.elicitation"

# Events that can block (exit code 2 prevents action)
BLOCKING_EVENTS = frozenset({
    HookEvent.TOOL_CHECK,
    HookEvent.PROMPT_SUBMIT,
    HookEvent.ENV_SET,
    HookEvent.TOOL_REGISTER,
    HookEvent.CLASSIC_PRE_TOOL_USE,
    HookEvent.CLASSIC_ELICITATION,
    HookEvent.CLASSIC_WORKTREE_CREATE,
})

# Events that continue past user tier (org-controlled)
ORG_CONTROLLED_EVENTS = frozenset({
    HookEvent.CLASSIC_PRE_TOOL_USE,
    HookEvent.CLASSIC_POST_TOOL_USE,
    HookEvent.CLASSIC_NOTIFICATION,
    HookEvent.CLASSIC_STOP,
    HookEvent.CLASSIC_SUBAGENT_START,
    HookEvent.CLASSIC_SUBAGENT_STOP,
    HookEvent.CLASSIC_PRE_COMPACT,
    HookEvent.CLASSIC_POST_COMPACT,
    HookEvent.CLASSIC_WORKTREE_CREATE,
    HookEvent.CLASSIC_WORKTREE_REMOVE,
    HookEvent.CLASSIC_ELICITATION,
    HookEvent.PROMPT_SECTION,
    HookEvent.PROMPT_CONTEXT,
    HookEvent.PROMPT_ATTACHMENT,
    HookEvent.SKILL_PROMPT,
    HookEvent.ATTRIBUTION_TEXT,
    HookEvent.SESSION_APPEND,
    HookEvent.SESSION_COMPACT,
    HookEvent.SETTINGS_READ,
    HookEvent.TOOL_DESCRIBE,
    HookEvent.COMMAND_DESCRIBE,
    HookEvent.AGENT_OFFER,
    HookEvent.AGENT_SPAWN,
    HookEvent.TOOL_REGISTER,
    HookEvent.TOOL_LIST,
    HookEvent.TOOL_CHECK,
    HookEvent.UI_LOG,
    HookEvent.ENV_GET,
    HookEvent.ENV_SET,
    HookEvent.PLUGIN_REGISTER,
})
```

- [ ] **Step 4: Implement HookBus in `src/zcoder/agent/plugin/hook_bus.py`**

```python
import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable
from zcoder.agent.plugin.events import HookEvent, BLOCKING_EVENTS, ORG_CONTROLLED_EVENTS
from zcoder.agent.plugin.manager import PluginManager, LoadedPlugin
from zcoder.agent.plugin.tier import PluginTier

logger = logging.getLogger(__name__)

@dataclass
class HookContext:
    event: HookEvent
    tool: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    session_id: str = ""
    cwd: str = ""
    origin_tier: PluginTier = PluginTier.USER
    provider: str = ""
    approver: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

@dataclass
class HookResult:
    blocked: bool = False
    message: str = ""
    warnings: tuple[str, ...] = ()
    modified_args: dict[str, Any] | None = None
    deny_reason: str | None = None

class HookBus:
    def __init__(self, plugin_manager: PluginManager):
        self.plugin_manager = plugin_manager
        self._trace: list[tuple[PluginTier, HookEvent, str]] = []  # For deny-rules-hold

    async def fire(self, context: HookContext) -> HookResult:
        """Fire hooks for an event, respecting tier order and blocking semantics."""
        self._trace.clear()
        hooks = self.plugin_manager.get_hooks_for_event(context.event.value)
        if not hooks:
            return HookResult()

        warnings: list[str] = []
        blocked = False
        message = ""
        modified_args = None
        deny_reason = None

        # First pass: run all hooks in tier order
        for plugin, hook in hooks:
            tier = PluginTier.from_string(plugin.manifest.tier)
            self._trace.append((tier, context.event, plugin.manifest.name))

            try:
                result = await self._run_hook(plugin, hook, context, tier)
                if result.blocked:
                    blocked = True
                    message = result.message or "Blocked by hook"
                    deny_reason = result.deny_reason
                    break
                if result.warnings:
                    warnings.extend(result.warnings)
                if result.modified_args:
                    modified_args = result.modified_args
            except Exception as e:
                logger.error(f"Hook error: {plugin.manifest.name} / {context.event}: {e}")
                if context.event in BLOCKING_EVENTS:
                    warnings.append(f"Hook error: {e}")

        # Deny-rules-hold: if user-tier plugin rewrote a blocking decision,
        # re-run without user tier and compare
        if blocked and context.event in BLOCKING_EVENTS:
            if self._user_tier_rewrote_blocking_decision():
                org_result = await self._fire_without_user_tier(context)
                if org_result.blocked and org_result.message != message:
                    # Org deny rule holds
                    blocked = True
                    message = org_result.message
                    deny_reason = org_result.deny_reason
                    logger.info(f"Deny rule holds for {context.event}: {deny_reason}")

        return HookResult(
            blocked=blocked,
            message=message,
            warnings=tuple(warnings),
            modified_args=modified_args,
            deny_reason=deny_reason
        )

    def _user_tier_rewrote_blocking_decision(self) -> bool:
        """Check if any user-tier plugin in the trace modified the outcome."""
        # Simplified: check if user tier participated
        return any(tier == PluginTier.USER for tier, _, _ in self._trace)

    async def _fire_without_user_tier(self, context: HookContext) -> HookResult:
        """Re-run hooks excluding user tier (for deny-rules-hold)."""
        # This would need a filtered plugin list
        # Simplified implementation
        return HookResult()

    async def _run_hook(
        self,
        plugin: LoadedPlugin,
        hook_config: Any,
        context: HookContext,
        tier: PluginTier
    ) -> HookResult:
        """Run a single hook with timeout and env sanitization."""
        # Implementation similar to existing hooks.py but async
        # Uses subprocess with sanitized env
        pass
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/agent/plugin/test_events.py tests/unit/agent/plugin/test_hook_bus.py -v`
Expected: PASS

- [ ] **Step 6: Integrate with existing hooks.py**

Modify `src/zcoder/agent/codeagent/hooks.py` to use new HookBus for classic events while maintaining backward compatibility.

- [ ] **Step 7: Commit**

```bash
git add src/zcoder/agent/plugin/ src/zcoder/agent/codeagent/hooks.py tests/unit/agent/plugin/
git commit -m "feat(plugin): add 30+ hook event types and hook bus with deny-rules-hold"
```

---

### Task 3: UI Pane/Dialog Hooks (Diff Pane, Scroll, Focus)

**Files:**
- Create: `src/zcoder/agent/plugin/ui_hooks.py`
- Create: `src/zcoder/interfaces/tui/pane.py`
- Create: `tests/unit/agent/plugin/test_ui_hooks.py`

**Interfaces:**
- Consumes: `HookBus`, `HookEvent.UI_RENDER`, `HookEvent.UI_SCROLL`, `HookEvent.UI_FOCUS`, `HookEvent.UI_CLOSE`
- Produces: `UIPaneManager`, `DiffPane`, `DialogRenderer`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/agent/plugin/test_ui_hooks.py
def test_diff_pane_render():
    from zcoder.agent.plugin.ui_hooks import DiffPane
    pane = DiffPane(repo_path="/tmp/test", session_id="test")
    result = pane.render(file_list=["a.py", "b.py"], selected=0)
    assert "a.py" in result
    assert "b.py" in result

def test_ui_scroll_handler():
    from zcoder.agent.plugin.ui_hooks import UIPaneManager
    manager = UIPaneManager()
    # Test scroll event handling
    pass
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement UI hooks in `src/zcoder/agent/plugin/ui_hooks.py`**

```python
from dataclasses import dataclass
from typing import Any
from zcoder.agent.plugin.events import HookEvent
from zcoder.agent.plugin.hook_bus import HookBus, HookContext, HookResult

@dataclass
class DiffPane:
    repo_path: str
    session_id: str
    base: str = "HEAD"
    files: list[str] = None
    selected_index: int = 0
    hunks: dict[str, list[str]] = None

    def __post_init__(self):
        if self.files is None:
            self.files = []
        if self.hunks is None:
            self.hunks = {}

    def render(self, viewport_height: int = 20) -> str:
        """Render diff pane for docked or dialog mode."""
        lines = []
        lines.append(f"Diff: {self.repo_path} (base: {self.base})")
        lines.append(f"Files: {len(self.files)}")
        lines.append("─" * 50)
        for i, f in enumerate(self.files):
            prefix = "❯ " if i == self.selected_index else "  "
            lines.append(f"{prefix}{f}")
        return "\n".join(lines)

    def scroll(self, delta: int) -> None:
        """Scroll hunks or file list."""
        self.selected_index = max(0, min(len(self.files) - 1, self.selected_index + delta))

class UIPaneManager:
    def __init__(self, hook_bus: HookBus):
        self.hook_bus = hook_bus
        self.panes: dict[str, DiffPane] = {}

    async def handle_ui_render(self, context: HookContext) -> HookResult:
        """Handle ui.render event for panes."""
        # Render pane content
        pass

    async def handle_ui_scroll(self, context: HookContext) -> HookResult:
        """Handle ui.scroll event."""
        pane_id = context.args.get("pane_id")
        delta = context.args.get("delta", 0)
        if pane_id in self.panes:
            self.panes[pane_id].scroll(delta)
        return HookResult()

    async def handle_ui_focus(self, context: HookContext) -> HookResult:
        """Handle ui.focus event."""
        pane_id = context.args.get("pane_id")
        index = context.args.get("index", 0)
        if pane_id in self.panes:
            self.panes[pane_id].selected_index = index
        return HookResult()

    async def handle_ui_close(self, context: HookContext) -> HookResult:
        """Handle ui.close event."""
        pane_id = context.args.get("pane_id")
        if pane_id in self.panes:
            del self.panes[pane_id]
        return HookResult()
```

- [ ] **Step 4: Create TUI pane integration in `src/zcoder/interfaces/tui/pane.py`**

```python
from textual.widgets import Static
from textual.containers import Container
from zcoder.agent.plugin.ui_hooks import DiffPane

class DiffPaneWidget(Container):
    """Textual widget for diff pane."""
    def __init__(self, diff_pane: DiffPane):
        super().__init__()
        self.diff_pane = diff_pane
        self.static = Static(diff_pane.render())
        self.mount(self.static)

    def update(self):
        self.static.update(self.diff_pane.render())
```

- [ ] **Step 5: Run tests to verify they pass**

- [ ] **Step 6: Commit**

```bash
git add src/zcoder/agent/plugin/ui_hooks.py src/zcoder/interfaces/tui/pane.py tests/
git commit -m "feat(plugin): add UI pane/dialog hooks (diff pane, scroll, focus, close)"
```

---

### Task 4: MCP Tier Control (tool.register, tool.list, agent.offer)

**Files:**
- Create: `src/zcoder/agent/plugin/mcp_control.py`
- Modify: `src/zcoder/agent/orchestration/providers.py` (integrate)
- Create: `tests/unit/agent/plugin/test_mcp_control.py`

**Interfaces:**
- Consumes: `HookBus`, `HookEvent.TOOL_REGISTER`, `HookEvent.TOOL_LIST`, `HookEvent.AGENT_OFFER`, `HookEvent.AGENT_SPAWN`
- Produces: `MCPRegistry`, `ToolRegistry` with tier filtering

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/agent/plugin/test_mcp_control.py
def test_mcp_tool_registration_tier_filter():
    from zcoder.agent.plugin.mcp_control import MCPRegistry
    registry = MCPRegistry()
    # Prepend tier tool should be registered
    registry.register_tool("mcp__org_server__tool", "prepend")
    assert "mcp__org_server__tool" in registry.list_tools()
    # User tier tool with same prefix should be blocked if org allowlist exists
    registry.set_org_allowlist(["org_server"])
    registry.register_tool("mcp__org_server__tool2", "user")
    assert "mcp__org_server__tool2" not in registry.list_tools()
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement MCP control in `src/zcoder/agent/plugin/mcp_control.py`**

```python
from dataclasses import dataclass, field
from typing import Any
from zcoder.agent.plugin.tier import PluginTier
from zcoder.agent.plugin.hook_bus import HookBus, HookContext, HookResult

@dataclass
class MCPRegistry:
    tools: dict[str, dict[str, Any]] = field(default_factory=dict)  # tool_name -> {server, tier, plugin}
    org_allowlist: list[str] = field(default_factory=list)
    managed_mcp_servers: list[str] = field(default_factory=list)
    prepend_plugins: list[str] = field(default_factory=list)
    append_plugins: list[str] = field(default_factory=list)

    def set_org_config(self, allowlist: list[str], managed: list[str], prepend: list[str], append: list[str]):
        self.org_allowlist = allowlist
        self.managed_mcp_servers = managed
        self.prepend_plugins = prepend
        self.append_plugins = append

    def register_tool(self, tool_name: str, tier: str, server: str = "", plugin: str = "") -> bool:
        """Register a tool. Returns False if blocked by tier policy."""
        tier_enum = PluginTier.from_string(tier)

        # Prepend/append tier: always allow
        if tier_enum in (PluginTier.PREPEND, PluginTier.APPEND):
            self.tools[tool_name] = {"server": server, "tier": tier, "plugin": plugin}
            return True

        # User tier: check allowlist
        if tier_enum == PluginTier.USER:
            if not self.org_allowlist:
                # No allowlist: block tools that look like org tools
                if self._looks_like_org_tool(tool_name):
                    return False
            else:
                # Has allowlist: only allow if server in allowlist
                server_name = self._extract_server_name(tool_name)
                if server_name not in self.org_allowlist:
                    return False

            self.tools[tool_name] = {"server": server, "tier": tier, "plugin": plugin}
            return True

        # Builtin: allow
        self.tools[tool_name] = {"server": server, "tier": tier, "plugin": plugin}
        return True

    def _looks_like_org_tool(self, tool_name: str) -> bool:
        """Check if tool name resembles an org-managed tool."""
        for server in self.managed_mcp_servers:
            if tool_name.startswith(f"mcp__{server}__"):
                return True
            if tool_name.startswith(f"mcp__plugin_{server}_"):
                return True
        for plugin in self.prepend_plugins + self.append_plugins:
            if tool_name.startswith(f"mcp__plugin_{plugin}_"):
                return True
        return False

    def _extract_server_name(self, tool_name: str) -> str:
        """Extract server name from mcp__server__tool format."""
        if tool_name.startswith("mcp__"):
            parts = tool_name.split("__")
            if len(parts) >= 2:
                return parts[1]
        return ""

    def list_tools(self, tier_filter: PluginTier | None = None) -> list[str]:
        """List tools, optionally filtered by tier."""
        if tier_filter is None:
            return list(self.tools.keys())
        return [name for name, info in self.tools.items() if info["tier"] == tier_filter.value]

    def get_tool_info(self, tool_name: str) -> dict[str, Any] | None:
        return self.tools.get(tool_name)

class MCPControlHooks:
    """Hook handlers for MCP tier control."""
    def __init__(self, registry: MCPRegistry, hook_bus: HookBus):
        self.registry = registry
        self.hook_bus = hook_bus
        self._register_hooks()

    def _register_hooks(self):
        self.hook_bus.register(HookEvent.TOOL_REGISTER, self._on_tool_register)
        self.hook_bus.register(HookEvent.TOOL_LIST, self._on_tool_list)
        self.hook_bus.register(HookEvent.AGENT_OFFER, self._on_agent_offer)
        self.hook_bus.register(HookEvent.AGENT_SPAWN, self._on_agent_spawn)

    async def _on_tool_register(self, context: HookContext) -> HookResult:
        tool_name = context.args.get("tool_name", "")
        tier = context.origin_tier.value
        server = context.args.get("server", "")
        plugin = context.args.get("plugin", "")

        allowed = self.registry.register_tool(tool_name, tier, server, plugin)
        if not allowed:
            return HookResult(blocked=True, message=f"Tool {tool_name} blocked by org policy", deny_reason="org_mcp_policy")
        return HookResult()

    async def _on_tool_list(self, context: HookContext) -> HookResult:
        # Org tools are listed as org tier listed them
        # User tools that were blocked from registration are not listed
        pass

    async def _on_agent_offer(self, context: HookContext) -> HookResult:
        # Prepend/append tier agents continue past user tier
        pass

    async def _on_agent_spawn(self, context: HookContext) -> HookResult:
        pass
```

- [ ] **Step 4: Run tests to verify they pass**

- [ ] **Step 5: Commit**

```bash
git add src/zcoder/agent/plugin/mcp_control.py tests/
git commit -m "feat(plugin): add MCP tier control for tool.register, tool.list, agent.offer"
```

---

## Phase 2: Policy & Security (Tasks 5-8)

### Task 5: Settings Policy Reads (`$.settings.read({ source: "policy" })`)

**Files:**
- Create: `src/zcoder/agent/plugin/settings_policy.py`
- Modify: `src/zcoder/config/production.py` (integrate)
- Create: `tests/unit/agent/plugin/test_settings_policy.py`

**Interfaces:**
- Consumes: `HookBus`, `HookEvent.SETTINGS_READ`, `ProductionConfig`
- Produces: `SettingsPolicyReader` with tier-aware reads

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/agent/plugin/test_settings_policy.py
def test_settings_policy_read():
    from zcoder.agent.plugin.settings_policy import SettingsPolicyReader
    reader = SettingsPolicyReader()
    # Policy source should read from managed settings
    result = reader.read("some.setting", source="policy")
    assert result is not None
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement settings policy in `src/zcoder/agent/plugin/settings_policy.py`**

```python
from dataclasses import dataclass
from typing import Any
from zcoder.config.production import ProductionConfig, load_config
from zcoder.agent.plugin.hook_bus import HookBus, HookContext, HookResult
from zcoder.agent.plugin.events import HookEvent

@dataclass
class SettingsPolicyReader:
    config: ProductionConfig = None

    def __post_init__(self):
        if self.config is None:
            self.config = load_config()

    def read(self, key: str, source: str = "default") -> Any:
        """Read setting from specified source."""
        if source == "policy":
            return self._read_policy(key)
        elif source == "managed":
            return self._read_managed(key)
        return self._read_default(key)

    def _read_policy(self, key: str) -> Any:
        """Read from policy (managed settings). Fails closed."""
        try:
            # Navigate nested config
            parts = key.split(".")
            obj = self.config
            for part in parts:
                if hasattr(obj, part):
                    obj = getattr(obj, part)
                elif isinstance(obj, dict) and part in obj:
                    obj = obj[part]
                else:
                    return None
            return obj
        except Exception:
            # Fail closed: unreadable policy = policy in force
            return None

    def _read_managed(self, key: str) -> Any:
        """Read from managed settings file."""
        # Implementation for managed settings file
        pass

    def _read_default(self, key: str) -> Any:
        """Read from default/user/project settings."""
        pass

class SettingsPolicyHooks:
    def __init__(self, reader: SettingsPolicyReader, hook_bus: HookBus):
        self.reader = reader
        self.hook_bus = hook_bus
        self.hook_bus.register(HookEvent.SETTINGS_READ, self._on_settings_read)

    async def _on_settings_read(self, context: HookContext) -> HookResult:
        key = context.args.get("key", "")
        source = context.args.get("source", "default")

        # Prepend/append tier plugins continue past user tier
        if context.origin_tier in (PluginTier.PREPEND, PluginTier.APPEND):
            return HookResult()

        # User tier: read through policy
        value = self.reader.read(key, source)
        return HookResult(modified_args={"value": value})
```

- [ ] **Step 4: Run tests to verify they pass**

- [ ] **Step 5: Commit**

```bash
git add src/zcoder/agent/plugin/settings_policy.py tests/
git commit -m "feat(plugin): add settings policy reads with tier-aware access"
```

---

### Task 6: Telemetry Plugin (telemetry.log, telemetry.mark)

**Files:**
- Create: `src/zcoder/agent/plugin/telemetry.py`
- Modify: `src/zcoder/infrastructure/observability/otel.py` (integrate)
- Create: `tests/unit/agent/plugin/test_telemetry.py`

**Interfaces:**
- Consumes: `HookBus`, `HookEvent.TELEMETRY_LOG`, `HookEvent.TELEMETRY_MARK`, `OTelProvider`
- Produces: `TelemetryPlugin`, `TelemetrySender`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/agent/plugin/test_telemetry.py
def test_telemetry_log():
    from zcoder.agent.plugin.telemetry import TelemetryPlugin
    plugin = TelemetryPlugin()
    plugin.log("test_event", {"prop": "value"})
    # Should queue event
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement telemetry plugin in `src/zcoder/agent/plugin/telemetry.py`**

```python
import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any
from zcoder.agent.plugin.hook_bus import HookBus, HookContext, HookResult
from zcoder.agent.plugin.events import HookEvent
from zcoder.infrastructure.observability.otel import get_tracer, get_meter

@dataclass
class TelemetryEvent:
    event: str
    props: dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    session_id: str = ""

@dataclass
class TelemetryMark:
    feature: str
    kind: str  # ok, sad, bad
    reason: str | None = None
    props: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    session_id: str = ""

class TelemetryPlugin:
    def __init__(self, hook_bus: HookBus | None = None):
        self.hook_bus = hook_bus
        self.event_queue: list[TelemetryEvent] = []
        self.mark_queue: list[TelemetryMark] = []
        self.session_id = ""
        self.enabled = True
        self._flush_task: asyncio.Task | None = None

    def set_session(self, session_id: str):
        self.session_id = session_id

    def log(self, event: str, props: dict[str, Any]):
        """Queue a telemetry event."""
        if not self.enabled:
            return
        # Validate: snake_case event name, finite values
        self.event_queue.append(TelemetryEvent(
            event=event,
            props=props,
            session_id=self.session_id
        ))
        self._maybe_flush()

    def mark(self, feature: str, kind: str, reason: str | None = None, props: dict[str, Any] | None = None):
        """Queue a feature mark."""
        if not self.enabled:
            return
        if kind not in ("ok", "sad", "bad"):
            raise ValueError(f"Invalid mark kind: {kind}")
        if kind in ("sad", "bad") and not reason:
            raise ValueError(f"Reason required for {kind} mark")

        self.mark_queue.append(TelemetryMark(
            feature=feature,
            kind=kind,
            reason=reason,
            props=props or {},
            session_id=self.session_id
        ))
        self._maybe_flush()

    def _maybe_flush(self):
        if len(self.event_queue) + len(self.mark_queue) >= 100:
            self.flush()

    async def flush(self):
        """Send queued events to ingest."""
        if not self.event_queue and not self.mark_queue:
            return

        # Send to OTel or Anthropic ingest
        events = self.event_queue[:]
        marks = self.mark_queue[:]
        self.event_queue.clear()
        self.mark_queue.clear()

        # Use existing OTel infrastructure
        tracer = get_tracer()
        with tracer.start_as_current_span("telemetry.flush") as span:
            span.set_attribute("events.count", len(events))
            span.set_attribute("marks.count", len(marks))

    def disable(self):
        self.enabled = False

class TelemetryHooks:
    def __init__(self, plugin: TelemetryPlugin, hook_bus: HookBus):
        self.plugin = plugin
        self.hook_bus = hook_bus
        self.hook_bus.register(HookEvent.TELEMETRY_LOG, self._on_log)
        self.hook_bus.register(HookEvent.TELEMETRY_MARK, self._on_mark)

    async def _on_log(self, context: HookContext) -> HookResult:
        event = context.args.get("event", "")
        props = context.args.get("props", {})
        # Gate: only built-in tier or engine can call
        if context.origin_tier not in (PluginTier.PREPEND, PluginTier.APPEND, PluginTier.BUILTIN):
            return HookResult(blocked=True, message="Telemetry log restricted to org/builtin", deny_reason="telemetry_gate")
        self.plugin.log(event, props)
        return HookResult()

    async def _on_mark(self, context: HookContext) -> HookResult:
        feature = context.args.get("feature", "")
        kind = context.args.get("kind", "")
        reason = context.args.get("reason")
        props = context.args.get("props", {})

        if context.origin_tier not in (PluginTier.PREPEND, PluginTier.APPEND, PluginTier.BUILTIN):
            return HookResult(blocked=True, message="Telemetry mark restricted to org/builtin", deny_reason="telemetry_gate")

        try:
            self.plugin.mark(feature, kind, reason, props)
        except ValueError as e:
            return HookResult(blocked=True, message=str(e), deny_reason="telemetry_validation")
        return HookResult()
```

- [ ] **Step 4: Run tests to verify they pass**

- [ ] **Step 5: Commit**

```bash
git add src/zcoder/agent/plugin/telemetry.py tests/
git commit -m "feat(plugin): add telemetry plugin with log/mark and tier gate"
```

---

### Task 7: Deny Rules Hold (Org Deny Overrides User Plugins)

**Files:**
- Create: `src/zcoder/agent/plugin/deny_rules.py`
- Modify: `src/zcoder/agent/plugin/hook_bus.py` (integrate)
- Create: `tests/unit/agent/plugin/test_deny_rules.py`

**Interfaces:**
- Consumes: `HookBus`, `HookEvent.TOOL_CHECK`, `PermissionEngine`
- Produces: `DenyRulesEngine` with double-dispatch logic

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/agent/plugin/test_deny_rules.py
def test_deny_rule_holds_over_user_allow():
    from zcoder.agent.plugin.deny_rules import DenyRulesEngine
    engine = DenyRulesEngine()
    # Org sets deny rule
    engine.add_deny_rule("run_shell", "security_policy")
    # User plugin tries to allow
    result = engine.check("run_shell", user_allow=True)
    assert result.blocked == True
    assert result.deny_reason == "security_policy"
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement deny rules in `src/zcoder/agent/plugin/deny_rules.py`**

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from zcoder.agent.plugin.tier import PluginTier
from zcoder.agent.plugin.hook_bus import HookBus, HookContext, HookResult
from zcoder.agent.plugin.events import HookEvent

class DenyReason(Enum):
    SETTINGS_RULE = "rule"
    CLASSIC_HOOK = "hook"
    SETTING_ASK = "setting"
    CEILING = "ceiling"
    PLUGIN_ASK = "plugin"
    HOST_ASK = "host"
    REFUSAL = "refusal"

@dataclass
class DenyRule:
    tool_pattern: str
    reason: DenyReason
    source: str  # rule name, hook event, setting key, etc.
    description: str = ""

@dataclass
class DenyRulesEngine:
    rules: list[DenyRule] = field(default_factory=list)
    allow_mods_to_override: bool = False

    def add_deny_rule(self, tool_pattern: str, source: str, reason: DenyReason = DenyReason.SETTINGS_RULE, description: str = ""):
        self.rules.append(DenyRule(tool_pattern, reason, source, description))

    def check(self, tool_name: str, user_allow: bool = False) -> HookResult:
        """Check if tool is denied. Implements deny-rules-hold logic."""
        # Find matching deny rule
        matching_rule = None
        for rule in self.rules:
            if self._match(tool_name, rule.tool_pattern):
                matching_rule = rule
                break

        if not matching_rule:
            return HookResult()  # No deny rule

        # First pass: would user plugin rewrite?
        if user_allow and not self.allow_mods_to_override:
            # Second pass: re-evaluate without user tier
            return HookResult(
                blocked=True,
                message=f"Deny rule holds: {matching_rule.source}",
                deny_reason=matching_rule.reason.value
            )

        # If user allow is stricter (deny over ask), it stands
        return HookResult(
            blocked=True,
            message=f"Denied by {matching_rule.reason.value}: {matching_rule.source}",
            deny_reason=matching_rule.reason.value
        )

    def _match(self, tool_name: str, pattern: str) -> bool:
        import fnmatch
        return fnmatch.fnmatch(tool_name, pattern)

class DenyRulesHooks:
    def __init__(self, engine: DenyRulesEngine, hook_bus: HookBus):
        self.engine = engine
        self.hook_bus = hook_bus
        self.hook_bus.register(HookEvent.TOOL_CHECK, self._on_tool_check)

    async def _on_tool_check(self, context: HookContext) -> HookResult:
        tool_name = context.args.get("tool", "")
        # Check if any user-tier plugin in trace would rewrite
        user_would_allow = self._user_tier_would_allow(context, tool_name)

        result = self.engine.check(tool_name, user_allow=user_would_allow)
        if result.blocked:
            # Log the hold (ui.log row continues past user tier)
            self._log_hold(context, tool_name, result)
        return result

    def _user_tier_would_allow(self, context: HookContext, tool_name: str) -> bool:
        # Simplified: check if user tier plugins are registered for tool.check
        return False  # Would need plugin inspection

    def _log_hold(self, context: HookContext, tool_name: str, result: HookResult):
        # Log via ui.log (continues past user tier)
        pass
```

- [ ] **Step 4: Integrate with HookBus double-dispatch**

Modify `src/zcoder/agent/plugin/hook_bus.py` to implement the double-dispatch logic for `TOOL_CHECK` events.

- [ ] **Step 5: Run tests to verify they pass**

- [ ] **Step 6: Commit**

```bash
git add src/zcoder/agent/plugin/deny_rules.py src/zcoder/agent/plugin/hook_bus.py tests/
git commit -m "feat(plugin): add deny-rules-hold with double-dispatch logic"
```

---

### Task 8: Pinned Environment Variables

**Files:**
- Create: `src/zcoder/agent/plugin/pinned_env.py`
- Modify: `src/zcoder/core/security.py` (integrate with `build_child_env`)
- Create: `tests/unit/agent/plugin/test_pinned_env.py`

**Interfaces:**
- Consumes: `HookBus`, `HookEvent.ENV_SET`, `HookEvent.ENV_GET`, `ProductionConfig`
- Produces: `PinnedEnvManager` with org-controlled variables

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/agent/plugin/test_pinned_env.py
def test_pinned_env_blocks_user_write():
    from zcoder.agent.plugin.pinned_env import PinnedEnvManager
    manager = PinnedEnvManager()
    manager.set_managed_env({"API_KEY": "secret"})
    # User plugin tries to write
    result = manager.check_write("API_KEY", PluginTier.USER)
    assert result.blocked == True
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement pinned env in `src/zcoder/agent/plugin/pinned_env.py`**

```python
from dataclasses import dataclass, field
from typing import Any
from zcoder.agent.plugin.tier import PluginTier
from zcoder.agent.plugin.hook_bus import HookBus, HookContext, HookResult
from zcoder.agent.plugin.events import HookEvent
from zcoder.config.production import ProductionConfig

# Always-pinned variables (every build)
ALWAYS_PINNED = frozenset({
    "LD_PRELOAD", "LD_LIBRARY_PATH", "LD_AUDIT",
    "DYLD_INSERT_LIBRARIES", "DYLD_LIBRARY_PATH", "DYLD_FRAMEWORK_PATH",
    "BASH_ENV", "ENV", "ZDOTDIR", "NODE_OPTIONS",
    "CLAUDE_CODE_MANAGED_SETTINGS_PATH",
    "CLAUDE_CODE_REMOTE_SETTINGS_PATH",
    "CLAUDE_CODE_MOCK_REMOTE_SETTINGS",
    "CLAUDE_CODE_DISABLE_ADMIN_ENV_UNION",
    "CLAUDE_CONFIG_DIR",
    "CLAUDE_SECURESTORAGE_CONFIG_DIR",
    "USE_LOCAL_OAUTH",
    "USE_STAGING_OAUTH",
    "CLAUDE_LOCAL_OAUTH_API_BASE",
})

# Launcher variables (pinned when policy names launcher)
LAUNCHER_PINNED = frozenset({
    "CLAUDE_CODE_PROCESS_WRAPPER",
})

@dataclass
class PinnedEnvManager:
    config: ProductionConfig = None
    managed_env: dict[str, str] = field(default_factory=dict)
    launcher_name: str = ""

    def __post_init__(self):
        if self.config is None:
            from zcoder.config.production import load_config
            self.config = load_config()

    def set_managed_env(self, env: dict[str, str]):
        self.managed_env = env

    def set_launcher(self, name: str):
        self.launcher_name = name

    def is_pinned(self, var_name: str) -> bool:
        """Check if variable is pinned."""
        if var_name in ALWAYS_PINNED:
            return True
        if self.launcher_name and var_name in LAUNCHER_PINNED:
            return True
        # Managed settings env vars
        if var_name in self.managed_env:
            return True
        return False

    def check_write(self, var_name: str, tier: PluginTier) -> HookResult:
        """Check if write is allowed."""
        if tier in (PluginTier.PREPEND, PluginTier.APPEND, PluginTier.BUILTIN):
            return HookResult()  # Org/builtin can write

        if self.is_pinned(var_name):
            return HookResult(
                blocked=True,
                message=f"Variable {var_name} is pinned by organization policy",
                deny_reason="pinned_env"
            )
        return HookResult()

    def check_read(self, var_name: str, tier: PluginTier) -> HookResult:
        """Check if read is allowed (org reads continue past user tier)."""
        if tier in (PluginTier.PREPEND, PluginTier.APPEND):
            return HookResult(modified_args={"continue_past_user_tier": True})
        return HookResult()

class PinnedEnvHooks:
    def __init__(self, manager: PinnedEnvManager, hook_bus: HookBus):
        self.manager = manager
        self.hook_bus = hook_bus
        self.hook_bus.register(HookEvent.ENV_SET, self._on_env_set)
        self.hook_bus.register(HookEvent.ENV_GET, self._on_env_get)

    async def _on_env_set(self, context: HookContext) -> HookResult:
        var_name = context.args.get("name", "")
        return self.manager.check_write(var_name, context.origin_tier)

    async def _on_env_get(self, context: HookContext) -> HookResult:
        var_name = context.args.get("name", "")
        return self.manager.check_read(var_name, context.origin_tier)
```

- [ ] **Step 4: Integrate with `build_child_env` in `src/zcoder/core/security.py`**

```python
# In build_child_env, add pinned env check before setting
from zcoder.agent.plugin.pinned_env import PinnedEnvManager, ALWAYS_PINNED
```

- [ ] **Step 5: Run tests to verify they pass**

- [ ] **Step 6: Commit**

```bash
git add src/zcoder/agent/plugin/pinned_env.py src/zcoder/core/security.py tests/
git commit -m "feat(plugin): add pinned environment variables with tier enforcement"
```

---

## Phase 3: Session & Prompt Hooks (Tasks 9-10)

### Task 9: Session Compaction Hooks

**Files:**
- Create: `src/zcoder/agent/plugin/compaction.py`
- Modify: `src/zcoder/agent/orchestration/sessions.py` (integrate)
- Create: `tests/unit/agent/plugin/test_compaction.py`

**Interfaces:**
- Consumes: `HookBus`, `HookEvent.SESSION_COMPACT`, `HookEvent.CLASSIC_PRE_COMPACT`, `HookEvent.CLASSIC_POST_COMPACT`
- Produces: `CompactionHooks` with org-controlled compaction

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/agent/plugin/test_compaction.py
def test_compaction_org_controlled():
    from zcoder.agent.plugin.compaction import CompactionHooks
    hooks = CompactionHooks()
    # User plugin hook should not run for compaction
    result = hooks.pre_compact("session_1", "token_limit", origin_tier=PluginTier.USER)
    assert result.blocked == False  # Continues past user tier
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement compaction hooks in `src/zcoder/agent/plugin/compaction.py`**

```python
from zcoder.agent.plugin.hook_bus import HookBus, HookContext, HookResult
from zcoder.agent.plugin.events import HookEvent
from zcoder.agent.plugin.tier import PluginTier

class CompactionHooks:
    def __init__(self, hook_bus: HookBus):
        self.hook_bus = hook_bus
        self.hook_bus.register(HookEvent.SESSION_COMPACT, self._on_compact)
        self.hook_bus.register(HookEvent.CLASSIC_PRE_COMPACT, self._on_pre_compact)
        self.hook_bus.register(HookEvent.CLASSIC_POST_COMPACT, self._on_post_compact)

    async def _on_compact(self, context: HookContext) -> HookResult:
        # Continue past user tier: compaction is org/engine controlled
        if context.origin_tier == PluginTier.USER:
            return HookResult(modified_args={"continue_past_user_tier": True})
        return HookResult()

    async def _on_pre_compact(self, context: HookContext) -> HookResult:
        if context.origin_tier == PluginTier.USER:
            return HookResult(modified_args={"continue_past_user_tier": True})
        return HookResult()

    async def _on_post_compact(self, context: HookContext) -> HookResult:
        if context.origin_tier == PluginTier.USER:
            return HookResult(modified_args={"continue_past_user_tier": True})
        return HookResult()
```

- [ ] **Step 4: Integrate with session orchestration**

Modify `src/zcoder/agent/orchestration/sessions.py` to fire compaction events.

- [ ] **Step 5: Run tests to verify they pass**

- [ ] **Step 6: Commit**

```bash
git add src/zcoder/agent/plugin/compaction.py src/zcoder/agent/orchestration/sessions.py tests/
git commit -m "feat(plugin): add session compaction hooks with org control"
```

---

### Task 10: Prompt Composition Hooks

**Files:**
- Create: `src/zcoder/agent/plugin/prompt_compose.py`
- Modify: `src/zcoder/agent/orchestration/agents_sdk.py` (integrate)
- Create: `tests/unit/agent/plugin/test_prompt_compose.py`

**Interfaces:**
- Consumes: `HookBus`, `HookEvent.PROMPT_COMPOSE`, `HookEvent.PROMPT_SECTION`, `HookEvent.PROMPT_CONTEXT`, `HookEvent.PROMPT_ATTACHMENT`, `HookEvent.SKILL_PROMPT`, `HookEvent.ATTRIBUTION_TEXT`
- Produces: `PromptCompositionHooks` with org-controlled system prompt

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/agent/plugin/test_prompt_compose.py
def test_prompt_compose_org_controlled():
    from zcoder.agent.plugin.prompt_compose import PromptCompositionHooks
    hooks = PromptCompositionHooks()
    # User plugin cannot modify system prompt sections
    result = hooks.compose(sections=[], origin_tier=PluginTier.USER)
    assert result.modified_args is not None
    assert result.modified_args["continue_past_user_tier"] == True
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement prompt composition hooks in `src/zcoder/agent/plugin/prompt_compose.py`**

```python
from zcoder.agent.plugin.hook_bus import HookBus, HookContext, HookResult
from zcoder.agent.plugin.events import HookEvent
from zcoder.agent.plugin.tier import PluginTier

class PromptCompositionHooks:
    def __init__(self, hook_bus: HookBus):
        self.hook_bus = hook_bus
        self.hook_bus.register(HookEvent.PROMPT_COMPOSE, self._on_compose)
        self.hook_bus.register(HookEvent.PROMPT_SECTION, self._on_section)
        self.hook_bus.register(HookEvent.PROMPT_CONTEXT, self._on_context)
        self.hook_bus.register(HookEvent.PROMPT_ATTACHMENT, self._on_attachment)
        self.hook_bus.register(HookEvent.SKILL_PROMPT, self._on_skill_prompt)
        self.hook_bus.register(HookEvent.ATTRIBUTION_TEXT, self._on_attribution)

    async def _on_compose(self, context: HookContext) -> HookResult:
        if context.origin_tier == PluginTier.USER:
            return HookResult(modified_args={"continue_past_user_tier": True})
        return HookResult()

    async def _on_section(self, context: HookContext) -> HookResult:
        if context.origin_tier == PluginTier.USER:
            return HookResult(modified_args={"continue_past_user_tier": True})
        return HookResult()

    async def _on_context(self, context: HookContext) -> HookResult:
        if context.origin_tier == PluginTier.USER:
            return HookResult(modified_args={"continue_past_user_tier": True})
        return HookResult()

    async def _on_attachment(self, context: HookContext) -> HookResult:
        if context.origin_tier == PluginTier.USER:
            return HookResult(modified_args={"continue_past_user_tier": True})
        return HookResult()

    async def _on_skill_prompt(self, context: HookContext) -> HookResult:
        if context.origin_tier == PluginTier.USER:
            return HookResult(modified_args={"continue_past_user_tier": True})
        return HookResult()

    async def _on_attribution(self, context: HookContext) -> HookResult:
        if context.origin_tier == PluginTier.USER:
            return HookResult(modified_args={"continue_past_user_tier": True})
        return HookResult()
```

- [ ] **Step 4: Integrate with agent orchestration**

Modify `src/zcoder/agent/orchestration/agents_sdk.py` to fire prompt composition events.

- [ ] **Step 5: Run tests to verify they pass**

- [ ] **Step 6: Commit**

```bash
git add src/zcoder/agent/plugin/prompt_compose.py src/zcoder/agent/orchestration/agents_sdk.py tests/
git commit -m "feat(plugin): add prompt composition hooks with org control"
```

---

## Phase 4: Performance Optimization (Task 11)

### Task 11: Performance Optimization

**Files:**
- Modify: `src/zcoder/agent/plugin/hook_bus.py` (caching, async optimization)
- Modify: `src/zcoder/agent/plugin/manager.py` (lazy loading)
- Modify: `src/zcoder/main.py` (startup optimization)
- Create: `tests/performance/test_plugin_perf.py`

**Interfaces:**
- Consumes: All plugin components
- Produces: Optimized startup, hook dispatch, memory usage

- [ ] **Step 1: Write performance tests**

```python
# tests/performance/test_plugin_perf.py
def test_plugin_load_time():
    import time
    from zcoder.agent.plugin.manager import PluginManager
    start = time.time()
    mgr = PluginManager()
    mgr.load_all()
    elapsed = time.time() - start
    assert elapsed < 0.1  # <100ms

def test_hook_dispatch_latency():
    import asyncio
    import time
    from zcoder.agent.plugin.hook_bus import HookBus
    from zcoder.agent.plugin.manager import PluginManager
    mgr = PluginManager()
    mgr.load_all()
    bus = HookBus(mgr)
    start = time.time()
    for _ in range(100):
        asyncio.run(bus.fire(HookContext(event=HookEvent.TOOL_CHECK, tool="test_tool")))
    elapsed = time.time() - start
    assert elapsed < 0.05  # <0.5ms per dispatch
```

- [ ] **Step 2: Run tests to establish baseline**

- [ ] **Step 3: Optimize HookBus**

```python
# In hook_bus.py - add caching
class HookBus:
    def __init__(self, plugin_manager: PluginManager):
        self.plugin_manager = plugin_manager
        self._hook_cache: dict[str, list[tuple[LoadedPlugin, Any]]] = {}
        self._trace: list[tuple[PluginTier, HookEvent, str]] = []

    def get_hooks_for_event(self, event: str) -> list[tuple[LoadedPlugin, Any]]:
        if event not in self._hook_cache:
            self._hook_cache[event] = self.plugin_manager.get_hooks_for_event(event)
        return self._hook_cache[event]

    def invalidate_cache(self):
        self._hook_cache.clear()
```

- [ ] **Step 4: Optimize PluginManager lazy loading**

```python
# In manager.py - lazy load plugins
class PluginManager:
    def __init__(self, plugin_dirs: list[Path] | None = None):
        self.loader = PluginLoader(plugin_dirs)
        self._loaded = False
        self._plugins_by_tier: dict[PluginTier, list[LoadedPlugin]] = {}
        self._plugins_by_name: dict[str, LoadedPlugin] = {}

    def _ensure_loaded(self):
        if not self._loaded:
            self.load_all()
            self._loaded = True

    def get_plugins_for_tier(self, tier: PluginTier) -> list[LoadedPlugin]:
        self._ensure_loaded()
        return self._plugins_by_tier.get(tier, [])
```

- [ ] **Step 5: Optimize CLI startup in main.py**

```python
# In main.py - defer plugin loading until needed
def get_plugin_manager() -> PluginManager:
    global _PLUGIN_MANAGER
    if _PLUGIN_MANAGER is None:
        _PLUGIN_MANAGER = PluginManager()
    return _PLUGIN_MANAGER
```

- [ ] **Step 6: Run performance tests to verify improvements**

Run: `pytest tests/performance/test_plugin_perf.py -v`
Expected: PASS with improved times

- [ ] **Step 7: Commit**

```bash
git add src/zcoder/agent/plugin/ src/zcoder/main.py tests/performance/
git commit -m "perf(plugin): optimize plugin loading, hook dispatch, and CLI startup"
```

---

## Phase 5: Integration & Validation (Task 12)

### Task 12: Full Integration Testing

**Files:**
- Create: `tests/integration/test_plugin_system.py`
- Create: `tests/e2e/test_plugin_e2e.py`
- Modify: `tests/conftest.py` (fixtures)

**Interfaces:**
- Consumes: All plugin components
- Produces: End-to-end validation

- [ ] **Step 1: Write integration tests**

```python
# tests/integration/test_plugin_system.py
def test_full_plugin_workflow(pg_store):
    """Test complete plugin lifecycle: install -> load -> hook fire -> uninstall"""
    pass

def test_tier_precedence(pg_store):
    """Test prepend > user > append > builtin precedence"""
    pass

def test_deny_rules_hold_integration(pg_store):
    """Test deny rule holds over user plugin allow"""
    pass

def test_pinned_env_integration(pg_store):
    """Test pinned env blocks user writes"""
    pass

def test_mcp_tier_control_integration(pg_store):
    """Test MCP tool registration tier filtering"""
    pass
```

- [ ] **Step 2: Run all tests**

Run: `pytest tests/ -v --tb=short`
Expected: 2,225+ tests pass

- [ ] **Step 3: Run quality gates**

Run: `make check`
Expected: All gates pass (lint, typecheck, security, test-cov)

- [ ] **Step 4: Run health checks**

Run: `python -m zcoder.main --health-check --health-check-deep`
Expected: Healthy

- [ ] **Step 5: Build standalone**

Run: `make standalone`
Expected: Build succeeds

- [ ] **Step 6: Commit**

```bash
git add tests/
git commit -m "test(plugin): add full integration and E2E tests for plugin system"
```

---

## Summary

This plan implements all 10 missing claude-code features in zcoder across 12 tasks:

| Task | Feature | Est. Effort |
|------|---------|-------------|
| 1 | Plugin Tier System & Manifest | Medium |
| 2 | Hook Event Bus (30+ events) | High |
| 3 | UI Pane/Dialog Hooks | Medium |
| 4 | MCP Tier Control | Medium |
| 5 | Settings Policy Reads | Low |
| 6 | Telemetry Plugin | Medium |
| 7 | Deny Rules Hold | High |
| 8 | Pinned Environment Variables | Medium |
| 9 | Session Compaction Hooks | Low |
| 10 | Prompt Composition Hooks | Medium |
| 11 | Performance Optimization | Medium |
| 12 | Integration Testing | Medium |

**Total estimated effort:** ~40-50 hours of implementation

**Key architectural decisions:**
- Tier system uses IntEnum for natural ordering
- Hook bus uses double-dispatch for deny-rules-hold
- All org-controlled events continue past user tier
- Pinned env fails closed (unreadable policy = policy in force)
- Lazy plugin loading for startup performance
- Backward compatibility with existing hooks.py maintained

**Execution approach:** Subagent-driven development recommended due to high task interdependence and need for independent review at each tier boundary.