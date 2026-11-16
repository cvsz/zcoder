"""Tests for zcoder.agent.plugin.auth - Authentication plugin system."""

from __future__ import annotations

import pytest

from zcoder.agent.plugin.auth import (
    ApiKeyAuthPlugin,
    AuthHooks,
    AuthIdentity,
    AuthPlugin,
    AuthResult,
    PermissionResult,
    create_auth_plugin,
)
from zcoder.agent.plugin.hook_bus import HookBus
from zcoder.agent.plugin.manager import PluginManager
from zcoder.agent.plugin.tier import PluginTier


class TestAuthIdentity:
    """Tests for AuthIdentity dataclass."""

    def test_creation(self):
        identity = AuthIdentity(
            principal_id="user-123",
            organization_id="org-456",
            project_id="proj-789",
            role="admin",
            authentication_method="oidc",
        )
        assert identity.principal_id == "user-123"
        assert identity.organization_id == "org-456"
        assert identity.project_id == "proj-789"
        assert identity.role == "admin"
        assert identity.authentication_method == "oidc"
        assert identity.claims == {}
        assert identity.expires_at is None

    def test_creation_minimal(self):
        identity = AuthIdentity(principal_id="user-1")
        assert identity.principal_id == "user-1"
        assert identity.organization_id is None
        assert identity.role == "viewer"
        assert identity.authentication_method == "unknown"


class TestAuthResult:
    """Tests for AuthResult dataclass."""

    def test_success(self):
        result = AuthResult(success=True)
        assert result.success is True
        assert result.identity is None
        assert result.error_message is None

    def test_failure(self):
        result = AuthResult(
            success=False,
            error_message="Invalid credentials",
            error_code="invalid_credentials",
        )
        assert result.success is False
        assert result.error_message == "Invalid credentials"
        assert result.error_code == "invalid_credentials"


class TestPermissionResult:
    """Tests for PermissionResult dataclass."""

    def test_allowed(self):
        result = PermissionResult(
            allowed=True,
            principal_id="user-1",
            resource="/docs",
            action="read",
        )
        assert result.allowed is True
        assert result.principal_id == "user-1"
        assert result.resource == "/docs"
        assert result.action == "read"

    def test_denied(self):
        result = PermissionResult(
            allowed=False,
            principal_id="user-1",
            resource="/admin",
            action="write",
            reason="Insufficient permissions",
            error_code="insufficient_permissions",
        )
        assert result.allowed is False
        assert result.reason == "Insufficient permissions"
        assert result.error_code == "insufficient_permissions"


class TestAuthPlugin:
    """Tests for AuthPlugin base class."""

    def test_creation(self):
        plugin = AuthPlugin(name="test_auth")
        assert plugin.name == "test_auth"
        assert plugin.enabled is True
        assert plugin.tier == PluginTier.USER
        assert plugin.hook_bus is None

    def test_authenticate_not_implemented(self):
        plugin = AuthPlugin(name="test_auth")
        with pytest.raises(NotImplementedError):
            plugin.authenticate({"api_key": "test"})

    def test_validate_token_not_implemented(self):
        plugin = AuthPlugin(name="test_auth")
        with pytest.raises(NotImplementedError):
            plugin.validate_token("token-123")

    def test_check_permission_not_implemented(self):
        plugin = AuthPlugin(name="test_auth")
        with pytest.raises(NotImplementedError):
            plugin.check_permission("user-1", "/docs", "read")

    def test_create_session(self):
        plugin = AuthPlugin(name="test_auth")
        identity = AuthIdentity(principal_id="user-1", role="admin")
        session_id = plugin.create_session(identity)
        assert session_id is not None
        assert session_id.startswith("sess_")

        # Retrieve the session
        retrieved = plugin.get_session(session_id)
        assert retrieved is not None
        assert retrieved.principal_id == "user-1"

    def test_revoke_session(self):
        plugin = AuthPlugin(name="test_auth")
        identity = AuthIdentity(principal_id="user-1")
        session_id = plugin.create_session(identity)

        assert plugin.get_session(session_id) is not None
        assert plugin.revoke_session(session_id) is True
        assert plugin.get_session(session_id) is None
        assert plugin.revoke_session(session_id) is False  # Already revoked

    def test_enable_disable(self):
        plugin = AuthPlugin(name="test_auth")
        assert plugin.enabled is True

        plugin.disable()
        assert plugin.enabled is False

        plugin.enable()
        assert plugin.enabled is True

    def test_register_hooks_noop(self):
        """register_hooks should not raise by default."""

        bus = HookBus(PluginManager())
        plugin = AuthPlugin(name="test_auth")
        plugin.register_hooks(bus)  # Should not raise


