"""Performance optimizations for zcoder plugin system.

Provides lazy loading, caching, and startup optimizations for the plugin system.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any

from zcoder.agent.plugin.hook_bus import HookBus
from zcoder.agent.plugin.manager import PluginManager


@dataclass
class PerformanceMetrics:
    """Tracks plugin system performance metrics."""
    load_time: float = 0.0
    hook_dispatch_count: int = 0
    hook_dispatch_time: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0

    @property
    def avg_hook_dispatch_time(self) -> float:
        if self.hook_dispatch_count == 0:
            return 0.0
        return self.hook_dispatch_time / self.hook_dispatch_count

    @property
    def cache_hit_rate(self) -> float:
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0.0
        return self.cache_hits / total


class LazyPluginManager:
    """Lazy-loading wrapper for PluginManager."""
    
    def __init__(self, plugin_manager: PluginManager):
        self._plugin_manager = plugin_manager
        self._loaded = False
        self._load_future: asyncio.Future | None = None

    def _ensure_loaded(self) -> None:
        """Ensure plugins are loaded (blocking)."""
        if not self._loaded:
            self._plugin_manager.load_all()
            self._loaded = True

    async def ensure_loaded_async(self) -> None:
        """Ensure plugins are loaded (async)."""
        if not self._loaded:
            if self._load_future is None:
                self._load_future = asyncio.get_event_loop().run_in_executor(
                    None, self._plugin_manager.load_all
                )
            await self._load_future
            self._loaded = True

    def __getattr__(self, name: str) -> Any:
        """Delegate to plugin manager after ensuring loaded."""
        self._ensure_loaded()
        return getattr(self._plugin_manager, name)


class OptimizedHookBus(HookBus):
    """HookBus with performance optimizations."""
    
    def __init__(self, plugin_manager: PluginManager):
        super().__init__(plugin_manager)
        self._metrics = PerformanceMetrics()
        self._builtin_hook_cache: dict[str, list[tuple]] = {}

    @property
    def metrics(self) -> PerformanceMetrics:
        return self._metrics

    def _get_all_hooks(self, event: str) -> list[tuple]:
        """Get all hooks with caching."""
        # Check cache first
        if event in self._builtin_hook_cache:
            self._metrics.cache_hits += 1
            return self._builtin_hook_cache[event]
        
        self._metrics.cache_misses += 1
        hooks = super()._get_all_hooks(event)
        self._builtin_hook_cache[event] = hooks
        return hooks

    async def fire(self, context) -> Any:
        """Fire hooks with metrics tracking."""
        start = time.perf_counter()
        try:
            result = await super().fire(context)
            return result
        finally:
            elapsed = time.perf_counter() - start
            self._metrics.hook_dispatch_count += 1
            self._metrics.hook_dispatch_time += elapsed

    def invalidate_cache(self) -> None:
        """Invalidate all caches."""
        super().invalidate_cache()
        self._builtin_hook_cache.clear()


def create_optimized_plugin_system() -> tuple[LazyPluginManager, OptimizedHookBus]:
    """Create optimized plugin system components."""
    from zcoder.agent.plugin.manager import PluginManager
    
    plugin_manager = PluginManager()
    lazy_manager = LazyPluginManager(plugin_manager)
    hook_bus = OptimizedHookBus(plugin_manager)
    
    return lazy_manager, hook_bus


class PluginSystemInitializer:
    """Manages plugin system initialization with background loading."""
    
    def __init__(self):
        self._lazy_manager: LazyPluginManager | None = None
        self._hook_bus: OptimizedHookBus | None = None
        self._init_task: asyncio.Task | None = None
        self._initialized = False

    async def initialize(self) -> tuple[LazyPluginManager, OptimizedHookBus]:
        """Initialize plugin system with background loading."""
        if self._initialized:
            assert self._lazy_manager is not None
            assert self._hook_bus is not None
            return self._lazy_manager, self._hook_bus

        from zcoder.agent.plugin.manager import PluginManager
        
        plugin_manager = PluginManager()
        self._lazy_manager = LazyPluginManager(plugin_manager)
        self._hook_bus = OptimizedHookBus(plugin_manager)

        # Start background loading
        self._init_task = asyncio.create_task(
            self._lazy_manager.ensure_loaded_async()
        )

        self._initialized = True
        assert self._lazy_manager is not None
        assert self._hook_bus is not None
        return self._lazy_manager, self._hook_bus

    async def wait_ready(self) -> None:
        """Wait for initialization to complete."""
        if self._init_task:
            await self._init_task

    def get_hook_bus(self) -> OptimizedHookBus:
        """Get hook bus (initializes if needed)."""
        if not self._initialized:
            raise RuntimeError("Plugin system not initialized")
        assert self._hook_bus is not None
        return self._hook_bus

    def get_manager(self) -> LazyPluginManager:
        """Get plugin manager (initializes if needed)."""
        if not self._initialized:
            raise RuntimeError("Plugin system not initialized")
        assert self._lazy_manager is not None
        return self._lazy_manager


# Global initializer instance
_global_initializer: PluginSystemInitializer | None = None


def get_plugin_system() -> PluginSystemInitializer:
    """Get global plugin system initializer."""
    global _global_initializer
    if _global_initializer is None:
        _global_initializer = PluginSystemInitializer()
    return _global_initializer


async def initialize_plugin_system() -> tuple[LazyPluginManager, OptimizedHookBus]:
    """Initialize plugin system (convenience function)."""
    initializer = get_plugin_system()
    return await initializer.initialize()


def get_hook_bus() -> OptimizedHookBus:
    """Get hook bus from initialized system."""
    return get_plugin_system().get_hook_bus()


def get_plugin_manager() -> LazyPluginManager:
    """Get plugin manager from initialized system."""
    return get_plugin_system().get_manager()