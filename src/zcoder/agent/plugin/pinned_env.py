"""Pinned environment variables for zcoder plugin system.

Implements organization-controlled environment variables that user plugins
cannot override, compatible with claude-code's pinned variables feature.
"""

import logging
from dataclasses import dataclass, field

from zcoder.agent.plugin.events import HookEvent
from zcoder.agent.plugin.hook_bus import HookBus, HookContext, HookResult
from zcoder.agent.plugin.tier import PluginTier
from zcoder.config.production import ProductionConfig

logger = logging.getLogger(__name__)

# Always-pinned variables (every build)
ALWAYS_PINNED = frozenset(
    {
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "LD_AUDIT",
        "DYLD_INSERT_LIBRARIES",
        "DYLD_LIBRARY_PATH",
        "DYLD_FRAMEWORK_PATH",
        "BASH_ENV",
        "ENV",
        "ZDOTDIR",
        "NODE_OPTIONS",
        "CLAUDE_CODE_MANAGED_SETTINGS_PATH",
        "CLAUDE_CODE_REMOTE_SETTINGS_PATH",
        "CLAUDE_CODE_MOCK_REMOTE_SETTINGS",
        "CLAUDE_CODE_DISABLE_ADMIN_ENV_UNION",
        "CLAUDE_CONFIG_DIR",
        "CLAUDE_SECURESTORAGE_CONFIG_DIR",
        "USE_LOCAL_OAUTH",
        "USE_STAGING_OAUTH",
        "CLAUDE_LOCAL_OAUTH_API_BASE",
    }
)

# Launcher variables (pinned when policy names launcher)
LAUNCHER_PINNED = frozenset(
    {
        "CLAUDE_CODE_PROCESS_WRAPPER",
    }
)

# Policy/settings source variables (always pinned)
POLICY_SOURCE_PINNED = frozenset(
    {
        "CLAUDE_CODE_MANAGED_SETTINGS_PATH",
        "CLAUDE_CODE_REMOTE_SETTINGS_PATH",
        "CLAUDE_CODE_MOCK_REMOTE_SETTINGS",
        "CLAUDE_CODE_DISABLE_ADMIN_ENV_UNION",
        "CLAUDE_CONFIG_DIR",
        "CLAUDE_SECURESTORAGE_CONFIG_DIR",
        "USE_LOCAL_OAUTH",
        "USE_STAGING_OAUTH",
        "CLAUDE_LOCAL_OAUTH_API_BASE",
    }
)


@dataclass
class PinnedEnvManager:
    """Manages pinned environment variables with tier enforcement."""

    config: ProductionConfig | None = None
    managed_env: dict[str, str] = field(default_factory=dict)
    launcher_name: str = ""

    def __post_init__(self):
        if self.config is None:
            from zcoder.config.production import load_config

            self.config = load_config()

    def set_managed_env(self, env: dict[str, str]):
        """Set managed environment variables from policy."""
        self.managed_env = env

    def set_launcher(self, name: str):
        """Set launcher name from policy."""
        self.launcher_name = name

    def is_pinned(self, var_name: str) -> bool:
        """Check if variable is pinned."""
        if var_name in ALWAYS_PINNED:
            return True
        if self.launcher_name and var_name in LAUNCHER_PINNED:
            return True
        # Managed settings env vars
        if var_name in self.managed_env:
            return True
        return False

    def check_write(self, var_name: str, tier: PluginTier) -> HookResult:
        """Check if write is allowed."""
        # Prepend/append/builtin tiers can write
        if tier in (PluginTier.PREPEND, PluginTier.APPEND, PluginTier.BUILTIN):
            return HookResult()

        if self.is_pinned(var_name):
            return HookResult(
                blocked=True,
                message=f"Variable {var_name} is pinned by organization policy",
                deny_reason="pinned_env",
            )
        return HookResult()

    def check_read(self, var_name: str, tier: PluginTier) -> HookResult:
        """Check if read is allowed (org reads continue past user tier)."""
        if tier in (PluginTier.PREPEND, PluginTier.APPEND):
            return HookResult(modified_args={"continue_past_user_tier": True})
        return HookResult()


@dataclass
class PinnedEnvHooks:
    """Hook handlers for pinned environment variables."""

    manager: PinnedEnvManager
    hook_bus: HookBus

    def __post_init__(self):
        self.hook_bus.register(HookEvent.ENV_SET, self._on_env_set)
        self.hook_bus.register(HookEvent.ENV_GET, self._on_env_get)

    async def _on_env_set(self, context: HookContext) -> HookResult:
        var_name = context.args.get("name", "")
        return self.manager.check_write(var_name, context.origin_tier)

    async def _on_env_get(self, context: HookContext) -> HookResult:
        var_name = context.args.get("name", "")
        return self.manager.check_read(var_name, context.origin_tier)


def create_pinned_env_manager(hook_bus: HookBus, config: ProductionConfig | None = None) -> PinnedEnvManager:
    """Create pinned environment manager and register hooks."""
    manager = PinnedEnvManager(config=config)
    PinnedEnvHooks(manager=manager, hook_bus=hook_bus)
    return manager