class TestApiKeyAuthPlugin:
    """Tests for ApiKeyAuthPlugin."""

    def test_creation(self):
        plugin = ApiKeyAuthPlugin(name="test_api_key")
        assert plugin.name == "test_api_key"
        assert plugin.provider_name == "api_key" if hasattr(plugin, "provider_name") else True

    def test_register_and_authenticate(self):
        plugin = ApiKeyAuthPlugin(name="test_api_key")
        plugin.register_api_key("key-123", "user-1", "org-1")

        result = plugin.authenticate({"api_key": "key-123"})
        assert result.success is True
        assert result.identity is not None
        assert result.identity.principal_id == "user-1"
        assert result.identity.organization_id == "org-1"
        assert result.identity.authentication_method == "api_key"

    def test_authenticate_invalid_key(self):
        plugin = ApiKeyAuthPlugin(name="test_api_key")
        plugin.register_api_key("key-123", "user-1")

        result = plugin.authenticate({"api_key": "invalid-key"})
        assert result.success is False
        assert result.error_code == "invalid_api_key"
        assert result.identity is None

    def test_authenticate_no_key(self):
        plugin = ApiKeyAuthPlugin(name="test_api_key")

        result = plugin.authenticate({})
        assert result.success is False
        assert result.error_code == "missing_api_key"

    def test_authenticate_bearer_prefix(self):
        plugin = ApiKeyAuthPlugin(name="test_api_key")
        plugin.register_api_key("key-123", "user-1")

        result = plugin.authenticate({"api_key": "Bearer key-123"})
        assert result.success is True
        assert result.identity.principal_id == "user-1"

    def test_validate_token(self):
        plugin = ApiKeyAuthPlugin(name="test_api_key")
        plugin.register_api_key("key-123", "user-1")

        result = plugin.validate_token("key-123")
        assert result.success is True
        assert result.identity.principal_id == "user-1"

    def test_check_permission_allowed(self):
        plugin = ApiKeyAuthPlugin(name="test_api_key")
        plugin.register_api_key("key-123", "user-1")

        result = plugin.check_permission("user-1", "/docs", "read")
        assert result.allowed is True

    def test_check_permission_unknown_principal(self):
        plugin = ApiKeyAuthPlugin(name="test_api_key")

        result = plugin.check_permission("unknown", "/docs", "read")
        assert result.allowed is False
        assert result.error_code == "unknown_principal"


class TestCreateAuthPlugin:
    """Tests for create_auth_plugin factory function."""

    def test_creation(self):
        plugin = create_auth_plugin(name="test_auth")
        assert isinstance(plugin, AuthPlugin)
        assert plugin.name == "test_auth"
        assert plugin.enabled is True

    def test_creation_disabled(self):
        plugin = create_auth_plugin(name="test_auth", enabled=False)
        assert plugin.enabled is False


class TestAuthHooks:
    """Tests for AuthHooks."""

    def test_creation(self):

        manager = PluginManager()
        bus = HookBus(manager)
        plugin = AuthPlugin(name="test_auth")
        hooks = AuthHooks(plugin=plugin, hook_bus=bus)
        assert hooks.plugin is plugin
        assert hooks.hook_bus is bus
