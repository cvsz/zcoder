"""Plugin Marketplace for Phase 17.

Provides plugin discovery, loading, and management capabilities
for ZCoder extensions.
"""

from zcoder.agent.plugins.cli import cmd_plugin, setup_parser
from zcoder.agent.plugins.manifest import PluginManifest, PluginType, PluginVisibility
from zcoder.agent.plugins.registry import PluginInfo, PluginRegistry, create_default_registry

__all__ = [
    "PluginManifest",
    "PluginType",
    "PluginVisibility",
    "PluginRegistry",
    "PluginInfo",
    "create_default_registry",
    "cmd_plugin",
    "setup_parser",
]
