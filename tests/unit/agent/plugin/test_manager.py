"""Tests for PluginManager."""

import tempfile
from pathlib import Path

from zcoder.agent.plugin.loader import PluginLoader
from zcoder.agent.plugin.manager import PluginManager
from zcoder.agent.plugin.tier import PluginTier


class TestPluginManager:
    """Tests for PluginManager."""

    def test_load_all_empty(self):
        """Test loading with no plugins."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = PluginLoader(plugin_dirs=[Path(tmpdir)])
            manager = PluginManager(loader=loader)
            manager.load_all()
            assert len(manager.get_all_plugins_ordered()) == 0

    def test_tier_ordering(self):
        """Test plugins are ordered by tier precedence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir)

            # Create plugins in different tiers
            for tier_name in ["prepend", "user", "append", "builtin"]:
                pdir = plugin_dir / f"plugin_{tier_name}"
                pdir.mkdir()
                (pdir / "manifest.json").write_text(
                    f'{{"name": "plugin_{tier_name}", "version": "1.0.0", "tier": "{tier_name}"}}'
                )

            loader = PluginLoader(plugin_dirs=[plugin_dir])
            manager = PluginManager(loader=loader)
            manager.load_all()

            ordered = manager.get_all_plugins_ordered()
            assert len(ordered) == 4
            assert ordered[0].manifest.tier == "prepend"
            assert ordered[1].manifest.tier == "user"
            assert ordered[2].manifest.tier == "append"
            assert ordered[3].manifest.tier == "builtin"

    def test_get_plugins_for_tier(self):
        """Test getting plugins for specific tier."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir)
            pdir = plugin_dir / "plugin_user"
            pdir.mkdir()
            (pdir / "manifest.json").write_text('{"name": "plugin_user", "version": "1.0.0", "tier": "user"}')

            loader = PluginLoader(plugin_dirs=[plugin_dir])
            manager = PluginManager(loader=loader)
            manager.load_all()

            user_plugins = manager.get_plugins_for_tier(PluginTier.USER)
            assert len(user_plugins) == 1
            assert user_plugins[0].manifest.name == "plugin_user"

            prepend_plugins = manager.get_plugins_for_tier(PluginTier.PREPEND)
            assert len(prepend_plugins) == 0

    def test_get_plugin_by_name(self):
        """Test getting plugin by name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir)
            pdir = plugin_dir / "my_plugin"
            pdir.mkdir()
            (pdir / "manifest.json").write_text('{"name": "my_plugin", "version": "1.0.0"}')

            loader = PluginLoader(plugin_dirs=[plugin_dir])
            manager = PluginManager(loader=loader)
            manager.load_all()

            plugin = manager.get_plugin("my_plugin")
            assert plugin is not None
            assert plugin.manifest.name == "my_plugin"

            missing = manager.get_plugin("nonexistent")
            assert missing is None

    def test_get_hooks_for_event(self):
        """Test getting hooks for event in tier order."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir)

            # Prepend tier plugin with hook
            p1 = plugin_dir / "prepend_plugin"
            p1.mkdir()
            (p1 / "manifest.json").write_text(
                '{"name": "prepend_plugin", "version": "1.0.0", "tier": "prepend", "hooks": {"tool.call": [{"command": "hook1"}]}}'
            )
            (p1 / "hooks.py").write_text("def hook1(args): pass")

            # User tier plugin with hook
            p2 = plugin_dir / "user_plugin"
            p2.mkdir()
            (p2 / "manifest.json").write_text(
                '{"name": "user_plugin", "version": "1.0.0", "tier": "user", "hooks": {"tool.call": [{"command": "hook2"}]}}'
            )
            (p2 / "hooks.py").write_text("def hook2(args): pass")

            loader = PluginLoader(plugin_dirs=[plugin_dir])
            manager = PluginManager(loader=loader)
            manager.load_all()

            hooks = manager.get_hooks_for_event("tool.call")
            assert len(hooks) == 2
            # Prepend should come first
            assert hooks[0][0].manifest.name == "prepend_plugin"
            assert hooks[1][0].manifest.name == "user_plugin"

    def test_get_tools_first_wins(self):
        """Test that first (highest precedence) tool wins."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir)

            # Prepend tier defines tool
            p1 = plugin_dir / "prepend_plugin"
            p1.mkdir()
            (p1 / "manifest.json").write_text(
                '{"name": "prepend_plugin", "version": "1.0.0", "tier": "prepend", "tools": {"shared_tool": {"description": "Prepend"}}}'
            )
            (p1 / "tools.py").write_text('def shared_tool(args): return "prepend"')

            # User tier defines same tool
            p2 = plugin_dir / "user_plugin"
            p2.mkdir()
            (p2 / "manifest.json").write_text(
                '{"name": "user_plugin", "version": "1.0.0", "tier": "user", "tools": {"shared_tool": {"description": "User"}}}'
            )
            (p2 / "tools.py").write_text('def shared_tool(args): return "user"')

            loader = PluginLoader(plugin_dirs=[plugin_dir])
            manager = PluginManager(loader=loader)
            manager.load_all()

            tools = manager.get_tools()
            assert "shared_tool" in tools
            # Prepend should win
            assert tools["shared_tool"][0].manifest.name == "prepend_plugin"

    def test_get_tools_tier_filter(self):
        """Test getting tools filtered by tier."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir)
            p1 = plugin_dir / "prepend_plugin"
            p1.mkdir()
            (p1 / "manifest.json").write_text(
                '{"name": "prepend_plugin", "version": "1.0.0", "tier": "prepend", "tools": {"tool1": {"description": "T1"}}}'
            )

            p2 = plugin_dir / "user_plugin"
            p2.mkdir()
            (p2 / "manifest.json").write_text(
                '{"name": "user_plugin", "version": "1.0.0", "tier": "user", "tools": {"tool2": {"description": "T2"}}}'
            )

            loader = PluginLoader(plugin_dirs=[plugin_dir])
            manager = PluginManager(loader=loader)
            manager.load_all()

            prepend_tools = manager.get_tools(tier_filter=PluginTier.PREPEND)
            assert "tool1" in prepend_tools
            assert "tool2" not in prepend_tools

            user_tools = manager.get_tools(tier_filter=PluginTier.USER)
            assert "tool2" in user_tools
            assert "tool1" not in user_tools

    def test_get_commands(self):
        """Test getting commands."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir)
            p1 = plugin_dir / "prepend_plugin"
            p1.mkdir()
            (p1 / "manifest.json").write_text(
                '{"name": "prepend_plugin", "version": "1.0.0", "tier": "prepend", "commands": {"cmd1": {"description": "C1", "handler": "h1"}}}'
            )

            loader = PluginLoader(plugin_dirs=[plugin_dir])
            manager = PluginManager(loader=loader)
            manager.load_all()

            commands = manager.get_commands()
            assert "cmd1" in commands
            assert commands["cmd1"][0].manifest.name == "prepend_plugin"

    def test_get_mcp_servers(self):
        """Test getting MCP servers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir)
            p1 = plugin_dir / "plugin1"
            p1.mkdir()
            (p1 / "manifest.json").write_text(
                '{"name": "plugin1", "version": "1.0.0", "mcp_servers": {"server1": {"command": "cmd"}}}'
            )

            loader = PluginLoader(plugin_dirs=[plugin_dir])
            manager = PluginManager(loader=loader)
            manager.load_all()

            servers = manager.get_mcp_servers()
            assert "server1" in servers
            assert servers["server1"][0].manifest.name == "plugin1"

    def test_reload(self):
        """Test reloading plugins."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir)
            p1 = plugin_dir / "plugin1"
            p1.mkdir()
            (p1 / "manifest.json").write_text('{"name": "plugin1", "version": "1.0.0"}')

            loader = PluginLoader(plugin_dirs=[plugin_dir])
            manager = PluginManager(loader=loader)
            manager.load_all()

            assert len(manager.get_all_plugins_ordered()) == 1

            # Add another plugin
            p2 = plugin_dir / "plugin2"
            p2.mkdir()
            (p2 / "manifest.json").write_text('{"name": "plugin2", "version": "1.0.0"}')

            manager.reload()
            assert len(manager.get_all_plugins_ordered()) == 2

    def test_get_stats(self):
        """Test getting statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir)
            p1 = plugin_dir / "plugin1"
            p1.mkdir()
            (p1 / "manifest.json").write_text(
                '{"name": "plugin1", "version": "1.0.0", "hooks": {"tool.call": [{"command": "h1"}]}, "tools": {"t1": {"description": "T1"}}, "commands": {"c1": {"description": "C1", "handler": "h1"}}}'
            )

            loader = PluginLoader(plugin_dirs=[plugin_dir])
            manager = PluginManager(loader=loader)
            manager.load_all()

            stats = manager.get_stats()
            assert stats["total_plugins"] == 1
            assert stats["total_hooks"] == 1
            assert stats["total_tools"] == 1
            assert stats["total_commands"] == 1
            assert "user" in stats["by_tier"]
