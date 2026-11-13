"""MCP Tier Control for zcoder plugin system.

Implements tier-based filtering for tool.register, tool.list,
agent.offer, and agent.spawn events per claude-code's security model.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from zcoder.agent.plugin.hook_bus import HookBus, HookContext, HookResult
from zcoder.agent.plugin.tier import PluginTier

logger = logging.getLogger(__name__)


@dataclass
class MCPRegistry:
    """Registry for MCP tools and servers with tier awareness."""

    tools: dict[str, dict[str, Any]] = field(default_factory=dict)  # tool_name -> {server, tier, plugin}
    org_allowlist: list[str] = field(default_factory=list)
    managed_mcp_servers: list[str] = field(default_factory=list)
    prepend_plugins: list[str] = field(default_factory=list)
    append_plugins: list[str] = field(default_factory=list)

    def set_org_config(
        self,
        allowlist: list[str],
        managed: list[str],
        prepend: list[str],
        append: list[str],
    ) -> None:
        """Set organization configuration from managed settings."""
        self.org_allowlist = allowlist
        self.managed_mcp_servers = managed
        self.prepend_plugins = prepend
        self.append_plugins = append

    def register_tool(
        self,
        tool_name: str,
        tier: str,
        server: str = "",
        plugin: str = "",
    ) -> bool:
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
                # Use the explicit server parameter, fall back to extracting from tool_name
                server_name = server if server else self._extract_server_name(tool_name)
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
        return [name for name, info in self.tools.items() if info["tier"] == tier_filter.name.lower()]

    def get_tool_info(self, tool_name: str) -> dict[str, Any] | None:
        return self.tools.get(tool_name)


@dataclass
class MCPControlHooks:
    """Hook handlers for MCP tier control events."""

    registry: MCPRegistry
    hook_bus: HookBus

    def __post_init__(self):
        self._register_hooks()

    def _register_hooks(self) -> None:
        # Note: HookBus uses plugin-based hooks, not direct registration
        # These handlers are called from the orchestrator when events fire
        pass

    async def on_tool_register(self, context: HookContext) -> HookResult:
        """Handle tool.register event - filter by tier."""
        tool_name = context.args.get("tool_name", "")
        tier = context.origin_tier.name.lower()  # Convert to string (e.g., "prepend")
        server = context.args.get("server", "")
        plugin = context.args.get("plugin", "")

        allowed = self.registry.register_tool(tool_name, tier, server, plugin)
        if not allowed:
            return HookResult(
                blocked=True,
                message=f"Tool {tool_name} blocked by org MCP policy",
                deny_reason="org_mcp_policy",
            )
        return HookResult()

    async def on_tool_list(self, context: HookContext) -> HookResult:
        """Handle tool.list event - filter tools by tier."""
        # Org tools are listed as org tier listed them
        # User tools that were blocked from registration are not listed
        tier_filter = context.args.get("tier_filter")
        if tier_filter:
            tier_enum = PluginTier.from_string(tier_filter)
            tools = self.registry.list_tools(tier_enum)
        else:
            tools = self.registry.list_tools()

        return HookResult(
            modified_args={"tools": tools},
        )

    async def on_agent_offer(self, context: HookContext) -> HookResult:
        """Handle agent.offer event - prepend/append continue past user tier."""
        # Prepend/append tier agents continue past user tier
        if context.origin_tier in (PluginTier.PREPEND, PluginTier.APPEND):
            return HookResult(modified_args={"continue_past_user_tier": True})
        return HookResult()

    async def on_agent_spawn(self, context: HookContext) -> HookResult:
        """Handle agent.spawn event - prepend/append continue past user tier."""
        if context.origin_tier in (PluginTier.PREPEND, PluginTier.APPEND):
            return HookResult(modified_args={"continue_past_user_tier": True})
        return HookResult()

    async def on_tool_describe(self, context: HookContext) -> HookResult:
        """Handle tool.describe event - prepend/append continue past user tier."""
        if context.origin_tier in (PluginTier.PREPEND, PluginTier.APPEND):
            return HookResult(modified_args={"continue_past_user_tier": True})
        return HookResult()

    async def on_command_describe(self, context: HookContext) -> HookResult:
        """Handle command.describe event - prepend/append continue past user tier."""
        if context.origin_tier in (PluginTier.PREPEND, PluginTier.APPEND):
            return HookResult(modified_args={"continue_past_user_tier": True})
        return HookResult()


def create_mcp_control(
    hook_bus: HookBus,
    org_allowlist: list[str] | None = None,
    managed_servers: list[str] | None = None,
    prepend_plugins: list[str] | None = None,
    append_plugins: list[str] | None = None,
) -> MCPControlHooks:
    """Create MCP control with organization configuration."""
    registry = MCPRegistry()
    registry.set_org_config(
        allowlist=org_allowlist or [],
        managed=managed_servers or [],
        prepend=prepend_plugins or [],
        append=append_plugins or [],
    )
    return MCPControlHooks(registry=registry, hook_bus=hook_bus)