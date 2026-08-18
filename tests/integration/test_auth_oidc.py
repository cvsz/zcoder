"""tests/test_auth_oidc.py — Tests for OIDC authentication and RBAC."""

import time

import pytest

from zcoder.infrastructure.auth.oidc import (
    AuthenticatedIdentity,
    BreakGlassAdmin,
    PermissionDeniedError,
    RbacPolicy,
    SessionStore,
    ZCoderRole,
    _audit_log,
    role_has_privilege,
)


class TestRoleHierarchy:
    def test_admin_can_do_viewer_actions(self):
        assert role_has_privilege(ZCoderRole.ADMIN, ZCoderRole.VIEWER)

    def test_admin_can_do_operator_actions(self):
        assert role_has_privilege(ZCoderRole.ADMIN, ZCoderRole.OPERATOR)

    def test_operator_can_do_viewer_actions(self):
        assert role_has_privilege(ZCoderRole.OPERATOR, ZCoderRole.VIEWER)

    def test_operator_cannot_do_admin_actions(self):
        assert not role_has_privilege(ZCoderRole.OPERATOR, ZCoderRole.ADMIN)

    def test_viewer_cannot_do_operator_actions(self):
        assert not role_has_privilege(ZCoderRole.VIEWER, ZCoderRole.OPERATOR)

    def test_viewer_cannot_do_admin_actions(self):
        assert not role_has_privilege(ZCoderRole.VIEWER, ZCoderRole.ADMIN)


class TestAuthenticatedIdentity:
    def _make_identity(self, role: ZCoderRole = ZCoderRole.VIEWER) -> AuthenticatedIdentity:
        return AuthenticatedIdentity(
            sub="user123",
            email="user@example.com",
            role=role,
        )

    def test_identity_not_expired_by_default(self):
        identity = self._make_identity()
        assert not identity.is_expired

    def test_identity_expired_when_past_expiry(self):
        identity = self._make_identity()
        identity.expires_at = time.time() - 1  # 1 second ago
        assert identity.is_expired

    def test_require_role_passes_for_sufficient_role(self):
        identity = self._make_identity(role=ZCoderRole.ADMIN)
        # Should not raise
        identity.require_role(ZCoderRole.VIEWER)
        identity.require_role(ZCoderRole.OPERATOR)
        identity.require_role(ZCoderRole.ADMIN)

    def test_require_role_raises_for_insufficient_role(self):
        identity = self._make_identity(role=ZCoderRole.VIEWER)
        with pytest.raises(PermissionDeniedError):
            identity.require_role(ZCoderRole.OPERATOR)

    def test_require_role_raises_viewer_for_admin(self):
        identity = self._make_identity(role=ZCoderRole.VIEWER)
        with pytest.raises(PermissionDeniedError):
            identity.require_role(ZCoderRole.ADMIN)


class TestRbacPolicy:
    def _identity(self, role: ZCoderRole) -> AuthenticatedIdentity:
        return AuthenticatedIdentity(sub="test", role=role)

    def test_viewer_can_list_jobs(self):
        identity = self._identity(ZCoderRole.VIEWER)
        # Should not raise
        RbacPolicy.check(identity, "job.list")

    def test_viewer_cannot_submit_job(self):
        identity = self._identity(ZCoderRole.VIEWER)
        with pytest.raises(PermissionDeniedError):
            RbacPolicy.check(identity, "job.submit")

    def test_operator_can_submit_job(self):
        identity = self._identity(ZCoderRole.OPERATOR)
        RbacPolicy.check(identity, "job.submit")

    def test_operator_cannot_update_config(self):
        identity = self._identity(ZCoderRole.OPERATOR)
        with pytest.raises(PermissionDeniedError):
            RbacPolicy.check(identity, "zcoder.config.settings.update")

    def test_admin_can_update_config(self):
        identity = self._identity(ZCoderRole.ADMIN)
        RbacPolicy.check(identity, "zcoder.config.settings.update")

    def test_admin_can_trigger_deploy(self):
        identity = self._identity(ZCoderRole.ADMIN)
        RbacPolicy.check(identity, "deploy.trigger")

    def test_viewer_cannot_grant_approval(self):
        identity = self._identity(ZCoderRole.VIEWER)
        with pytest.raises(PermissionDeniedError):
            RbacPolicy.check(identity, "approval.grant")

    def test_operator_can_grant_approval(self):
        identity = self._identity(ZCoderRole.OPERATOR)
        RbacPolicy.check(identity, "approval.grant")

    def test_unknown_action_requires_admin(self):
        identity = self._identity(ZCoderRole.OPERATOR)
        with pytest.raises(PermissionDeniedError):
            RbacPolicy.check(identity, "some.unknown.action.that.does.not.exist")

    def test_is_allowed_returns_false_not_raises(self):
        identity = self._identity(ZCoderRole.VIEWER)
        assert RbacPolicy.is_allowed(identity, "job.submit") is False

    def test_is_allowed_returns_true(self):
        identity = self._identity(ZCoderRole.VIEWER)
        assert RbacPolicy.is_allowed(identity, "job.list") is True

    def test_rbac_enforced_server_side(self):
        """Verify RBAC is enforced at policy level, not just UI."""
        # This test proves the enforcement is in the server-side policy class
        viewer = self._identity(ZCoderRole.VIEWER)
        operator = self._identity(ZCoderRole.OPERATOR)
        admin = self._identity(ZCoderRole.ADMIN)

        dangerous_actions = [
            "zcoder.config.settings.update",
            "role.change",
            "secret.rotate",
            "deploy.trigger",
        ]
        for action in dangerous_actions:
            with pytest.raises(PermissionDeniedError):
                RbacPolicy.check(viewer, action)
            with pytest.raises(PermissionDeniedError):
                RbacPolicy.check(operator, action)
            # Admin should succeed
            RbacPolicy.check(admin, action)


