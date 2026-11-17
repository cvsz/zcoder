"""Authentication plugin system for zcoder.

Provides base classes and patterns for authentication plugins including
OIDC, SAML, API key, and custom authentication methods. Plugins can hook
into authentication events to provide custom identity verification,
authorization, and session management.

Follows the same patterns as the telemetry plugin with HookBus integration.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from zcoder.agent.plugin.events import HookEvent
from zcoder.agent.plugin.hook_bus import HookBus, HookContext, HookResult
from zcoder.agent.plugin.tier import PluginTier

logger = logging.getLogger(__name__)


# ─── Authentication event types ──────────────────────────────────────────────

AUTH_EVENT_LOGIN = "auth.login"
AUTH_EVENT_LOGOUT = "auth.logout"
AUTH_EVENT_TOKEN_REFRESH = "auth.token.refresh"  # nosec B105  # hook event name, not a credential
AUTH_EVENT_TOKEN_VALIDATE = "auth.token.validate"  # nosec B105  # hook event name, not a credential
AUTH_EVENT_PERMISSION_CHECK = "auth.permission.check"
AUTH_EVENT_SESSION_CREATE = "auth.session.create"
AUTH_EVENT_SESSION_REVOKE = "auth.session.revoke"


# ─── Authentication result types ─────────────────────────────────────────────


@dataclass
class AuthIdentity:
    """Authenticated identity information."""

    principal_id: str
    organization_id: str | None = None
    project_id: str | None = None
    role: str = "viewer"
    authentication_method: str = "unknown"
    claims: dict[str, Any] = field(default_factory=dict)
    expires_at: float | None = None


@dataclass
class AuthResult:
    """Result of an authentication operation."""

    success: bool
    identity: AuthIdentity | None = None
    error_message: str | None = None
    error_code: str | None = None
    retry_after: float | None = None


@dataclass
class PermissionResult:
    """Result of a permission check."""

    allowed: bool
    principal_id: str = ""
    resource: str = ""
    action: str = ""
    reason: str | None = None
    error_code: str | None = None


# ─── Authentication plugin base class ────────────────────────────────────────


class AuthPlugin:
    """Base class for authentication plugins.

    Authentication plugins can:
    - Authenticate users via various methods (OIDC, SAML, API key, etc.)
    - Validate tokens
    - Check permissions
    - Create and revoke sessions
    - Hook into authentication events via the HookBus

    Subclasses should implement the abstract methods and register hook
    handlers via the provided HookBus.
    """

    def __init__(
        self,
        name: str,
        hook_bus: HookBus | None = None,
        enabled: bool = True,
        tier: PluginTier = PluginTier.USER,
    ):
        self.name = name
        self.hook_bus = hook_bus
        self.enabled = enabled
        self.tier = tier
        self._active_sessions: dict[str, AuthIdentity] = {}

    def authenticate(
        self,
        credentials: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> AuthResult:
        """Authenticate a user with the given credentials.

        Subclasses should override this method to implement their
        authentication logic.
        """
        raise NotImplementedError(f"{self.__class__.__name__}.authenticate() not implemented")

    def validate_token(self, token: str) -> AuthResult:
        """Validate an authentication token.

        Subclasses should override this method to implement token validation.
        """
        raise NotImplementedError(f"{self.__class__.__name__}.validate_token() not implemented")

    def check_permission(
        self,
        principal_id: str,
        resource: str,
        action: str,
    ) -> PermissionResult:
        """Check if a principal has permission to perform an action on a resource.

        Subclasses should override this method to implement permission checking.
        """
        raise NotImplementedError(f"{self.__class__.__name__}.check_permission() not implemented")

    def create_session(
        self,
        identity: AuthIdentity,
        ttl_seconds: int | None = None,
    ) -> str:
        """Create a session for an authenticated identity.

        Returns a session ID that can be used for subsequent requests.
        """
        session_id = f"sess_{int(time.time())}_{identity.principal_id[:8]}"
        self._active_sessions[session_id] = identity
        return session_id

    def revoke_session(self, session_id: str) -> bool:
        """Revoke a session. Returns True if the session was found and revoked."""
        if session_id in self._active_sessions:
            del self._active_sessions[session_id]
            return True
        return False

    def get_session(self, session_id: str) -> AuthIdentity | None:
        """Get the identity for a session, or None if not found/expired."""
        identity = self._active_sessions.get(session_id)
        if identity is None:
            return None
        if identity.expires_at is not None and time.time() > identity.expires_at:
            del self._active_sessions[session_id]
            return None
        return identity

    def register_hooks(self, hook_bus: HookBus) -> None:
        """Register hook handlers for authentication events.

        Subclasses should override this to register their hook handlers.
        By default, no hooks are registered.
        """
        pass

    def enable(self):
        """Enable the plugin."""
        self.enabled = True

    def disable(self):
        """Disable the plugin."""
        self.enabled = False


# ─── Built-in authentication hook handlers ───────────────────────────────────


class AuthHooks:
    """Hook handlers for authentication events."""

    def __init__(self, plugin: AuthPlugin, hook_bus: HookBus):
        self.plugin = plugin
        self.hook_bus = hook_bus
        self._register_hooks()

    def _register_hooks(self):
        """Register all authentication hooks."""
        self.hook_bus.register(HookEvent.SESSION_START, self._on_session_start)
        self.hook_bus.register(HookEvent.USER_PROMPT_SUBMIT, self._on_prompt_submit)

    async def _on_session_start(self, context: HookContext) -> HookResult:
        """Handle session start events."""
        if not self.plugin.enabled:
            return HookResult()

        session_id = context.session_id
        if not session_id:
            return HookResult()

        # Check if we have an existing identity for this session
        identity = self.plugin.get_session(session_id)
        if identity is None:
            return HookResult(
                blocked=False,
                message="No active authentication for session",
                deny_reason="no_auth",
            )

        # Attach identity to context
        context.extra["identity"] = identity
        context.extra["principal_id"] = identity.principal_id
        return HookResult()

    async def _on_prompt_submit(self, context: HookContext) -> HookResult:
        """Handle prompt submission events."""
        if not self.plugin.enabled:
            return HookResult()

        session_id = context.session_id
        if not session_id:
            return HookResult()

        identity = self.plugin.get_session(session_id)
        if identity is None:
            return HookResult(
                blocked=False,
                message="Authentication required",
                deny_reason="no_auth",
            )

        context.extra["identity"] = identity
        context.extra["principal_id"] = identity.principal_id
        return HookResult()


def create_auth_plugin(
    name: str,
    hook_bus: HookBus | None = None,
    enabled: bool = True,
    tier: PluginTier = PluginTier.USER,
) -> AuthPlugin:
    """Create a basic authentication plugin.

    This is a factory function for creating AuthPlugin instances.
    For custom authentication logic, subclass AuthPlugin instead.
    """
    return AuthPlugin(name=name, hook_bus=hook_bus, enabled=enabled, tier=tier)


# ─── Built-in authentication implementations ─────────────────────────────────


class ApiKeyAuthPlugin(AuthPlugin):
    """API key authentication plugin.

    Authenticates requests using API keys stored in a dictionary.
    Suitable for simple service-to-service authentication.
    """

    def __init__(
        self,
        name: str = "api_key_auth",
        hook_bus: HookBus | None = None,
        api_keys: dict[str, str] | None = None,
        **kwargs,
    ):
        super().__init__(name=name, hook_bus=hook_bus, **kwargs)
        # Maps API key -> principal_id
        self._api_keys: dict[str, str] = api_keys or {}
        # Maps principal_id -> organization_id
        self._principal_orgs: dict[str, str] = {}

    def register_api_key(self, api_key: str, principal_id: str, organization_id: str | None = None):
        """Register an API key for a principal."""
        self._api_keys[api_key] = principal_id
        if organization_id:
            self._principal_orgs[principal_id] = organization_id

    def authenticate(
        self,
        credentials: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> AuthResult:
        """Authenticate using an API key."""
        if not self.enabled:
            return AuthResult(success=False, error_message="Plugin disabled")

        api_key = credentials.get("api_key") or credentials.get("authorization", "")
        if api_key.startswith("Bearer "):
            api_key = api_key[7:]

        if not api_key:
            return AuthResult(
                success=False,
                error_message="No API key provided",
                error_code="missing_api_key",
            )

        principal_id = self._api_keys.get(api_key)
        if principal_id is None:
            return AuthResult(
                success=False,
                error_message="Invalid API key",
                error_code="invalid_api_key",
            )

        organization_id = self._principal_orgs.get(principal_id)
        identity = AuthIdentity(
            principal_id=principal_id,
            organization_id=organization_id,
            role="operator",
            authentication_method="api_key",
        )

        return AuthResult(success=True, identity=identity)

    def validate_token(self, token: str) -> AuthResult:
        """Validate an API key as a token."""
        return self.authenticate({"api_key": token})

    def check_permission(
        self,
        principal_id: str,
        resource: str,
        action: str,
    ) -> PermissionResult:
        """Check permission - API key auth grants operator role by default."""
        if principal_id in self._api_keys.values():
            return PermissionResult(
                allowed=True,
                principal_id=principal_id,
                resource=resource,
                action=action,
            )
        return PermissionResult(
            allowed=False,
            principal_id=principal_id,
            resource=resource,
            action=action,
            reason="Principal not found",
            error_code="unknown_principal",
        )


# ─── Export ──────────────────────────────────────────────────────────────────


__all__ = [
    "AuthIdentity",
    "AuthResult",
    "PermissionResult",
    "AuthPlugin",
    "AuthHooks",
    "ApiKeyAuthPlugin",
    "create_auth_plugin",
    "AUTH_EVENT_LOGIN",
    "AUTH_EVENT_LOGOUT",
    "AUTH_EVENT_TOKEN_REFRESH",
    "AUTH_EVENT_TOKEN_VALIDATE",
    "AUTH_EVENT_PERMISSION_CHECK",
    "AUTH_EVENT_SESSION_CREATE",
    "AUTH_EVENT_SESSION_REVOKE",
]
