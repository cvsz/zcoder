"""Tests for performance optimizations."""

import asyncio

import pytest

from zcoder.agent.plugin.manager import PluginManager
from zcoder.agent.plugin.performance import (
    LazyPluginManager,
    OptimizedHookBus,
    PerformanceMetrics,
    PluginSystemInitializer,
    create_optimized_plugin_system,
    get_hook_bus,
    get_plugin_manager,
    get_plugin_system,
    initialize_plugin_system,
)


class TestPerformanceMetrics:
    """Tests for PerformanceMetrics."""

    def test_default_values(self):
        """Test default values."""
        metrics = PerformanceMetrics()
        assert metrics.load_time == 0.0
        assert metrics.hook_dispatch_count == 0
        assert metrics.hook_dispatch_time == 0.0
        assert metrics.cache_hits == 0
        assert metrics.cache_misses == 0

    def test_avg_hook_dispatch_time(self):
        """Test average hook dispatch time calculation."""
        metrics = PerformanceMetrics()
        assert metrics.avg_hook_dispatch_time == 0.0

        metrics.hook_dispatch_count = 10
        metrics.hook_dispatch_time = 5.0
        assert metrics.avg_hook_dispatch_time == 0.5

    def test_cache_hit_rate(self):
        """Test cache hit rate calculation."""
        metrics = PerformanceMetrics()
        assert metrics.cache_hit_rate == 0.0

        metrics.cache_hits = 8
        metrics.cache_misses = 2
        assert metrics.cache_hit_rate == 0.8


class TestLazyPluginManager:
    """Tests for LazyPluginManager."""

    def test_lazy_loading(self):
        """Test plugins loaded on first access."""
        plugin_manager = PluginManager()
        lazy_manager = LazyPluginManager(plugin_manager)

        # Should not be loaded yet
        assert lazy_manager._loaded is False

        # Access should trigger load
        _ = lazy_manager.get_all_plugins_ordered()
        assert lazy_manager._loaded is True

    def test_async_loading(self):
        """Test async loading."""
        plugin_manager = PluginManager()
        lazy_manager = LazyPluginManager(plugin_manager)

        async def test():
            assert lazy_manager._loaded is False
            await lazy_manager.ensure_loaded_async()
            assert lazy_manager._loaded is True

        asyncio.run(test())


class TestOptimizedHookBus:
    """Tests for OptimizedHookBus."""

    def test_metrics_tracking(self):
        """Test metrics are tracked."""
        plugin_manager = PluginManager()
        hook_bus = OptimizedHookBus(plugin_manager)

        assert hook_bus.metrics.hook_dispatch_count == 0

    def test_cache_tracking(self):
        """Test cache hit/miss tracking."""
        plugin_manager = PluginManager()
        hook_bus = OptimizedHookBus(plugin_manager)

        # First call should be cache miss
        hook_bus._get_all_hooks("test_event")
        assert hook_bus.metrics.cache_misses == 1
        assert hook_bus.metrics.cache_hits == 0

        # Second call should be cache hit
        hook_bus._get_all_hooks("test_event")
        assert hook_bus.metrics.cache_hits == 1


class TestPluginSystemInitializer:
    """Tests for PluginSystemInitializer."""

    @pytest.fixture
    def initializer(self):
        """Create fresh initializer."""
        return PluginSystemInitializer()

    @pytest.mark.asyncio
    async def test_initialize(self, initializer):
        """Test initialization."""
        lazy_manager, hook_bus = await initializer.initialize()

        assert isinstance(lazy_manager, LazyPluginManager)
        assert isinstance(hook_bus, OptimizedHookBus)
        assert initializer._initialized is True

    @pytest.mark.asyncio
    async def test_wait_ready(self, initializer):
        """Test waiting for initialization."""
        await initializer.initialize()
        await initializer.wait_ready()  # Should not raise

    @pytest.mark.asyncio
    async def test_getters(self, initializer):
        """Test getters after initialization."""
        await initializer.initialize()

        hook_bus = initializer.get_hook_bus()
        assert isinstance(hook_bus, OptimizedHookBus)

        manager = initializer.get_manager()
        assert isinstance(manager, LazyPluginManager)


class TestCreateOptimizedPluginSystem:
    """Tests for create_optimized_plugin_system."""

    def test_creates_components(self):
        """Test component creation."""
        lazy_manager, hook_bus = create_optimized_plugin_system()

        assert isinstance(lazy_manager, LazyPluginManager)
        assert isinstance(hook_bus, OptimizedHookBus)


class TestGlobalFunctions:
    """Tests for global plugin system functions."""

    @pytest.fixture(autouse=True)
    def reset_global(self):
        """Reset global state."""
        import zcoder.agent.plugin.performance as perf

        perf._global_initializer = None
        yield
        perf._global_initializer = None

    def test_get_plugin_system(self):
        """Test getting global plugin system."""
        system1 = get_plugin_system()
        system2 = get_plugin_system()
        assert system1 is system2  # Should be singleton

    @pytest.mark.asyncio
    async def test_initialize_plugin_system(self):
        """Test initialize_plugin_system convenience function."""
        lazy_manager, hook_bus = await initialize_plugin_system()

        assert isinstance(lazy_manager, LazyPluginManager)
        assert isinstance(hook_bus, OptimizedHookBus)

    @pytest.mark.asyncio
    async def test_get_hook_bus(self):
        """Test get_hook_bus."""
        await initialize_plugin_system()
        hook_bus = get_hook_bus()
        assert isinstance(hook_bus, OptimizedHookBus)

    @pytest.mark.asyncio
    async def test_get_plugin_manager(self):
        """Test get_plugin_manager."""
        await initialize_plugin_system()
        manager = get_plugin_manager()
        assert isinstance(manager, LazyPluginManager)
