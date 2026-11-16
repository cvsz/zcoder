"""Integration tests for zcoder.agent.plugin.manager - allowlist/blocklist and hot-reload."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from zcoder.agent.plugin.loader import LoadedPlugin, PluginLoader
from zcoder.agent.plugin.manager import PluginManager, PluginTier
from zcoder.agent.plugin.manifest import PluginManifest


def _make_manifest(name: str, tier: str = "user") -> PluginManifest:
    return PluginManifest(
        name=name,
        version="1.0.0",
        description=f"{name} plugin",
        tier=tier,
    )


def _make_plugin(name: str, tier: str = "user") -> LoadedPlugin:
    return LoadedPlugin(
        manifest=_make_manifest(name, tier),
        hooks={},
        tools={},
        commands={},
        mcp_servers={},
        module=None,
    )


class TestAllowlistBlocklist:
    """Tests for allowlist/blocklist policy enforcement."""

    def test_is_allowed_empty_lists_allows_all(self):
        manager = PluginManager()
        assert manager._is_allowed("any-plugin") is True

    def test_blocklist_denies_listed_plugin(self):
        manager = PluginManager(blocklist=["bad-plugin"])
        assert manager._is_allowed("bad-plugin") is False
        assert manager._is_allowed("good-plugin") is True

    def test_allowlist_denies_unlisted_plugin(self):
        manager = PluginManager(allowlist=["good-plugin"])
        assert manager._is_allowed("good-plugin") is True
        assert manager._is_allowed("bad-plugin") is False

    def test_blocklist_takes_precedence_over_allowlist(self):
        manager = PluginManager(
            allowlist=["good-plugin", "bad-plugin"],
            blocklist=["bad-plugin"],
        )
        assert manager._is_allowed("bad-plugin") is False
        assert manager._is_allowed("good-plugin") is True

    def test_load_all_skips_blocklisted_plugins(self):
        manager = PluginManager(blocklist=["blocked-plugin"])
        plugins = [_make_plugin("allowed-plugin"), _make_plugin("blocked-plugin")]

        with patch.object(PluginLoader, "load_all_plugins", return_value=plugins):
            manager.load_all()

        names = {p.manifest.name for p in manager.get_all_plugins_ordered()}
        assert "allowed-plugin" in names
        assert "blocked-plugin" not in names

    def test_load_all_skips_non_allowlisted_plugins(self):
        manager = PluginManager(allowlist=["allowed-plugin"])
        plugins = [_make_plugin("allowed-plugin"), _make_plugin("blocked-plugin")]

        with patch.object(PluginLoader, "load_all_plugins", return_value=plugins):
            manager.load_all()

        names = {p.manifest.name for p in manager.get_all_plugins_ordered()}
        assert "allowed-plugin" in names
        assert "blocked-plugin" not in names

    def test_get_plugin_returns_none_for_blocklisted(self):
        manager = PluginManager(blocklist=["blocked-plugin"])
        plugins = [_make_plugin("allowed-plugin"), _make_plugin("blocked-plugin")]

        with patch.object(PluginLoader, "load_all_plugins", return_value=plugins):
            manager.load_all()

        assert manager.get_plugin("allowed-plugin") is not None
        assert manager.get_plugin("blocked-plugin") is None

    def test_load_from_git_respects_blocklist(self):
        manager = PluginManager(blocklist=["git-plugin"])
        git_plugin = _make_plugin("git-plugin")

        with patch.object(PluginLoader, "load_from_git", return_value=git_plugin):
            result = manager.load_from_git("https://example.com/git-plugin.git")

        assert result is None
        assert manager.get_plugin("git-plugin") is None

    def test_load_from_git_disabled_when_allow_git_plugins_false(self):
        manager = PluginManager(allow_git_plugins=False)
        git_plugin = _make_plugin("git-plugin")

        with patch.object(PluginLoader, "load_from_git", return_value=git_plugin):
            result = manager.load_from_git("https://example.com/git-plugin.git")

        assert result is None

    def test_load_from_git_blocked_by_blocklist(self):
        manager = PluginManager(blocklist=["git-plugin"])
        git_plugin = _make_plugin("git-plugin")

        with patch.object(PluginLoader, "load_from_git", return_value=git_plugin):
            result = manager.load_from_git("https://example.com/git-plugin.git")

        assert result is None

    def test_stats_excludes_blocklisted_plugins(self):
        manager = PluginManager(blocklist=["blocked-plugin"])
        allowed = _make_plugin("allowed-plugin")
        allowed.hooks = {"event1": [MagicMock()]}
        blocked = _make_plugin("blocked-plugin")

        with patch.object(PluginLoader, "load_all_plugins", return_value=[allowed, blocked]):
            manager.load_all()

        stats = manager.get_stats()
        assert stats["total_plugins"] == 1
        assert stats["by_tier"]["user"]["plugins"] == ["allowed-plugin"]
        assert stats["total_hooks"] == 1


class TestHotReload:
    """Tests for plugin hot-reload."""

    def test_reload_clears_and_reloads(self):
        manager = PluginManager()
        plugins = [_make_plugin("plugin-a"), _make_plugin("plugin-b")]

        with patch.object(PluginLoader, "load_all_plugins", return_value=plugins):
            manager.load_all()
            assert manager._loaded is True
            assert len(manager.get_all_plugins_ordered()) == 2

        # Reload with different plugins
        new_plugins = [_make_plugin("plugin-c")]
        with patch.object(PluginLoader, "load_all_plugins", return_value=new_plugins):
            manager.reload()
            assert manager._loaded is True
            names = {p.manifest.name for p in manager.get_all_plugins_ordered()}
            assert names == {"plugin-c"}

    def test_reload_after_config_registration_preserves_config(self):
        manager = PluginManager()
        from zcoder.config.settings import Config

        config = Config()
        manager.register_config(config)
        plugins = [_make_plugin("plugin-a")]

        with patch.object(PluginLoader, "load_all_plugins", return_value=plugins):
            manager.reload()
            assert manager.get_config() is config

    def test_reload_idempotent(self):
        manager = PluginManager()
        plugins = [_make_plugin("plugin-a")]

        with patch.object(PluginLoader, "load_all_plugins", return_value=plugins):
            manager.reload()
            manager.reload()
            names = {p.manifest.name for p in manager.get_all_plugins_ordered()}
            assert names == {"plugin-a"}

    def test_load_all_idempotent(self):
        manager = PluginManager()
        plugins = [_make_plugin("plugin-a")]

        with patch.object(PluginLoader, "load_all_plugins", return_value=plugins):
            manager.load_all()
            manager.load_all()  # Should not duplicate
            names = {p.manifest.name for p in manager.get_all_plugins_ordered()}
            assert names == {"plugin-a"}
            assert len(manager.get_all_plugins_ordered()) == 1


class TestHooksExecution:
    """Tests for hooks execution ordered by tier precedence."""

    def test_get_hooks_for_event_returns_ordered_hooks(self):
        manager = PluginManager()

        prepend_plugin = _make_plugin("prepend", "prepend")
        prepend_plugin.hooks = {"turn/end": [MagicMock()]}

        user_plugin = _make_plugin("user", "user")
        user_plugin.hooks = {"turn/end": [MagicMock()]}

        append_plugin = _make_plugin("append", "append")
        append_plugin.hooks = {"turn/end": [MagicMock()]}

        builtin_plugin = _make_plugin("builtin", "builtin")
        builtin_plugin.hooks = {"turn/end": [MagicMock()]}

        plugins = [prepend_plugin, user_plugin, append_plugin, builtin_plugin]

        with patch.object(PluginLoader, "load_all_plugins", return_value=plugins):
            manager.load_all()
            hooks = manager.get_hooks_for_event("turn/end")

        assert len(hooks) == 4
        # Order: prepend -> user -> append -> builtin
        assert hooks[0][0].manifest.name == "prepend"
        assert hooks[1][0].manifest.name == "user"
        assert hooks[2][0].manifest.name == "append"
        assert hooks[3][0].manifest.name == "builtin"

    def test_get_hooks_for_event_unknown_event_returns_empty(self):
        manager = PluginManager()
        plugins = [_make_plugin("plugin-a")]

        with patch.object(PluginLoader, "load_all_plugins", return_value=plugins):
            manager.load_all()
            hooks = manager.get_hooks_for_event("nonexistent/event")

        assert hooks == []

    def test_get_plugins_for_tier_filters_correctly(self):
        manager = PluginManager()
        prepend_plugin = _make_plugin("prepend", "prepend")
        user_plugin = _make_plugin("user", "user")
        plugins = [prepend_plugin, user_plugin]

        with patch.object(PluginLoader, "load_all_plugins", return_value=plugins):
            manager.load_all()
            prepend_plugins = manager.get_plugins_for_tier(PluginTier.PREPEND)
            user_plugins = manager.get_plugins_for_tier(PluginTier.USER)

        assert len(prepend_plugins) == 1
        assert prepend_plugins[0].manifest.name == "prepend"
        assert len(user_plugins) == 1
        assert user_plugins[0].manifest.name == "user"

    def test_get_plugins_by_tier_groups_all(self):
        manager = PluginManager()
        plugins = [
            _make_plugin("p1", "prepend"),
            _make_plugin("p2", "user"),
            _make_plugin("p3", "append"),
            _make_plugin("p4", "builtin"),
        ]

        with patch.object(PluginLoader, "load_all_plugins", return_value=plugins):
            manager.load_all()
            grouped = manager.get_plugins_by_tier()

        assert len(grouped[PluginTier.PREPEND]) == 1
        assert len(grouped[PluginTier.USER]) == 1
        assert len(grouped[PluginTier.APPEND]) == 1
        assert len(grouped[PluginTier.BUILTIN]) == 1
