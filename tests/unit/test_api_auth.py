"""Fail-closed authentication and CORS parser tests for the public API."""

import pytest

import zcoder.api.auth as auth_module
from zcoder.domain.models.tenant import EnterpriseRole
from zcoder.infrastructure.auth.oidc import AuthenticatedIdentity, AuthError, ZCoderRole


def configure_oidc(monkeypatch):
    monkeypatch.setenv("ZCODER_AUTH_ENABLED", "true")
    monkeypatch.setenv("ZCODER_OIDC_ISSUER", "https://issuer.example.com")
    monkeypatch.setenv("ZCODER_OIDC_AUDIENCE", "zcoder-api")


def test_authentication_is_unavailable_when_disabled(monkeypatch):
    monkeypatch.delenv("ZCODER_AUTH_ENABLED", raising=False)

    with pytest.raises(auth_module.AuthenticationUnavailable, match="enabled"):
        auth_module.authenticate_request({"Authorization": "Bearer token"})


def test_authentication_is_unavailable_without_oidc_configuration(monkeypatch):
    monkeypatch.setenv("ZCODER_AUTH_ENABLED", "true")
    monkeypatch.delenv("ZCODER_OIDC_ISSUER", raising=False)
    monkeypatch.delenv("ZCODER_OIDC_AUDIENCE", raising=False)

    with pytest.raises(auth_module.AuthenticationUnavailable, match="issuer"):
        auth_module.authenticate_request({"Authorization": "Bearer token"})


@pytest.mark.parametrize("header", [None, "Basic token", "Bearer", "Bearer "])
def test_authentication_requires_nonempty_bearer_token(monkeypatch, header):
    configure_oidc(monkeypatch)
    headers = {} if header is None else {"Authorization": header}

    with pytest.raises(auth_module.RequestAuthenticationError, match="Bearer"):
        auth_module.authenticate_request(headers)


def test_authentication_maps_only_verified_identity_claims(monkeypatch):
    configure_oidc(monkeypatch)
    captured = {}

    class FakeValidator:
        def __init__(self, **kwargs):
            captured["config"] = kwargs

        def validate_token(self, token):
            captured["token"] = token
            return AuthenticatedIdentity(
                sub="user-from-token",
                role=ZCoderRole.OPERATOR,
                raw_claims={
                    "sub": "user-from-token",
                    "organization_id": "org-from-token",
                    "project_id": "project-from-token",
                },
            )

    monkeypatch.setattr(auth_module, "OidcValidator", FakeValidator)

    context = auth_module.authenticate_request(
        {
            "Authorization": "Bearer verified-token",
            "X-Organization-Id": "attacker-org",
            "X-Principal-Id": "attacker-principal",
            "X-Project-Id": "attacker-project",
            "X-Role": "ADMIN",
        }
    )

    assert captured["token"] == "verified-token"
    assert context.principal_id == "user-from-token"
    assert context.organization_id == "org-from-token"
    assert context.project_id == "project-from-token"
    assert context.role is EnterpriseRole.OPERATOR
    assert captured["config"]["issuer"] == "https://issuer.example.com"


def test_authentication_rejects_identity_without_tenant_or_subject(monkeypatch):
    configure_oidc(monkeypatch)

    class FakeValidator:
        def __init__(self, **kwargs):
            pass

        def validate_token(self, token):
            return AuthenticatedIdentity(sub="", raw_claims={})

    monkeypatch.setattr(auth_module, "OidcValidator", FakeValidator)

    with pytest.raises(auth_module.RequestAuthenticationError, match="organization"):
        auth_module.authenticate_request({"Authorization": "Bearer token"})


def test_authentication_translates_oidc_failures_to_401(monkeypatch):
    configure_oidc(monkeypatch)

    class FakeValidator:
        def __init__(self, **kwargs):
            pass

        def validate_token(self, token):
            raise AuthError("token rejected")

    monkeypatch.setattr(auth_module, "OidcValidator", FakeValidator)

    with pytest.raises(auth_module.RequestAuthenticationError, match="token rejected") as exc:
        auth_module.authenticate_request({"Authorization": "Bearer bad-token"})
    assert exc.value.status_code == 401


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, []),
        ("https://console.example.com, http://localhost:3000", ["https://console.example.com", "http://localhost:3000"]),
    ],
)
def test_parse_cors_origins(raw, expected):
    assert auth_module.parse_cors_origins(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["*", "https://console.example.com/path", "ftp://console.example.com", "not-an-origin"],
)
def test_parse_cors_origins_rejects_wildcards_and_malformed_values(raw):
    with pytest.raises(ValueError):
        auth_module.parse_cors_origins(raw)
