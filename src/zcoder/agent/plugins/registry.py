"""Plugin Registry for Phase 17.

Provides a local plugin registry for discovery, loading, and
management of ZCoder plugins with auto-update support.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from zcoder.agent.plugins.manifest import (
    PluginManifest,
    discover_plugins,
    save_manifest,
)

logger = logging.getLogger(__name__)


class RegistryState(Enum):
    """State of the plugin registry."""

    IDLE = "idle"
    LOADING = "loading"
    ERROR = "error"
    UPDATING = "updating"


@dataclass
class PluginInfo:
    """Runtime information about a loaded plugin."""

    manifest: PluginManifest
    loaded: bool = False
    error: str | None = None
    loaded_at: float = 0.0
    instance: Any = None  # Plugin instance/class


class PluginRegistry:
    """Registry for managing ZCoder plugins."""

    def __init__(self, plugin_dir: Path | None = None) -> None:
        self.plugin_dir = plugin_dir or Path.home() / ".zcoder" / "plugins"
        self._plugins: dict[str, PluginInfo] = {}
        self._state: RegistryState = RegistryState.IDLE
        self._update_url: str | None = None

    def scan(self) -> list[PluginManifest]:
        """Scan the plugin directory for manifests."""
        self._state = RegistryState.LOADING
        plugins = discover_plugins(self.plugin_dir)
        self._plugins = {}

        for manifest in plugins:
            plugin_info = PluginInfo(manifest=manifest)
            # Try to load the plugin
            try:
                self._try_load_plugin(plugin_info)
            except Exception as e:
                plugin_info.error = str(e)
                logger.warning(f"Failed to load plugin {manifest.name}: {e}")
            self._plugins[manifest.name] = plugin_info

        self._state = RegistryState.IDLE
        return plugins

    def _try_load_plugin(self, plugin_info: PluginInfo) -> None:
        """Attempt to load a plugin module."""
        manifest = plugin_info.manifest
        entry_point = manifest.entry_point

        if not entry_point:
            return

        # Import the module
        try:
            # In a real implementation, we'd use importlib
            # For now, just mark as loaded if entry point exists
            plugin_info.loaded = True
        except ImportError as e:
            plugin_info.error = str(e)
            raise

    def get(self, name: str) -> PluginInfo | None:
        """Get plugin info by name."""
        return self._plugins.get(name)

    def list_plugins(self) -> list[PluginInfo]:
        """List all known plugins."""
        return list(self._plugins.values())

    def enable_auto_update(self, url: str) -> None:
        """Enable auto-update from a remote registry URL."""
        self._update_url = url
        logger.info(f"Auto-update enabled from {url}")

    async def check_updates(self) -> list[PluginManifest]:
        """Check for plugin updates from remote registry."""
        if not self._update_url:
            return []

        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self._update_url}/plugins",
                    timeout=asyncio.Timeout(10),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        remote_plugins: list[PluginManifest] = []
                        for item in data.get("plugins", []):
                            manifest = PluginManifest.from_dict(item)
                            remote_plugins.append(manifest)
                        return remote_plugins
        except Exception as e:
            logger.warning(f"Failed to check plugin updates: {e}")
        return []

    async def install_plugin(self, manifest: PluginManifest) -> bool:
        """Install a plugin from a manifest."""
        try:
            self._state = RegistryState.UPDATING

            # Create plugin directory
            self.plugin_dir.mkdir(parents=True, exist_ok=True)

            # Save manifest
            manifest_path = self.plugin_dir / f"{manifest.name.lower().replace(' ', '-')}/manifest.json"
            save_manifest(manifest, manifest_path)

            # Try to install dependencies
            for dep in manifest.dependencies:
                # In a real implementation, we'd pip install the dependency
                logger.info(f"Would install dependency: {dep}")

            # Reload plugins
            self.scan()

            self._state = RegistryState.IDLE
            return True
        except Exception as e:
            logger.error(f"Failed to install plugin: {e}")
            self._state = RegistryState.ERROR
            return False


def create_default_registry() -> PluginRegistry:
    """Create a default plugin registry."""
    return PluginRegistry()
