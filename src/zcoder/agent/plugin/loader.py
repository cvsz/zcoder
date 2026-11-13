"""Plugin loader for zcoder.

Loads plugins from directories, validates manifests, and prepares
hook/tool/command modules for execution.
"""

import importlib.util
import logging
import shutil
import subprocess  # nosec B404 - git operations with validated input
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from zcoder.agent.plugin.manifest import HookConfig, PluginManifest

logger = logging.getLogger(__name__)


@dataclass
class LoadedHook:
    """A loaded hook with its configuration."""

    config: HookConfig
    module: Any = None
    handler: Any = None


@dataclass
class LoadedTool:
    """A loaded tool with its configuration."""

    config: Any  # ToolConfig
    handler: Any
    schema: dict[str, Any]


@dataclass
class LoadedCommand:
    """A loaded command with its configuration."""

    config: Any  # CommandConfig
    handler: Any


@dataclass
class LoadedPlugin:
    """A fully loaded plugin ready for use."""

    manifest: PluginManifest
    hooks: dict[str, list[LoadedHook]] = field(default_factory=dict)
    tools: dict[str, LoadedTool] = field(default_factory=dict)
    commands: dict[str, LoadedCommand] = field(default_factory=dict)
    mcp_servers: dict[str, Any] = field(default_factory=dict)
    module: Any = None


