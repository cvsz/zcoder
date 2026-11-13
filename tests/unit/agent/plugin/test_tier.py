"""Tests for PluginTier enum."""

import pytest

from zcoder.agent.plugin.tier import PluginTier


class TestPluginTier:
    """Tests for PluginTier enum."""

    def test_tier_ordering(self):
        """Test that tiers have correct precedence order."""
        assert PluginTier.PREPEND < PluginTier.USER
        assert PluginTier.USER < PluginTier.APPEND
        assert PluginTier.APPEND < PluginTier.BUILTIN

    def test_tier_values(self):
        """Test tier numeric values."""
        assert PluginTier.PREPEND.value == 0
        assert PluginTier.USER.value == 1
        assert PluginTier.APPEND.value == 2
        assert PluginTier.BUILTIN.value == 3

    def test_from_string_valid(self):
        """Test parsing valid tier strings."""
        assert PluginTier.from_string("prepend") == PluginTier.PREPEND
        assert PluginTier.from_string("user") == PluginTier.USER
        assert PluginTier.from_string("append") == PluginTier.APPEND
        assert PluginTier.from_string("builtin") == PluginTier.BUILTIN

    def test_from_string_case_insensitive(self):
        """Test parsing is case-sensitive (exact match)."""
        # Implementation is case-sensitive
        with pytest.raises(ValueError):
            PluginTier.from_string("PREPEND")
        with pytest.raises(ValueError):
            PluginTier.from_string("User")

    def test_from_string_invalid(self):
        """Test parsing invalid tier string raises ValueError."""
        with pytest.raises(ValueError, match="Unknown tier"):
            PluginTier.from_string("invalid")
        with pytest.raises(ValueError, match="Unknown tier"):
            PluginTier.from_string("")

    def test_all_tiers(self):
        """Test all_tiers returns correct order."""
        tiers = PluginTier.all_tiers()
        assert tiers == [PluginTier.PREPEND, PluginTier.USER, PluginTier.APPEND, PluginTier.BUILTIN]

    def test_can_override_user(self):
        """Test can_override_user property."""
        assert PluginTier.PREPEND.can_override_user is True
        assert PluginTier.USER.can_override_user is True
        assert PluginTier.APPEND.can_override_user is False
        assert PluginTier.BUILTIN.can_override_user is False

    def test_is_org_tier(self):
        """Test is_org_tier property."""
        assert PluginTier.PREPEND.is_org_tier is True
        assert PluginTier.USER.is_org_tier is False
        assert PluginTier.APPEND.is_org_tier is True
        assert PluginTier.BUILTIN.is_org_tier is False

    def test_is_builtin_or_org(self):
        """Test is_builtin_or_org property."""
        assert PluginTier.PREPEND.is_builtin_or_org is True
        assert PluginTier.USER.is_builtin_or_org is False
        assert PluginTier.APPEND.is_builtin_or_org is True
        assert PluginTier.BUILTIN.is_builtin_or_org is True

    def test_str_representation(self):
        """Test string representation."""
        assert str(PluginTier.PREPEND) == "prepend"
        assert str(PluginTier.USER) == "user"
        assert str(PluginTier.APPEND) == "append"
        assert str(PluginTier.BUILTIN) == "builtin"
