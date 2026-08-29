"""Fail-closed authentication helpers for the public HTTP API.

This module intentionally has no FastAPI dependency so the identity boundary
can be tested independently of the optional web extra.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from urllib.parse import urlsplit

from zcoder.domain.models.tenant import EnterpriseRole, RequestContext
from zcoder.infrastructure.auth.oidc import (
    AuthError,
    OidcValidator,
    ZCoderRole,
)


class RequestAuthenticationError(Exception):
    """A request supplied invalid or incomplete authentication material."""

    status_code = 401

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code


class AuthenticationUnavailable(RequestAuthenticationError):
    """The server is not configured with the authentication it requires."""

    status_code = 503


def _header(headers: Mapping[str, str], name: str) -> str:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return ""


def _oidc_validator_from_environment() -> OidcValidator:
    enabled = os.environ.get("ZCODER_AUTH_ENABLED", "").strip().lower()
    if enabled not in {"1", "true", "yes"}:
        raise AuthenticationUnavailable("OIDC authentication is not enabled")

    issuer = os.environ.get("ZCODER_OIDC_ISSUER", "").strip()
    audience = os.environ.get("ZCODER_OIDC_AUDIENCE", "").strip()
    if not issuer:
        raise AuthenticationUnavailable("OIDC issuer is not configured")
    if not audience:
        raise AuthenticationUnavailable("OIDC audience is not configured")

    role_value = os.environ.get("ZCODER_OIDC_DEFAULT_ROLE", "VIEWER").strip().upper()
    try:
        default_role = ZCoderRole(role_value)
    except ValueError as exc:
        raise AuthenticationUnavailable("OIDC default role is invalid") from exc

    return OidcValidator(
        issuer=issuer,
        audience=audience,
        jwks_uri=os.environ.get("ZCODER_OIDC_JWKS_URI", "").strip(),
        role_claim=os.environ.get("ZCODER_OIDC_ROLE_CLAIM", "zcoder_role").strip(),
        default_role=default_role,
    )


def _claim_string(claims: Mapping[str, object], names: tuple[str, ...]) -> str:
    for name in names:
        value = claims.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def authenticate_request(headers: Mapping[str, str]) -> RequestContext:
    """Validate a bearer token and create a tenant-scoped request context.

    Tenant and role headers are deliberately ignored. Those values must be
    claims from the verified token, otherwise a caller could select another
    organization's data by changing an HTTP header.
    """
    validator = _oidc_validator_from_environment()
    authorization = _header(headers, "authorization").strip()
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token.strip():
        raise RequestAuthenticationError("A non-empty Bearer token is required")

    try:
        identity = validator.validate_token(token.strip())
    except AuthError as exc:
        raise RequestAuthenticationError(str(exc)) from exc
    except Exception as exc:
        raise RequestAuthenticationError("Bearer token validation failed") from exc

    claims = identity.raw_claims if isinstance(identity.raw_claims, Mapping) else {}
    organization_id = _claim_string(claims, ("organization_id", "org_id", "tenant_id"))
    if not organization_id:
        raise RequestAuthenticationError("Verified identity has no organization claim")
    if not isinstance(identity.sub, str) or not identity.sub.strip():
        raise RequestAuthenticationError("Verified identity has no subject claim")

    role_mapping = {
        ZCoderRole.ADMIN: EnterpriseRole.ORG_ADMIN,
        ZCoderRole.OPERATOR: EnterpriseRole.OPERATOR,
        ZCoderRole.VIEWER: EnterpriseRole.VIEWER,
    }
    role = role_mapping.get(identity.role)
    if role is None:
        raise RequestAuthenticationError("Verified identity has an unsupported role")

    project_id = _claim_string(claims, ("project_id",)) or None
    return RequestContext(
        principal_id=identity.sub.strip(),
        organization_id=organization_id,
        project_id=project_id,
        role=role,
        authentication_method="token",
    )


def parse_cors_origins(raw: str | None) -> list[str]:
    """Parse explicit browser origins for credentialed CORS.

    An empty value disables cross-origin access. Wildcards and URL-like
    values with paths, queries, fragments, or userinfo are rejected because
    credentialed CORS must name exact origins.
    """
    if not raw or not raw.strip():
        return []

    origins: list[str] = []
    for value in raw.split(","):
        origin = value.strip()
        parsed = urlsplit(origin)
        if (
            not origin
            or "*" in origin
            or parsed.scheme.lower() not in {"http", "https"}
            or not parsed.netloc
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError(f"Invalid credentialed CORS origin: {origin or '<empty>'}")
        try:
            if parsed.port is not None:
                pass
        except ValueError as exc:
            raise ValueError(f"Invalid credentialed CORS origin: {origin}") from exc
        if origin not in origins:
            origins.append(origin)
    return origins
