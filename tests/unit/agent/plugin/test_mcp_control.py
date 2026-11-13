"""Tests for MCP control."""

import pytest

from zcoder.agent.plugin.mcp_control import MCPRegistry, create_mcp_control
from zcoder.agent.plugin.tier import PluginTier


class TestMCPRegistry:
    """Tests for MCPRegistry."""

    def test_register_tool_prepend(self):
        """Test prepend tier always allowed."""
        registry = MCPRegistry()
        allowed = registry.register_tool("mcp__server__tool", "prepend", "server", "plugin")
        assert allowed is True
        assert "mcp__server__tool" in registry.tools

    def test_register_tool_append(self):
        """Test append tier always allowed."""
        registry = MCPRegistry()
        allowed = registry.register_tool("mcp__server__tool", "append", "server", "plugin")
        assert allowed is True

    def test_register_tool_builtin(self):
        """Test builtin tier always allowed."""
        registry = MCPRegistry()
        allowed = registry.register_tool("mcp__server__tool", "builtin", "server", "plugin")
        assert allowed is True

    def test_register_tool_user_no_allowlist_blocks_org(self):
        """Test user tier blocked when no allowlist and looks like org tool."""
        registry = MCPRegistry()
        registry.managed_mcp_servers = ["org_server"]

        # Tool that looks like org tool should be blocked
        allowed = registry.register_tool("mcp__org_server__tool", "user", "org_server", "user_plugin")
        assert allowed is False
        assert "mcp__org_server__tool" not in registry.tools

    def test_register_tool_user_no_allowlist_allows_regular(self):
        """Test user tier allowed for non-org tools when no allowlist."""
        registry = MCPRegistry()
        registry.managed_mcp_servers = ["org_server"]

        # Regular tool should be allowed
        allowed = registry.register_tool("my_custom_tool", "user", "", "user_plugin")
        assert allowed is True
        assert "my_custom_tool" in registry.tools

    def test_register_tool_user_with_allowlist(self):
        """Test user tier with allowlist."""
        registry = MCPRegistry()
        registry.org_allowlist = ["allowed_server"]

        # Server in allowlist
        allowed = registry.register_tool("mcp__allowed_server__tool", "user", "allowed_server", "user_plugin")
        assert allowed is True

        # Server not in allowlist
        allowed = registry.register_tool("mcp__blocked_server__tool", "user", "blocked_server", "user_plugin")
        assert allowed is False

    def test_register_tool_prepend_plugin_lookalike(self):
        """Test user tier blocked for prepend plugin lookalikes."""
        registry = MCPRegistry()
        registry.prepend_plugins = ["prepend_plugin"]

        allowed = registry.register_tool("mcp__plugin_prepend_plugin__tool", "user", "server", "user_plugin")
        assert allowed is False

    def test_register_tool_append_plugin_lookalike(self):
        """Test user tier blocked for append plugin lookalikes."""
        registry = MCPRegistry()
        registry.append_plugins = ["append_plugin"]

        allowed = registry.register_tool("mcp__plugin_append_plugin__tool", "user", "server", "user_plugin")
        assert allowed is False

    def test_list_tools_all(self):
        """Test listing all tools."""
        registry = MCPRegistry()
        registry.register_tool("tool1", "prepend", "server1")
        registry.register_tool("tool2", "user", "server2")

        tools = registry.list_tools()
        assert "tool1" in tools
        assert "tool2" in tools

    def test_list_tools_tier_filter(self):
        """Test listing tools with tier filter."""
        registry = MCPRegistry()
        registry.register_tool("tool1", "prepend", "server1")
        registry.register_tool("tool2", "user", "server2")

        prepend_tools = registry.list_tools(PluginTier.PREPEND)
        assert "tool1" in prepend_tools
        assert "tool2" not in prepend_tools

        user_tools = registry.list_tools(PluginTier.USER)
        assert "tool2" in user_tools
        assert "tool1" not in user_tools

    def test_get_tool_info(self):
        """Test getting tool info."""
        registry = MCPRegistry()
        registry.register_tool("my_tool", "prepend", "server1", "plugin1")

        info = registry.get_tool_info("my_tool")
        assert info is not None
        assert info["server"] == "server1"
        assert info["tier"] == "prepend"
        assert info["plugin"] == "plugin1"

    def test_extract_server_name(self):
        """Test server name extraction."""
        registry = MCPRegistry()
        assert registry._extract_server_name("mcp__server__tool") == "server"
        assert registry._extract_server_name("mcp__my_server__tool") == "my_server"
        assert registry._extract_server_name("regular_tool") == ""


class TestMCPControlHooks:
    """Tests for MCPControlHooks."""

    @pytest.fixture
    def mcp_control(self):
        """Create MCP control fixture."""
        from zcoder.agent.plugin.hook_bus import HookBus
        from zcoder.agent.plugin.manager import PluginManager

        manager = PluginManager()
        bus = HookBus(manager)
        mcp_control = create_mcp_control(
            bus,
            org_allowlist=["allowed"],
            managed_servers=["managed"],
            prepend_plugins=["prepend"],
            append_plugins=["append"],
        )
        # Create a fresh registry for each test
        mcp_control.registry = MCPRegistry()
        mcp_control.registry.set_org_config(
            allowlist=["allowed"],
            managed=["managed"],
            prepend=["prepend"],
            append=["append"],
        )
        return mcp_control

    def test_on_tool_register_prepend_allowed(self, mcp_control):
        """Test prepend tier tool registration allowed."""
        # This would need the hook to be called via hook_bus
        # For now test registry directly
        allowed = mcp_control.registry.register_tool("tool1", "prepend", "server1", "plugin1")
        assert allowed is True

    def test_on_tool_register_user_blocked(self, mcp_control):
        """Test user tier tool registration blocked for managed server."""
        allowed = mcp_control.registry.register_tool("mcp__managed__tool", "user", "managed", "user_plugin")
        assert allowed is False

    def test_on_tool_list(self, mcp_control):
        """Test tool list."""
        # Use different names to avoid collision with fixture pre-registration
        # Use "allowed" server which is in the fixture's org_allowlist
        mcp_control.registry.register_tool("tool_list_1", "prepend", "server1")
        mcp_control.registry.register_tool("tool_list_2", "user", "allowed")

        tools = mcp_control.registry.list_tools()
        assert "tool_list_1" in tools
        assert "tool_list_2" in tools