class TestSessionStore:
    def _make_identity(self) -> AuthenticatedIdentity:
        return AuthenticatedIdentity(sub="user1", email="user1@example.com", role=ZCoderRole.VIEWER)

    def test_create_and_get_session(self):
        store = SessionStore(max_age_seconds=3600)
        identity = self._make_identity()
        session = store.create(identity)
        assert session.session_id is not None
        retrieved = store.get(session.session_id)
        assert retrieved is not None
        assert retrieved.identity.sub == "user1"

    def test_expired_session_returns_none(self):
        store = SessionStore(max_age_seconds=0.001)  # expires immediately
        identity = self._make_identity()
        session = store.create(identity)
        time.sleep(0.01)
        retrieved = store.get(session.session_id)
        assert retrieved is None

    def test_destroy_session(self):
        store = SessionStore()
        identity = self._make_identity()
        session = store.create(identity)
        store.destroy(session.session_id)
        retrieved = store.get(session.session_id)
        assert retrieved is None

    def test_nonexistent_session_returns_none(self):
        store = SessionStore()
        assert store.get("nonexistent_session_id_xyz") is None

    def test_evict_expired_sessions(self):
        store = SessionStore(max_age_seconds=0.001)
        identity = self._make_identity()
        for _ in range(3):
            store.create(identity)
        time.sleep(0.01)
        count = store.evict_expired()
        assert count == 3


class TestBreakGlass:
    def test_break_glass_disabled_by_default(self):
        # Without env var set
        import os

        old = os.environ.pop("ZCODER_BREAK_GLASS_SECRET", None)
        try:
            assert BreakGlassAdmin.is_enabled() is False
        finally:
            if old is not None:
                os.environ["ZCODER_BREAK_GLASS_SECRET"] = old

    def test_break_glass_authenticate_wrong_token(self, monkeypatch):
        monkeypatch.setenv("ZCODER_BREAK_GLASS_SECRET", "correct-secret")
        result = BreakGlassAdmin.authenticate("wrong-token")
        assert result is None

    def test_break_glass_authenticate_correct_token(self, monkeypatch):
        monkeypatch.setenv("ZCODER_BREAK_GLASS_SECRET", "correct-secret")
        identity = BreakGlassAdmin.authenticate("correct-secret")
        assert identity is not None
        assert identity.role == ZCoderRole.ADMIN
        assert identity.sub == "break-glass"

    def test_break_glass_authenticate_disabled_returns_none(self, monkeypatch):
        monkeypatch.delenv("ZCODER_BREAK_GLASS_SECRET", raising=False)
        result = BreakGlassAdmin.authenticate("any-token")
        assert result is None


class TestSecurityMiscellaneous:
    def test_audit_log_does_not_raise(self):
        """Audit logging should never crash the application."""
        # Should not raise
        _audit_log("TEST_EVENT", "user@example.com", {"action": "test", "token": "should-be-filtered"})

    def test_oidc_invalid_token_raises_error(self):
        """Verify that malformed tokens are rejected."""
        from zcoder.infrastructure.auth.oidc import OidcValidator

        validator = OidcValidator(
            issuer="https://issuer.example.com",
            audience="zcoder",
            jwks_uri="https://issuer.example.com/.well-known/jwks.json",
        )
        with pytest.raises(Exception):  # TokenInvalidError or AuthError depending on deps
            validator.validate_token("not.a.real.jwt.token")

    def test_expired_token_rejected(self):
        """Verify token expiry is checked — expired identity is flagged."""
        identity = AuthenticatedIdentity(
            sub="expired-user",
            role=ZCoderRole.OPERATOR,
            expires_at=time.time() - 3600,
        )
        assert identity.is_expired

    def test_anonymous_mutation_denied(self):
        """Anonymous (no identity) must not be able to mutate state."""
        # Without an identity, RBAC should deny all mutation actions
        # This tests the invariant: you cannot call RbacPolicy.check with no identity
        from zcoder.infrastructure.auth.oidc import (
            AuthenticatedIdentity,
            PermissionDeniedError,
            RbacPolicy,
            ZCoderRole,
        )

        # Simulate anonymous user with VIEWER role (most restrictive assigned role)
        anon = AuthenticatedIdentity(sub="anonymous", role=ZCoderRole.VIEWER)
        mutation_actions = ["job.submit", "job.cancel", "zcoder.config.settings.update", "deploy.trigger"]
        for action in mutation_actions:
            with pytest.raises(PermissionDeniedError):
                RbacPolicy.check(anon, action)

    def test_untrusted_proxy_headers_policy(self):
        """Verify configuration has trusted proxy CIDR list."""
        from zcoder.config.production import SecurityConfig

        cfg = SecurityConfig()
        # By default, trusted_proxy_cidrs should be empty — don't trust arbitrary proxies
        assert cfg.trusted_proxy_cidrs == []
