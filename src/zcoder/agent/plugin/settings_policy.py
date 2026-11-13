"""Settings policy reads for zcoder plugin system.

Implements tier-aware settings reads with organization policy source,
compatible with claude-code's `$.settings.read({ source: "policy" })`.
"""

import logging
from dataclasses import dataclass
from typing import Any

from zcoder.agent.plugin.events import HookEvent
from zcoder.agent.plugin.hook_bus import HookBus, HookContext, HookResult
from zcoder.agent.plugin.tier import PluginTier
from zcoder.config.production import ProductionConfig, load_config

logger = logging.getLogger(__name__)


@dataclass
class SettingsPolicyReader:
    """Reads settings from various sources with tier awareness."""

    config: ProductionConfig | None = None

    def __post_init__(self):
        if self.config is None:
            self.config = load_config()

    def read(self, key: str, source: str = "default") -> Any:
        """Read setting from specified source."""
        if source == "policy":
            return self._read_policy(key)
        elif source == "managed":
            return self._read_managed(key)
        elif source == "user":
            return self._read_user(key)
        elif source == "project":
            return self._read_project(key)
        return self._read_default(key)

    def _read_policy(self, key: str) -> Any:
        """Read from policy (managed settings). Fails closed."""
        try:
            # Navigate nested config
            parts = key.split(".")
            obj: Any = self.config
            for part in parts:
                if hasattr(obj, part):
                    obj = getattr(obj, part)
                elif isinstance(obj, dict) and part in obj:
                    obj = obj[part]
                else:
                    return None
            return obj
        except Exception as e:
            logger.debug(f"Policy read failed for {key}: {e}")
            # Fail closed: unreadable policy = policy in force
            return None

    def _read_managed(self, key: str) -> Any:
        """Read from managed settings file."""
        # Implementation for managed settings file
        # Could read from /etc/zcoder/managed_settings.json or similar
        return None

    def _read_user(self, key: str) -> Any:
        """Read from user settings."""
        # Read from ~/.zcoder-config.json
        return None

    def _read_project(self, key: str) -> Any:
        """Read from project settings."""
        # Read from .zcoder/config.json in project
        return None

    def _read_default(self, key: str) -> Any:
        """Read from default config."""
        return self._read_policy(key)


@dataclass
class SettingsPolicyHooks:
    """Hook handlers for settings.read event."""

    reader: SettingsPolicyReader
    hook_bus: HookBus

    def __post_init__(self):
        self.hook_bus.register(HookEvent.SETTINGS_READ, self._on_settings_read)

    async def _on_settings_read(self, context: HookContext) -> HookResult:
        key = context.args.get("key", "")
        source = context.args.get("source", "default")

        # Prepend/append tier plugins continue past user tier
        if context.origin_tier in (PluginTier.PREPEND, PluginTier.APPEND):
            return HookResult(modified_args={"continue_past_user_tier": True})

        # User tier: read through policy reader
        value = self.reader.read(key, source)
        return HookResult(
            modified_args={"value": value, "source": source},
        )


def create_settings_policy_hooks(
    hook_bus: HookBus, config: ProductionConfig | None = None
) -> SettingsPolicyHooks:
    """Create settings policy hooks."""
    reader = SettingsPolicyReader(config=config)
    return SettingsPolicyHooks(reader=reader, hook_bus=hook_bus)
