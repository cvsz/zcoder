"""Plugin Marketplace CLI for Phase 17.

Provides CLI commands for plugin management including
install, uninstall, list, and search.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from zcoder.agent.plugins.manifest import load_manifest
from zcoder.agent.plugins.registry import PluginInfo, PluginRegistry

logger = logging.getLogger(__name__)

# Module-level parser for CLI help
plugin_parser: argparse.ArgumentParser | None = None


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    """Setup the plugin CLI parser."""
    global plugin_parser
    plugin_parser = subparsers.add_parser("plugin", help="Plugin marketplace commands")
    plugin_subparsers = plugin_parser.add_subparsers(dest="plugin_command")

    # List command
    list_parser = plugin_subparsers.add_parser("list", help="List installed plugins")
    list_parser.add_argument("--installed", action="store_true", help="Show only installed plugins")

    # Install command
    install_parser = plugin_subparsers.add_parser("install", help="Install a plugin")
    install_parser.add_argument("source", help="Plugin source (path or URL)")
    install_parser.add_argument("--name", help="Override plugin name")
    install_parser.add_argument("--version", help="Override plugin version")

    # Uninstall command
    uninstall_parser = plugin_subparsers.add_parser("uninstall", help="Uninstall a plugin")
    uninstall_parser.add_argument("name", help="Plugin name to uninstall")

    # Info command
    info_parser = plugin_subparsers.add_parser("info", help="Show plugin information")
    info_parser.add_argument("name", help="Plugin name")

    # Search command
    search_parser = plugin_subparsers.add_parser("search", help="Search for plugins")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument(
        "--type", choices=["tool", "agent", "provider", "transform", "view"], help="Filter by plugin type"
    )

    # Update command
    update_parser = plugin_subparsers.add_parser("update", help="Check for plugin updates")
    update_parser.add_argument("--all", action="store_true", help="Check all installed plugins")


def cmd_plugin(args: argparse.Namespace) -> int:
    """Execute a plugin CLI command."""
    command = getattr(args, "plugin_command", None)
    registry = PluginRegistry()

    if command == "list":
        return cmd_plugin_list(args, registry)
    elif command == "install":
        return cmd_plugin_install(args, registry)
    elif command == "uninstall":
        return cmd_plugin_uninstall(args, registry)
    elif command == "info":
        return cmd_plugin_info(args, registry)
    elif command == "search":
        return cmd_plugin_search(args, registry)
    elif command == "update":
        return cmd_plugin_update(args, registry)
    else:
        plugin_parser.print_help()
        return 1


def cmd_plugin_list(args: argparse.Namespace, registry: PluginRegistry) -> int:
    """List plugins command."""
    plugins = registry.list_plugins()
    if not plugins:
        print("No plugins installed.")
        return 0

    print(f"\nInstalled Plugins ({len(plugins)}):")
    print("=" * 60)
    for p in plugins:
        loaded_str = "✓" if p.loaded else "✗"
        error_str = f" ({p.error})" if p.error else ""
        print(f"  [{loaded_str}] {p.manifest.name} v{p.manifest.version}{error_str}")
        if p.manifest.tags:
            print(f"      Tags: {', '.join(p.manifest.tags[:3])}")
    return 0


def cmd_plugin_install(args: argparse.Namespace, registry: PluginRegistry) -> int:
    """Install plugin command."""
    source = args.source

    # Determine if source is a local path or URL
    source_path = Path(source)
    if source_path.exists():
        # Local path - load manifest
        try:
            manifest = load_manifest(source_path)
            print(f"Loading plugin from {source_path}")

            # Install
            success = registry.install_plugin(manifest)
            if success:
                print(f"✓ Plugin '{manifest.name}' installed successfully")
            else:
                print(f"✗ Failed to install plugin '{manifest.name}'")
            return 0 if success else 1
        except Exception as e:
            print(f"✗ Failed to load plugin from {source_path}: {e}")
            return 1
    else:
        # Remote URL or name-based install
        print(f"Installing plugin from remote source: {source}")
        # In a full implementation, this would download from a registry
        print("Remote plugin installation not yet implemented")
        return 0


def cmd_plugin_uninstall(args: argparse.Namespace, registry: PluginRegistry) -> int:
    """Uninstall plugin command."""
    name = args.name
    plugin_info = registry.get(name)

    if plugin_info is None:
        print(f"Plugin '{name}' not found.")
        return 1

    # Check if plugin is loaded
    if plugin_info.loaded:
        print(f"Warning: Plugin '{name}' is currently loaded. Unloading first.")
        plugin_info.loaded = False

    # Remove plugin directory
    plugin_dir = registry.plugin_dir / f"{name.lower().replace(' ', '-')}"
    if plugin_dir.exists():
        import shutil

        shutil.rmtree(plugin_dir)
        print(f"✓ Plugin '{name}' uninstalled successfully")
    else:
        print(f"Plugin '{name}' directory not found, but record removed")

    # Remove from registry
    if name in registry._plugins:
        del registry._plugins[name]

    return 0


def cmd_plugin_info(args: argparse.Namespace, registry: PluginRegistry) -> int:
    """Show plugin info command."""
    name = args.name
    plugin_info = registry.get(name)

    if plugin_info is None:
        print(f"Plugin '{name}' not found in registry.")
        return 1

    manifest = plugin_info.manifest
    print(f"\nPlugin: {manifest.name}")
    print(f"  Version: {manifest.version}")
    print(f"  Type: {manifest.plugin_type.value}")
    print(f"  Author: {manifest.author}")
    print(f"  Description: {manifest.description}")
    print(f"  Visibility: {manifest.visibility.value}")
    print(f"  License: {manifest.license}")
    print(f"  Entry Point: {manifest.entry_point}")
    if manifest.dependencies:
        print(f"  Dependencies: {', '.join(manifest.dependencies)}")
    if manifest.tags:
        print(f"  Tags: {', '.join(manifest.tags)}")
    if manifest.repository:
        print(f"  Repository: {manifest.repository}")
    if manifest.homepage:
        print(f"  Homepage: {manifest.homepage}")

    return 0


def cmd_plugin_search(args: argparse.Namespace, registry: PluginRegistry) -> int:
    """Search plugins command."""
    query = args.query.lower()
    plugin_type_filter = args.type

    # Scan local plugins
    plugins = registry.scan()

    results: list[PluginInfo] = []
    for p in plugins:
        manifest = p.manifest

        # Filter by type
        if plugin_type_filter and manifest.plugin_type.value != plugin_type_filter:
            continue

        # Filter by search query
        if query and query not in manifest.name.lower() and query not in manifest.description.lower():
            continue

        results.append(p)

    if not results:
        print(f"No plugins found matching '{query}'")
        return 0

    print(f"\nSearch Results for '{query}' ({len(results)}):")
    print("=" * 60)
    for p in results:
        loaded_str = "✓" if p.loaded else "✗"
        print(f"  [{loaded_str}] {p.manifest.name} v{p.manifest.version} - {manifest.plugin_type.value}")
        if manifest.description:
            # Truncate description
            desc = manifest.description[:80]
            if len(manifest.description) > 80:
                desc += "..."
            print(f"      {desc}")

    return 0


def cmd_plugin_update(args: argparse.Namespace, registry: PluginRegistry) -> int:
    """Update plugins command."""
    # Check for updates on all plugins
    remote_plugins = registry.check_updates()

    if not remote_plugins:
        print("No updates available.")
        return 0

    print(f"\nAvailable updates ({len(remote_plugins)}):")
    print("=" * 60)
    for manifest in remote_plugins:
        print(f"  {manifest.name} v{manifest.version}")

    # Ask if user wants to install updates
    install = input("\nInstall available updates? (y/N): ").lower().strip()
    if install == "y":
        for manifest in remote_plugins:
            success = registry.install_plugin(manifest)
            if success:
                print(f"  ✓ Updated {manifest.name}")
            else:
                print(f"  ✗ Failed to update {manifest.name}")

    return 0
