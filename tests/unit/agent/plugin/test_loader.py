"""Tests for PluginLoader."""

import tempfile
from pathlib import Path

import pytest

from zcoder.agent.plugin.loader import LoadedPlugin, PluginLoader
from zcoder.agent.plugin.manifest import PluginManifest


class TestPluginLoader:
    """Tests for PluginLoader."""

    def test_load_manifest(self):
        """Test loading manifest from file."""
        import json

        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir) / "test_plugin"
            plugin_dir.mkdir()

            manifest = PluginManifest(name="test", version="1.0.0", tier="user")
            (plugin_dir / "manifest.json").write_text(json.dumps(manifest.to_dict()))

            loader = PluginLoader()
            loaded = loader.load_manifest(plugin_dir)
            assert loaded.name == "test"
            assert loaded.version == "1.0.0"

    def test_load_manifest_not_found(self):
        """Test loading non-existent manifest raises error."""
        loader = PluginLoader()
        with pytest.raises(FileNotFoundError):
            loader.load_manifest(Path("/nonexistent"))

    def test_discover_plugins(self):
        """Test discovering plugins in directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir) / "plugins"
            plugin_dir.mkdir()

            # Create valid plugin
            plugin1 = plugin_dir / "plugin1"
            plugin1.mkdir()
            PluginManifest(name="plugin1", version="1.0.0").to_dict()
            (plugin1 / "manifest.json").write_text('{"name": "plugin1", "version": "1.0.0"}')

            # Create invalid (no manifest)
            plugin2 = plugin_dir / "plugin2"
            plugin2.mkdir()

            loader = PluginLoader(plugin_dirs=[plugin_dir])
            discovered = loader.discover_plugins()
            assert len(discovered) == 1
            assert discovered[0].name == "plugin1"

    def test_load_from_directory_minimal(self):
        """Test loading minimal plugin from directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir) / "test_plugin"
            plugin_dir.mkdir()
            (plugin_dir / "manifest.json").write_text('{"name": "test", "version": "1.0.0"}')

            loader = PluginLoader()
            plugin = loader.load_from_directory(plugin_dir)
            assert isinstance(plugin, LoadedPlugin)
            assert plugin.manifest.name == "test"
            assert plugin.hooks == {}
            assert plugin.tools == {}
            assert plugin.commands == {}

    def test_load_hooks_module(self):
        """Test loading hooks from hooks.py."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir) / "test_plugin"
            plugin_dir.mkdir()
            (plugin_dir / "manifest.json").write_text(
                '{"name": "test", "version": "1.0.0", "hooks": {"tool.call": [{"command": "my_hook"}]}}'
            )
            (plugin_dir / "hooks.py").write_text("""
def my_hook(args):
    return {"result": "ok"}
""")

            loader = PluginLoader()
            plugin = loader.load_from_directory(plugin_dir)
            assert "tool.call" in plugin.hooks
            assert len(plugin.hooks["tool.call"]) == 1
            hook = plugin.hooks["tool.call"][0]
            assert hook.config.command == "my_hook"
            assert hook.handler is not None

    def test_load_tools_module(self):
        """Test loading tools from tools.py."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir) / "test_plugin"
            plugin_dir.mkdir()
            (plugin_dir / "manifest.json").write_text(
                '{"name": "test", "version": "1.0.0", "tools": {"my_tool": {"description": "A tool"}}}'
            )
            (plugin_dir / "tools.py").write_text("""
def my_tool(args):
    return {"result": "ok"}
""")

            loader = PluginLoader()
            plugin = loader.load_from_directory(plugin_dir)
            assert "my_tool" in plugin.tools
            tool = plugin.tools["my_tool"]
            assert tool.handler is not None

    def test_load_commands_module(self):
        """Test loading commands from commands.py."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir) / "test_plugin"
            plugin_dir.mkdir()
            (plugin_dir / "manifest.json").write_text(
                '{"name": "test", "version": "1.0.0", "commands": {"my_cmd": {"description": "A cmd", "handler": "handle_cmd"}}}'
            )
            (plugin_dir / "commands.py").write_text("""
def handle_cmd(args):
    return {"result": "ok"}
""")

            loader = PluginLoader()
            plugin = loader.load_from_directory(plugin_dir)
            assert "my_cmd" in plugin.commands
            cmd = plugin.commands["my_cmd"]
            assert cmd.handler is not None
