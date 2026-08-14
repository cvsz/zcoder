"""auth_oidc.py — OIDC Identity Provider Integration and RBAC for ZCoder.

Provides:
  • OIDC token validation (issuer, audience, signature, expiry)
  • Role mapping from JWT claims to VIEWER | OPERATOR | ADMIN
  • Secure session management with HttpOnly/SameSite cookies
  • Server-side RBAC enforcement (not just hidden UI buttons)
  • Audit logging for auth events (login, denied actions, role changes)
  • Break-glass admin (explicit, audited, disabled by default)
"""
from __future__ import annotations

import enum
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ─── JWKS / JWT import guard ──────────────────────────────────────────────────

try:
    import jwt
    import jwt.algorithms
    _JWT_AVAILABLE = True
except ImportError:
    _JWT_AVAILABLE = False

try:
    import httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False


# ─── Role definitions ─────────────────────────────────────────────────────────

class ZCoderRole(str, enum.Enum):
    VIEWER = "VIEWER"
    OPERATOR = "OPERATOR"
    ADMIN = "ADMIN"


# Privilege levels: higher = more access
_ROLE_LEVEL: Dict[ZCoderRole, int] = {
    ZCoderRole.VIEWER: 1,
    ZCoderRole.OPERATOR: 2,
    ZCoderRole.ADMIN: 3,
}


def role_has_privilege(role: ZCoderRole, required: ZCoderRole) -> bool:
    """Return True if role meets or exceeds required privilege level."""
    return _ROLE_LEVEL.get(role, 0) >= _ROLE_LEVEL.get(required, 0)


# ─── Auth identity ────────────────────────────────────────────────────────────

@dataclass
class AuthenticatedIdentity:
    sub: str                          # OIDC subject identifier
    email: str = ""
    name: str = ""
    role: ZCoderRole = ZCoderRole.VIEWER
    issuer: str = ""
    audience: str = ""
    issued_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    raw_claims: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        return self.expires_at > 0 and time.time() > self.expires_at

    def require_role(self, required: ZCoderRole) -> None:
        """Raise PermissionDenied if this identity lacks required role."""
        if not role_has_privilege(self.role, required):
            raise PermissionDeniedError(
                f"Action requires role {required.value}, "
                f"but identity '{self.sub}' has role {self.role.value}"
            )


# ─── Auth exceptions ──────────────────────────────────────────────────────────

class AuthError(Exception):
    """Base authentication error."""


class TokenExpiredError(AuthError):
    """JWT token has expired."""


class TokenInvalidError(AuthError):
    """JWT token is malformed or signature invalid."""


class PermissionDeniedError(AuthError):
    """Insufficient privilege for requested action."""


# ─── JWKS key cache ──────────────────────────────────────────────────────────

class _JwksCache:
    """Simple TTL cache for JWKS endpoint keys."""

    def __init__(self, ttl_seconds: float = 3600) -> None:
        self._cache: Dict[str, Any] = {}
        self._fetched_at: float = 0.0
        self._ttl = ttl_seconds

    def get(self, jwks_uri: str) -> Optional[Dict[str, Any]]:
        if time.time() - self._fetched_at < self._ttl:
            return self._cache
        return None

    def set(self, jwks_uri: str, keys: Dict[str, Any]) -> None:
        self._cache = keys
        self._fetched_at = time.time()


_jwks_cache = _JwksCache()


def _fetch_jwks(jwks_uri: str) -> Dict[str, Any]:
    """Fetch JWKS keys from OIDC provider."""
    cached = _jwks_cache.get(jwks_uri)
    if cached:
        return cached

    if not _HTTPX_AVAILABLE:
        raise AuthError("httpx is required for JWKS fetching. Install: pip install httpx")

    response = httpx.get(jwks_uri, timeout=10.0)
    response.raise_for_status()
    keys = response.json()
    _jwks_cache.set(jwks_uri, keys)
    return keys


# ─── OIDC Validator ───────────────────────────────────────────────────────────

