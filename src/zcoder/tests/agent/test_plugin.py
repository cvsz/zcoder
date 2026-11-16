"""Tests for zcoder.agent.plugin.manager - Plugin manager."""

from zcoder.agent.plugin.manager import PluginManager, PluginTier


class TestPluginManager:
    """Tests for PluginManager."""

    def test_create_manager(self):
        manager = PluginManager()
        assert manager.loader is not None
        assert manager._loaded is False
        assert manager._config is None

    def test_register_and_get_config(self):
        manager = PluginManager()

        from zcoder.config.settings import Config

        config = Config()
        manager.register_config(config)
        assert manager.get_config() is config

    def test_get_config_before_registration(self):
        manager = PluginManager()
        assert manager.get_config() is None

    def test_plugin_tiers(self):
        # PluginTier has PREPEND, USER, APPEND, BUILTIN tiers
        tiers = PluginTier.all_tiers()
        tier_names = [t.name for t in tiers]
        assert "PREPEND" in tier_names
        assert "USER" in tier_names
        assert "APPEND" in tier_names
        assert "BUILTIN" in tier_names


class TestLoadedPlugin:
    """Tests for LoadedPlugin dataclass."""

    def test_loaded_plugin_creation(self):
        from zcoder.agent.plugin.loader import LoadedPlugin, PluginManifest

        manifest = PluginManifest(
            name="test-plugin",
            version="1.0.0",
            description="A test plugin",
        )
        plugin = LoadedPlugin(
            manifest=manifest,
            hooks={},
            tools={},
            commands={},
            mcp_servers={},
            module=None,
        )
        assert plugin.manifest.name == "test-plugin"
        assert plugin.hooks == {}
        assert plugin.tools == {}
        assert plugin.module is None


class TestPluginTier:
    """Tests for PluginTier enum."""

    def test_tier_ordering(self):
        from zcoder.agent.plugin.tier import PluginTier

        tiers = PluginTier.all_tiers()
        assert len(tiers) == 4

    def test_tier_names(self):
        from zcoder.agent.plugin.tier import PluginTier

        assert PluginTier.PREPEND.name == "PREPEND"
        assert PluginTier.USER.name == "USER"
        assert PluginTier.APPEND.name == "APPEND"
        assert PluginTier.BUILTIN.name == "BUILTIN"