class PluginLoader:
    """Loads plugins from directories and git repositories."""

    DEFAULT_PLUGIN_DIRS = [
        Path.home() / ".zcoder" / "plugins",
        Path("/usr/local/share/zcoder/plugins"),
        Path("/opt/zcoder/plugins"),
    ]

    def __init__(self, plugin_dirs: list[Path] | None = None):
        self.plugin_dirs = plugin_dirs or self.DEFAULT_PLUGIN_DIRS
        self._builtin_plugins_dir = Path(__file__).parent.parent.parent / "plugins"
        self._git_cache_dir = Path.home() / ".zcoder" / "plugin-cache"

    def _is_git_url(self, url: str) -> bool:
        """Check if a string is a git repository URL."""
        parsed = urlparse(url)
        return parsed.scheme in ("git", "http", "https", "ssh") or url.endswith(".git")

    def _clone_git_repo(self, url: str, target_dir: Path, branch: str | None = None, depth: int = 1) -> Path:
        """Clone a git repository to a target directory."""
        target_dir.parent.mkdir(parents=True, exist_ok=True)

        # Use cache directory for git operations
        self._git_cache_dir.mkdir(parents=True, exist_ok=True)

        # Generate cache key from URL
        cache_key = url.replace("://", "_").replace("/", "_").replace(".", "_").replace("@", "_")
        cache_dir = self._git_cache_dir / cache_key

        if cache_dir.exists():
            # Update existing cache
            logger.info(f"Updating cached git repo: {url}")
            subprocess.run(
                ["git", "-C", str(cache_dir), "fetch", "--all", "--tags"],
                check=True,
                capture_output=True,
                timeout=60,
            )
        else:
            # Clone with depth for faster operation
            logger.info(f"Cloning git repo: {url}")
            clone_cmd = ["git", "clone", "--depth", str(depth)]
            if branch:
                clone_cmd.extend(["--branch", branch])
            clone_cmd.extend([url, str(cache_dir)])
            subprocess.run(clone_cmd, check=True, capture_output=True, timeout=120)

        # Copy from cache to target directory
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(cache_dir, target_dir)

        # Checkout specific branch if provided
        if branch:
            subprocess.run(
                ["git", "-C", str(target_dir), "checkout", branch],
                check=True,
                capture_output=True,
                timeout=30,
            )

        return target_dir

    def load_from_git(self, url: str, branch: str | None = None, depth: int = 1) -> LoadedPlugin:
        """Load a plugin from a git repository URL."""
        if not self._is_git_url(url):
            raise ValueError(f"Not a valid git URL: {url}")

        # Create temporary directory for the plugin
        with tempfile.TemporaryDirectory(prefix="zcoder-plugin-") as tmpdir:
            plugin_path = Path(tmpdir) / "plugin"
            self._clone_git_repo(url, plugin_path, branch, depth)

            # Load the plugin from the cloned directory
            return self.load_from_directory(plugin_path)

    def load_manifest(self, plugin_path: Path) -> PluginManifest:
        """Load and validate plugin manifest."""
        manifest_path = plugin_path / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found: {manifest_path}")
        return PluginManifest.from_file(str(manifest_path))

    def load_from_directory(self, plugin_path: Path) -> LoadedPlugin:
        """Load a complete plugin from its directory."""
        manifest = self.load_manifest(plugin_path)

        # Add plugin directory to sys.path for imports
        plugin_dir_str = str(plugin_path)
        if plugin_dir_str not in sys.path:
            sys.path.insert(0, plugin_dir_str)

        try:
            # Load hooks
            hooks = self._load_hooks(plugin_path, manifest.hooks)

            # Load tools
            tools = self._load_tools(plugin_path, manifest.tools)

            # Load commands
            commands = self._load_commands(plugin_path, manifest.commands)

            # Load MCP servers
            mcp_servers = self._load_mcp_servers(plugin_path, manifest.mcp_servers)

            return LoadedPlugin(
                manifest=manifest,
                hooks=hooks,
                tools=tools,
                commands=commands,
                mcp_servers=mcp_servers,
            )
        except Exception as e:
            logger.error(f"Failed to load plugin {manifest.name}: {e}")
            raise
        finally:
            if plugin_dir_str in sys.path:
                sys.path.remove(plugin_dir_str)

    def _load_hooks(
        self, plugin_path: Path, hook_configs: dict[str, list[HookConfig]]
    ) -> dict[str, list[LoadedHook]]:
        """Load hook modules for all events."""
        hooks: dict[str, list[LoadedHook]] = {}

        # Look for hooks module
        hooks_file = plugin_path / "hooks.py"
        hooks_module = None
        if hooks_file.exists():
            hooks_module = self._import_module(hooks_file, f"{hooks_file.stem}_{plugin_path.name}")

        for event_name, configs in hook_configs.items():
            hooks[event_name] = []
            for config in configs:
                loaded_hook = LoadedHook(config=config)
                if hooks_module and hasattr(hooks_module, config.command):
                    loaded_hook.handler = getattr(hooks_module, config.command)
                hooks[event_name].append(loaded_hook)

        return hooks

    def _load_tools(self, plugin_path: Path, tool_configs: dict[str, Any]) -> dict[str, LoadedTool]:
        """Load tool implementations."""
        tools: dict[str, LoadedTool] = {}

        # Look for tools module
        tools_file = plugin_path / "tools.py"
        tools_module = None
        if tools_file.exists():
            tools_module = self._import_module(tools_file, f"{tools_file.stem}_{plugin_path.name}")

        for tool_name, config in tool_configs.items():
            handler = None
            schema = {"type": "object", "properties": config.parameters}

            if tools_module and hasattr(tools_module, tool_name):
                handler = getattr(tools_module, tool_name)

            tools[tool_name] = LoadedTool(config=config, handler=handler, schema=schema)

        return tools

    def _load_commands(self, plugin_path: Path, command_configs: dict[str, Any]) -> dict[str, LoadedCommand]:
        """Load command handlers."""
        commands: dict[str, LoadedCommand] = {}

        # Look for commands module
        commands_file = plugin_path / "commands.py"
        commands_module = None
        if commands_file.exists():
            commands_module = self._import_module(commands_file, f"{commands_file.stem}_{plugin_path.name}")

        for cmd_name, config in command_configs.items():
            handler = None
            if commands_module and hasattr(commands_module, config.handler):
                handler = getattr(commands_module, config.handler)

            commands[cmd_name] = LoadedCommand(config=config, handler=handler)

        return commands

    def _load_mcp_servers(self, plugin_path: Path, mcp_configs: dict[str, Any]) -> dict[str, Any]:
        """Load MCP server configurations."""
        # MCP servers are configured via manifest, not loaded as modules
        return {name: config.model_dump() for name, config in mcp_configs.items()}

    def _import_module(self, file_path: Path, module_name: str) -> Any:
        """Import a Python module from file."""
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load module from {file_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    def discover_plugins(self) -> list[Path]:
        """Discover all plugin directories with valid manifests."""
        plugins = []

        # Add builtin plugins directory if it exists
        all_dirs = list(self.plugin_dirs)
        if self._builtin_plugins_dir.exists():
            all_dirs.append(self._builtin_plugins_dir)

        for plugin_dir in all_dirs:
            if not plugin_dir.exists():
                continue
            try:
                for item in plugin_dir.iterdir():
                    if item.is_dir() and (item / "manifest.json").exists():
                        plugins.append(item)
            except PermissionError:
                logger.warning(f"Permission denied accessing plugin directory: {plugin_dir}")
            except Exception as e:
                logger.warning(f"Error scanning plugin directory {plugin_dir}: {e}")

        return plugins

    def load_all_plugins(self) -> list[LoadedPlugin]:
        """Discover and load all plugins."""
        loaded = []
        for plugin_path in self.discover_plugins():
            try:
                plugin = self.load_from_directory(plugin_path)
                loaded.append(plugin)
                logger.info(
                    f"Loaded plugin: {plugin.manifest.name} v{plugin.manifest.version} (tier: {plugin.manifest.tier})"
                )
            except Exception as e:
                logger.error(f"Failed to load plugin from {plugin_path}: {e}")
        return loaded