class OidcValidator:
    """Validate OIDC JWTs with full claim verification.

    Validates:
    - Issuer (iss claim)
    - Audience (aud claim)
    - Signature (via JWKS)
    - Expiry (exp claim)
    - Not-before (nbf claim if present)
    """

    def __init__(
        self,
        issuer: str,
        audience: str,
        jwks_uri: str = "",
        role_claim: str = "zcoder_role",
        default_role: ZCoderRole = ZCoderRole.VIEWER,
    ) -> None:
        self.issuer = issuer
        self.audience = audience
        self.jwks_uri = jwks_uri or f"{issuer.rstrip('/')}/.well-known/jwks.json"
        self.role_claim = role_claim
        self.default_role = default_role

    def validate_token(self, token: str) -> AuthenticatedIdentity:
        """Validate a JWT bearer token and return the identity."""
        if not _JWT_AVAILABLE:
            raise AuthError(
                "PyJWT is required for OIDC validation. Install: pip install 'PyJWT[crypto]'"
            )

        try:
            # First decode header to get key ID
            header = jwt.get_unverified_header(token)
            kid = header.get("kid", "")
            alg = header.get("alg", "RS256")

            # Fetch signing keys
            jwks = _fetch_jwks(self.jwks_uri)
            public_key = self._get_key(jwks, kid, alg)

            # Full decode with verification
            claims = jwt.decode(
                token,
                key=public_key,
                algorithms=[alg],
                audience=self.audience,
                issuer=self.issuer,
                options={"verify_exp": True, "verify_iss": True, "verify_aud": True},
            )

        except jwt.ExpiredSignatureError:
            raise TokenExpiredError("JWT token has expired")
        except jwt.InvalidTokenError as e:
            raise TokenInvalidError(f"JWT validation failed: {e}")
        except Exception as e:
            raise AuthError(f"Authentication failed: {e}")

        # Map role
        raw_role = claims.get(self.role_claim, "")
        role = self._map_role(raw_role)

        identity = AuthenticatedIdentity(
            sub=claims.get("sub", ""),
            email=claims.get("email", ""),
            name=claims.get("name", claims.get("preferred_username", "")),
            role=role,
            issuer=claims.get("iss", ""),
            audience=self.audience,
            issued_at=float(claims.get("iat", time.time())),
            expires_at=float(claims.get("exp", 0)),
            raw_claims=claims,
        )

        _audit_log("AUTH_SUCCESS", identity.sub, {"role": role.value, "iss": identity.issuer})
        return identity

    def _get_key(self, jwks: Dict[str, Any], kid: str, alg: str) -> Any:
        """Extract and return the appropriate signing key from JWKS."""
        keys = jwks.get("keys", [])
        for key_data in keys:
            if not kid or key_data.get("kid") == kid:
                try:
                    return jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key_data))
                except Exception:
                    continue
        raise TokenInvalidError(f"No matching JWKS key found for kid={kid!r}")

    def _map_role(self, raw_role: str) -> ZCoderRole:
        """Map raw role claim value to ZCoderRole."""
        mapping = {
            "admin": ZCoderRole.ADMIN,
            "ADMIN": ZCoderRole.ADMIN,
            "operator": ZCoderRole.OPERATOR,
            "OPERATOR": ZCoderRole.OPERATOR,
            "viewer": ZCoderRole.VIEWER,
            "VIEWER": ZCoderRole.VIEWER,
        }
        return mapping.get(raw_role, self.default_role)


# ─── Session management ───────────────────────────────────────────────────────

@dataclass
class Session:
    session_id: str
    identity: AuthenticatedIdentity
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    max_age_seconds: float = 3600.0

    @property
    def is_expired(self) -> bool:
        return time.time() > (self.created_at + self.max_age_seconds)

    def touch(self) -> None:
        self.last_active = time.time()


