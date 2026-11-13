"""Plugin Manifest Format for Phase 17.

Defines the manifest format for ZCoder plugins, including
validation and metadata fields.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PluginType(Enum):
    """Types of plugins supported."""

    TOOL = "tool"
    AGENT = "agent"
    PROVIDER = "provider"
    TRANSFORM = "transform"
    VIEW = "view"


class PluginVisibility(Enum):
    """Plugin visibility/visibility levels."""

    PUBLIC = "public"
    PRIVATE = "private"
    ENTERPRISE = "enterprise"


@dataclass
class PluginManifest:
    """Metadata for a ZCoder plugin."""

    name: str
    version: str
    description: str
    plugin_type: PluginType
    author: str
    visibility: PluginVisibility = PluginVisibility.PRIVATE
    entry_point: str = ""  # Module path or script
    dependencies: list[str] = field(default_factory=list)
    api_version: str = "1.0"
    license: str = "MIT"
    tags: list[str] = field(default_factory=list)
    repository: str = ""  # Git repo URL
    homepage: str = ""  # Plugin homepage
    screenshots: list[str] = field(default_factory=list)
    default_config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert manifest to dictionary."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "plugin_type": self.plugin_type.value,
            "author": self.author,
            "visibility": self.visibility.value,
            "entry_point": self.entry_point,
            "dependencies": self.dependencies,
            "api_version": self.api_version,
            "license": self.license,
            "tags": self.tags,
            "repository": self.repository,
            "homepage": self.homepage,
            "screenshots": self.screenshots,
            "default_config": self.default_config,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PluginManifest:
        """Create manifest from dictionary."""
        return cls(
            name=data.get("name", ""),
            version=data.get("version", "0.1.0"),
            description=data.get("description", ""),
            plugin_type=PluginType(data.get("plugin_type", "tool")),
            author=data.get("author", ""),
            visibility=PluginVisibility(data.get("visibility", "private")),
            entry_point=data.get("entry_point", ""),
            dependencies=data.get("dependencies", []),
            api_version=data.get("api_version", "1.0"),
            license=data.get("license", "MIT"),
            tags=data.get("tags", []),
            repository=data.get("repository", ""),
            homepage=data.get("homepage", ""),
            screenshots=data.get("screenshots", []),
            default_config=data.get("default_config", {}),
        )

    def validate(self) -> list[str]:
        """Validate the manifest and return a list of errors."""
        errors: list[str] = []

        if not self.name:
            errors.append("Plugin name is required")
        if not self.version:
            errors.append("Plugin version is required")
        if not self.description:
            errors.append("Plugin description is required")
        if not self.author:
            errors.append("Plugin author is required")
        if not self.plugin_type:
            errors.append("Plugin type is required")

        # Validate version format (semver-like)
        version_pattern = r"^\d+\.\d+(\.\d+)?(a|b|rc\d*)?$"
        if not re.match(version_pattern, self.version):
            errors.append(f"Invalid version format: {self.version}")

        # Validate entry point exists if provided
        if self.entry_point and not Path(self.entry_point).exists():
            errors.append(f"Entry point not found: {self.entry_point}")

        return errors


def load_manifest(filepath: Path) -> PluginManifest:
    """Load a plugin manifest from a JSON file."""
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)
    return PluginManifest.from_dict(data)


def save_manifest(manifest: PluginManifest, filepath: Path) -> None:
    """Save a plugin manifest to a JSON file."""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(manifest.to_dict(), f, indent=2)


def discover_plugins(directory: Path) -> list[PluginManifest]:
    """Discover all plugins in a directory."""
    plugins: list[PluginManifest] = []
    for fp in directory.rglob("manifest.json"):
        try:
            manifest = load_manifest(fp)
            errors = manifest.validate()
            if errors:
                logger.warning(f"Plugin {fp} has validation errors: {errors}")
            plugins.append(manifest)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Failed to load plugin manifest from {fp}: {e}")
    return plugins
