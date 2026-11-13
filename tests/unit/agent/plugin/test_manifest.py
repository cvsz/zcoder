"""Tests for PluginManifest."""

import pytest

from zcoder.agent.plugin.manifest import (
    CommandConfig,
    HookConfig,
    MCPServerConfig,
    PluginManifest,
    ToolConfig,
)


class TestHookConfig:
    """Tests for HookConfig."""

    def test_default_values(self):
        """Test default values."""
        config = HookConfig(command="echo hello")
        assert config.matcher == "*"
        assert config.command == "echo hello"
        assert config.timeout == 30

    def test_custom_values(self):
        """Test custom values."""
        config = HookConfig(matcher="test_*", command="my_hook", timeout=60)
        assert config.matcher == "test_*"
        assert config.command == "my_hook"
        assert config.timeout == 60

    def test_timeout_validation(self):
        """Test timeout validation raises error for out-of-range values."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            HookConfig(command="x", timeout=0)

        with pytest.raises(ValidationError):
            HookConfig(command="x", timeout=500)

        # Valid values
        config = HookConfig(command="x", timeout=1)
        assert config.timeout == 1

        config = HookConfig(command="x", timeout=300)
        assert config.timeout == 300


class TestToolConfig:
    """Tests for ToolConfig."""

    def test_basic(self):
        """Test basic tool config."""
        config = ToolConfig(description="A test tool", parameters={"arg": {"type": "string"}})
        assert config.description == "A test tool"
        assert config.parameters == {"arg": {"type": "string"}}


class TestCommandConfig:
    """Tests for CommandConfig."""

    def test_basic(self):
        """Test basic command config."""
        config = CommandConfig(description="A test command", handler="my_handler")
        assert config.description == "A test command"
        assert config.handler == "my_handler"


class TestMCPServerConfig:
    """Tests for MCPServerConfig."""

    def test_basic(self):
        """Test basic MCP server config."""
        config = MCPServerConfig(command="python server.py", args=["--port", "8080"], env={"KEY": "val"})
        assert config.command == "python server.py"
        assert config.args == ["--port", "8080"]
        assert config.env == {"KEY": "val"}

    def test_defaults(self):
        """Test default values."""
        config = MCPServerConfig(command="server")
        assert config.args == []
        assert config.env == {}


class TestPluginManifest:
    """Tests for PluginManifest."""

    def test_minimal_valid(self):
        """Test minimal valid manifest."""
        manifest = PluginManifest(name="test-plugin", version="1.0.0")
        assert manifest.name == "test-plugin"
        assert manifest.version == "1.0.0"
        assert manifest.tier == "user"
        assert manifest.description == ""

    def test_full_manifest(self):
        """Test full manifest with all fields."""
        manifest = PluginManifest(
            name="full-plugin",
            version="2.1.0",
            tier="prepend",
            description="A full plugin",
            author="Test Author",
            homepage="https://example.com",
            hooks={"tool.call": [HookConfig(command="pre_tool")]},
            tools={"my_tool": ToolConfig(description="My tool", parameters={})},
            commands={"my_cmd": CommandConfig(description="My command", handler="handle_cmd")},
            mcp_servers={"my_server": MCPServerConfig(command="server.py")},
            settings={"key": "value"},
            dependencies=["dep1", "dep2"],
        )
        assert manifest.name == "full-plugin"
        assert manifest.version == "2.1.0"
        assert manifest.tier == "prepend"
        assert manifest.author == "Test Author"
        assert manifest.homepage == "https://example.com"
        assert "tool.call" in manifest.hooks
        assert "my_tool" in manifest.tools
        assert "my_cmd" in manifest.commands
        assert "my_server" in manifest.mcp_servers
        assert manifest.settings == {"key": "value"}
        assert manifest.dependencies == ["dep1", "dep2"]

    def test_invalid_name(self):
        """Test invalid plugin name."""
        from pydantic import ValidationError

        # Test empty name
        with pytest.raises(ValidationError):
            PluginManifest(name="", version="1.0.0")

        # Test invalid name (special characters not allowed)
        with pytest.raises(ValidationError):
            PluginManifest(name="test@plugin", version="1.0.0")

        # Test invalid name (spaces not allowed)
        with pytest.raises(ValidationError):
            PluginManifest(name="test plugin", version="1.0.0")

    def test_invalid_version(self):
        """Test invalid version format."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            PluginManifest(name="test", version="1.0")
        with pytest.raises(ValidationError):
            PluginManifest(name="test", version="v1.0.0")

    def test_invalid_tier(self):
        """Test invalid tier."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="Unknown tier"):
            PluginManifest(name="test", version="1.0.0", tier="invalid")

    def test_valid_tiers(self):
        """Test all valid tiers."""
        for tier in ["prepend", "user", "append", "builtin"]:
            manifest = PluginManifest(name="test", version="1.0.0", tier=tier)
            assert manifest.tier == tier

    def test_get_hooks_for_event(self):
        """Test getting hooks for event."""
        manifest = PluginManifest(
            name="test",
            version="1.0.0",
            hooks={
                "tool.call": [HookConfig(command="hook1"), HookConfig(command="hook2")],
                "session.start": [HookConfig(command="start_hook")],
            },
        )
        tool_hooks = manifest.get_hooks_for_event("tool.call")
        assert len(tool_hooks) == 2
        assert tool_hooks[0].command == "hook1"
        assert tool_hooks[1].command == "hook2"

        start_hooks = manifest.get_hooks_for_event("session.start")
        assert len(start_hooks) == 1

        empty = manifest.get_hooks_for_event("nonexistent")
        assert empty == []

    def test_to_dict(self):
        """Test serialization to dict."""
        manifest = PluginManifest(name="test", version="1.0.0", tier="prepend")
        data = manifest.to_dict()
        assert data["name"] == "test"
        assert data["version"] == "1.0.0"
        assert data["tier"] == "prepend"

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {"name": "test", "version": "1.0.0", "tier": "append"}
        manifest = PluginManifest.from_dict(data)
        assert manifest.name == "test"
        assert manifest.tier == "append"