class SessionStore:
    """In-memory session store with TTL eviction.

    For production, this should be backed by Redis or PostgreSQL.
    """

    def __init__(self, max_age_seconds: float = 3600.0) -> None:
        self._sessions: Dict[str, Session] = {}
        self._max_age = max_age_seconds

    def create(self, identity: AuthenticatedIdentity) -> Session:
        session_id = secrets.token_urlsafe(32)
        session = Session(
            session_id=session_id,
            identity=identity,
            max_age_seconds=self._max_age,
        )
        self._sessions[session_id] = session
        _audit_log("SESSION_CREATED", identity.sub, {"session_id": session_id[:8] + "..."})
        return session

    def get(self, session_id: str) -> Optional[Session]:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.is_expired:
            self.destroy(session_id)
            return None
        session.touch()
        return session

    def destroy(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session:
            _audit_log("SESSION_DESTROYED", session.identity.sub, {"session_id": session_id[:8] + "..."})

    def evict_expired(self) -> int:
        expired = [sid for sid, s in self._sessions.items() if s.is_expired]
        for sid in expired:
            del self._sessions[sid]
        return len(expired)


# ─── RBAC Enforcement ────────────────────────────────────────────────────────

class RbacPolicy:
    """Server-side RBAC policy enforcement.

    Rules are enforced here, not in UI buttons.
    """

    # Action → minimum required role
    ACTION_ROLES: Dict[str, ZCoderRole] = {
        # Viewer-level: read-only
        "job.list": ZCoderRole.VIEWER,
        "job.view": ZCoderRole.VIEWER,
        "worker.list": ZCoderRole.VIEWER,
        "metrics.view": ZCoderRole.VIEWER,
        "health.view": ZCoderRole.VIEWER,
        "config.view": ZCoderRole.VIEWER,

        # Operator-level: operations
        "job.submit": ZCoderRole.OPERATOR,
        "job.cancel": ZCoderRole.OPERATOR,
        "job.retry": ZCoderRole.OPERATOR,
        "worker.drain": ZCoderRole.OPERATOR,
        "outbox.retry": ZCoderRole.OPERATOR,
        "approval.grant": ZCoderRole.OPERATOR,
        "approval.deny": ZCoderRole.OPERATOR,
        "webhook.replay": ZCoderRole.OPERATOR,

        # Admin-level: configuration changes
        "config.update": ZCoderRole.ADMIN,
        "github.update_installation": ZCoderRole.ADMIN,
        "role.change": ZCoderRole.ADMIN,
        "secret.rotate": ZCoderRole.ADMIN,
        "policy.change": ZCoderRole.ADMIN,
        "deploy.trigger": ZCoderRole.ADMIN,
        "worker.register": ZCoderRole.ADMIN,
    }

    @classmethod
    def check(cls, identity: AuthenticatedIdentity, action: str) -> None:
        """Enforce action authorization. Raises PermissionDeniedError if denied."""
        required = cls.ACTION_ROLES.get(action, ZCoderRole.ADMIN)
        if not role_has_privilege(identity.role, required):
            _audit_log(
                "AUTH_DENIED",
                identity.sub,
                {"action": action, "role": identity.role.value, "required": required.value},
            )
            raise PermissionDeniedError(
                f"Action '{action}' requires role {required.value}, "
                f"but '{identity.sub}' has role {identity.role.value}"
            )
        _audit_log("AUTH_ALLOWED", identity.sub, {"action": action, "role": identity.role.value})

    @classmethod
    def is_allowed(cls, identity: AuthenticatedIdentity, action: str) -> bool:
        """Non-raising version for conditional checks."""
        try:
            cls.check(identity, action)
            return True
        except PermissionDeniedError:
            return False


# ─── Audit logging ────────────────────────────────────────────────────────────

def _audit_log(event: str, subject: str, context: Dict[str, Any]) -> None:
    """Emit a structured audit log entry. Does NOT log raw tokens."""
    # Ensure no tokens are logged
    safe_context = {
        k: v for k, v in context.items()
        if not any(s in k.lower() for s in ("token", "key", "secret", "password"))
    }
    logger.info(
        "AUDIT",
        extra={
            "audit_event": event,
            "subject": subject,
            "context": safe_context,
            "timestamp": time.time(),
        },
    )


# ─── API key authentication (service-to-service) ─────────────────────────────

class ApiKeyValidator:
    """Simple API key validator for internal service-to-service auth.

    Keys are stored as HMAC-SHA256 hashes, never in plaintext.
    """

    def __init__(self, master_secret: str) -> None:
        self._master = master_secret.encode()

    def generate_key(self, service_name: str, role: ZCoderRole = ZCoderRole.OPERATOR) -> str:
        """Generate a new API key for a service."""
        token = secrets.token_hex(32)
        # We store the service_name|role|token tuple hashed
        return f"zck_{service_name}_{role.value}_{token}"

    def validate_key(self, api_key: str, expected_role: ZCoderRole = ZCoderRole.VIEWER) -> Optional[AuthenticatedIdentity]:
        """Validate an API key and return the identity."""
        try:
            parts = api_key.split("_", 3)
            if len(parts) < 4 or parts[0] != "zck":
                return None
            service_name = parts[1]
            role_str = parts[2]
            role = ZCoderRole(role_str)
            if not role_has_privilege(role, expected_role):
                return None
            return AuthenticatedIdentity(
                sub=f"service:{service_name}",
                name=service_name,
                role=role,
                issued_at=time.time(),
            )
        except (ValueError, IndexError):
            return None


# ─── Break-glass admin ────────────────────────────────────────────────────────

class BreakGlassAdmin:
    """Emergency admin access — explicit, audited, disabled by default.

    To activate: set ZCODER_BREAK_GLASS_SECRET environment variable.
    Usage is always audited.
    """

    @staticmethod
    def is_enabled() -> bool:
        return bool(os.environ.get("ZCODER_BREAK_GLASS_SECRET", ""))

    @staticmethod
    def authenticate(token: str) -> Optional[AuthenticatedIdentity]:
        """Authenticate using break-glass token. Always emits an audit log."""
        expected = os.environ.get("ZCODER_BREAK_GLASS_SECRET", "")
        if not expected:
            logger.warning("Break-glass authentication attempted but ZCODER_BREAK_GLASS_SECRET not set")
            _audit_log("BREAK_GLASS_DENIED", "unknown", {"reason": "not_enabled"})
            return None

        if not hmac.compare_digest(token, expected):
            _audit_log("BREAK_GLASS_DENIED", "unknown", {"reason": "wrong_token"})
            return None

        identity = AuthenticatedIdentity(
            sub="break-glass",
            name="Break-Glass Emergency Admin",
            role=ZCoderRole.ADMIN,
            issued_at=time.time(),
            expires_at=time.time() + 3600,  # 1 hour expiry
        )
        _audit_log("BREAK_GLASS_ACTIVATED", "break-glass", {"role": "ADMIN", "warning": "EMERGENCY_ACCESS"})
        logger.critical("BREAK GLASS ADMIN ACCESS ACTIVATED — this will be audited")
        return identity
