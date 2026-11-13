"""ZCoder Plugin System.

A tiered plugin system compatible with claude-code's architecture:
- PREPEND: Organization prepend tier (outermost)
- USER: User-installed plugins
- APPEND: Organization append tier
- BUILTIN: Built-in plugins (innermost)

Plugins are loaded from directories containing manifest.json and
optional hooks.py, tools.py, commands.py modules.
"""

from zcoder.agent.plugin.compaction import CompactionHooks, create_compaction_hooks
from zcoder.agent.plugin.events import (
    BLOCKING_EVENTS,
    ORG_CONTROLLED_EVENTS,
    HookEvent,
    get_all_events,
    is_blocking,
    is_org_controlled,
)
from zcoder.agent.plugin.hook_bus import HookBus, HookContext, HookResult
from zcoder.agent.plugin.loader import LoadedCommand, LoadedHook, LoadedPlugin, LoadedTool, PluginLoader
from zcoder.agent.plugin.manager import PluginManager
from zcoder.agent.plugin.manifest import (
    CommandConfig,
    HookConfig,
    MCPServerConfig,
    PluginManifest,
    ToolConfig,
)
from zcoder.agent.plugin.mcp_control import MCPControlHooks, MCPRegistry, create_mcp_control
from zcoder.agent.plugin.performance import (
    LazyPluginManager,
    OptimizedHookBus,
    PerformanceMetrics,
    PluginSystemInitializer,
    create_optimized_plugin_system,
    get_hook_bus,
    get_plugin_manager,
    get_plugin_system,
    initialize_plugin_system,
)
from zcoder.agent.plugin.pinned_env import PinnedEnvManager, create_pinned_env_manager
from zcoder.agent.plugin.prompt_compose import PromptCompositionHooks, create_prompt_composition_hooks
from zcoder.agent.plugin.settings_policy import (
    SettingsPolicyHooks,
    SettingsPolicyReader,
    create_settings_policy_hooks,
)
from zcoder.agent.plugin.telemetry import TelemetryHooks, TelemetryPlugin, create_telemetry_plugin
from zcoder.agent.plugin.tier import PluginTier
from zcoder.agent.plugin.ui_hooks import DiffPane, UIPaneManager, register_ui_hooks

__all__ = [
    "PluginTier",
    "PluginManifest",
    "HookConfig",
    "ToolConfig",
    "CommandConfig",
    "MCPServerConfig",
    "PluginLoader",
    "LoadedPlugin",
    "LoadedHook",
    "LoadedTool",
    "LoadedCommand",
    "PluginManager",
    "HookEvent",
    "BLOCKING_EVENTS",
    "ORG_CONTROLLED_EVENTS",
    "get_all_events",
    "is_blocking",
    "is_org_controlled",
    "HookBus",
    "HookContext",
    "HookResult",
    "DiffPane",
    "UIPaneManager",
    "register_ui_hooks",
    "MCPRegistry",
    "MCPControlHooks",
    "create_mcp_control",
    "SettingsPolicyReader",
    "SettingsPolicyHooks",
    "create_settings_policy_hooks",
    "TelemetryPlugin",
    "TelemetryHooks",
    "create_telemetry_plugin",
    "PinnedEnvManager",
    "create_pinned_env_manager",
    "CompactionHooks",
    "create_compaction_hooks",
    "PromptCompositionHooks",
    "create_prompt_composition_hooks",
    "LazyPluginManager",
    "OptimizedHookBus",
    "PerformanceMetrics",
    "PluginSystemInitializer",
    "create_optimized_plugin_system",
    "get_plugin_manager",
    "get_hook_bus",
    "get_plugin_system",
    "initialize_plugin_system",
]

# Version
__version__ = "1.0.0"
