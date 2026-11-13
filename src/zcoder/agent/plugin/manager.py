"""Plugin manager for zcoder.

Manages loaded plugins, organizes them by tier, and provides
access to hooks, tools, and commands in tier precedence order.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from zcoder.agent.plugin.loader import LoadedPlugin, PluginLoader
from zcoder.agent.plugin.tier import PluginTier

logger = logging.getLogger(__name__)


@dataclass
class PluginManager:
    """Manages all loaded plugins organized by tier."""

    loader: PluginLoader = field(default_factory=PluginLoader)
    _plugins_by_tier: dict[PluginTier, list[LoadedPlugin]] = field(default_factory=dict)
    _plugins_by_name: dict[str, LoadedPlugin] = field(default_factory=dict)
    _loaded: bool = False

    # Enterprise allowlist/blocklist configuration
    allowlist: list[str] = field(default_factory=list)
    blocklist: list[str] = field(default_factory=list)
    allow_git_plugins: bool = True

    def __post_init__(self):
        for tier in PluginTier:
            self._plugins_by_tier[tier] = []

    def _is_allowed(self, plugin_name: str) -> bool:
        """Check if a plugin is allowed based on allowlist/blocklist."""
        if self.blocklist and plugin_name in self.blocklist:
            return False
        if self.allowlist and plugin_name not in self.allowlist:
            return False
        return True

    def load_all(self) -> None:
        """Discover and load all plugins."""
        if self._loaded:
            return

        loaded_plugins = self.loader.load_all_plugins()

        for plugin in loaded_plugins:
            if not self._is_allowed(plugin.manifest.name):
                logger.info(f"Plugin {plugin.manifest.name} blocked by allowlist/blocklist policy")
                continue
            tier = PluginTier.from_string(plugin.manifest.tier)
            self._plugins_by_tier[tier].append(plugin)
            self._plugins_by_name[plugin.manifest.name] = plugin

        self._loaded = True
        logger.info(f"Plugin manager loaded {len(self._plugins_by_name)} plugins")

    def _ensure_loaded(self) -> None:
        """Ensure plugins are loaded (lazy loading)."""
        if not self._loaded:
            self.load_all()

    def get_plugins_for_tier(self, tier: PluginTier) -> list[LoadedPlugin]:
        """Get all plugins for a specific tier."""
        self._ensure_loaded()
        return self._plugins_by_tier.get(tier, [])

    def get_all_plugins_ordered(self) -> list[LoadedPlugin]:
        """Get all plugins in tier precedence order: prepend -> user -> append -> builtin."""
        self._ensure_loaded()
        result = []
        for tier in PluginTier.all_tiers():
            result.extend(self._plugins_by_tier[tier])
        return result

    def get_plugin(self, name: str) -> LoadedPlugin | None:
        """Get a specific plugin by name."""
        self._ensure_loaded()
        return self._plugins_by_name.get(name)

    def get_hooks_for_event(self, event: str) -> list[tuple[LoadedPlugin, Any]]:
        """Get all hooks for an event, ordered by tier precedence."""
        self._ensure_loaded()
        hooks = []
        for plugin in self.get_all_plugins_ordered():
            if event in plugin.hooks:
                for hook in plugin.hooks[event]:
                    hooks.append((plugin, hook))
        return hooks

    def get_tools(self, tier_filter: PluginTier | None = None) -> dict[str, tuple[LoadedPlugin, Any]]:
        """Get all tools, optionally filtered by tier."""
        self._ensure_loaded()
        tools = {}
        for plugin in self.get_all_plugins_ordered():
            plugin_tier = PluginTier.from_string(plugin.manifest.tier)
            if tier_filter is not None and plugin_tier != tier_filter:
                continue
            for tool_name, tool in plugin.tools.items():
                if tool_name not in tools:  # First (highest precedence) wins
                    tools[tool_name] = (plugin, tool)
        return tools

    def get_commands(self, tier_filter: PluginTier | None = None) -> dict[str, tuple[LoadedPlugin, Any]]:
        """Get all commands, optionally filtered by tier."""
        self._ensure_loaded()
        commands = {}
        for plugin in self.get_all_plugins_ordered():
            plugin_tier = PluginTier.from_string(plugin.manifest.tier)
            if tier_filter is not None and plugin_tier != tier_filter:
                continue
            for cmd_name, cmd in plugin.commands.items():
                if cmd_name not in commands:
                    commands[cmd_name] = (plugin, cmd)
        return commands

    def get_mcp_servers(self) -> dict[str, tuple[LoadedPlugin, dict]]:
        """Get all MCP servers from all plugins."""
        self._ensure_loaded()
        servers = {}
        for plugin in self.get_all_plugins_ordered():
            for server_name, config in plugin.mcp_servers.items():
                if server_name not in servers:
                    servers[server_name] = (plugin, config)
        return servers

    def get_plugins_by_tier(self) -> dict[PluginTier, list[LoadedPlugin]]:
        """Get all plugins grouped by tier."""
        self._ensure_loaded()
        return dict(self._plugins_by_tier)

    def reload(self) -> None:
        """Reload all plugins (clear cache and reload)."""
        self._plugins_by_tier.clear()
        self._plugins_by_name.clear()
        for tier in PluginTier:
            self._plugins_by_tier[tier] = []
        self._loaded = False
        self.load_all()

    def get_stats(self) -> dict[str, Any]:
        """Get plugin manager statistics."""
        self._ensure_loaded()
        stats: dict[str, Any] = {
            "total_plugins": sum(len(p) for p in self._plugins_by_tier.values()),
            "by_tier": {},
            "total_hooks": 0,
            "total_tools": 0,
            "total_commands": 0,
        }
        for tier, plugins in self._plugins_by_tier.items():
            tier_stats: dict[str, Any] = {
                "count": len(plugins),
                "plugins": [p.manifest.name for p in plugins],
                "hooks": 0,
                "tools": 0,
                "commands": 0,
            }
            for plugin in plugins:
                tier_stats["hooks"] += sum(len(h) for h in plugin.hooks.values())
                tier_stats["tools"] += len(plugin.tools)
                tier_stats["commands"] += len(plugin.commands)
            stats["by_tier"][tier.name.lower()] = tier_stats
            stats["total_hooks"] += tier_stats["hooks"]
            stats["total_tools"] += tier_stats["tools"]
            stats["total_commands"] += tier_stats["commands"]
        return stats

    def load_from_git(self, url: str, branch: str | None = None, depth: int = 1) -> LoadedPlugin | None:
        """Load a plugin from a git repository URL."""
        if not self.allow_git_plugins:
            logger.warning(f"Git plugin loading is disabled, skipping {url}")
            return None

        if not self._is_allowed("git-plugin"):
            logger.info(f"Git plugin from {url} blocked by allowlist/blocklist policy")
            return None

        try:
            plugin = self.loader.load_from_git(url, branch=branch, depth=depth)
            tier = PluginTier.from_string(plugin.manifest.tier)
            self._plugins_by_tier[tier].append(plugin)
            self._plugins_by_name[plugin.manifest.name] = plugin
            logger.info(f"Loaded git plugin: {plugin.manifest.name} from {url}")
            return plugin
        except Exception as e:
            logger.error(f"Failed to load git plugin from {url}: {e}")
            raise
