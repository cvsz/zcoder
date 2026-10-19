"""Validate signed JWT claims and isolate signing-key caches by issuer URL."""

from __future__ import annotations

import json
import time

import pytest

import zcoder.infrastructure.auth.oidc as oidc

jwt = pytest.importorskip("jwt")
rsa = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.rsa")


@pytest.fixture
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def validator(monkeypatch, signing_key):
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key()))
    public_jwk["kid"] = "test-key"
    monkeypatch.setattr(oidc, "_fetch_jwks", lambda uri: {"keys": [public_jwk]})
    return oidc.OidcValidator(issuer="https://issuer.example", audience="zcoder")


def encode_token(signing_key, **overrides):
    claims = {
        "iss": "https://issuer.example",
        "aud": "zcoder",
        "sub": "user-1",
        "exp": time.time() + 60,
    }
    claims.update(overrides)
    claims = {key: value for key, value in claims.items() if value is not None}
    return jwt.encode(claims, signing_key, algorithm="RS256", headers={"kid": "test-key"})


@pytest.mark.parametrize("claim", ["exp", "sub", "iss", "aud"])
def test_validator_rejects_signed_tokens_missing_required_claims(validator, signing_key, claim):
    token = encode_token(signing_key, **{claim: None})

    with pytest.raises(oidc.TokenInvalidError):
        validator.validate_token(token)


def test_validator_accepts_valid_signed_token(validator, signing_key):
    identity = validator.validate_token(encode_token(signing_key))

    assert identity.sub == "user-1"
    assert identity.expires_at > time.time()


def test_validator_rejects_expired_signed_token(validator, signing_key):
    with pytest.raises(oidc.TokenExpiredError):
        validator.validate_token(encode_token(signing_key, exp=time.time() - 60))


def test_jwks_cache_does_not_reuse_keys_for_another_uri():
    cache = oidc._JwksCache()
    first_keys = {"keys": [{"kid": "first-issuer"}]}
    cache.set("https://first.example/jwks", first_keys)

    assert cache.get("https://first.example/jwks") == first_keys
    assert cache.get("https://second.example/jwks") is None


def test_jwks_cache_keeps_independent_expiry_per_uri(monkeypatch):
    now = 1000.0
    monkeypatch.setattr(oidc.time, "monotonic", lambda: now)
    cache = oidc._JwksCache(ttl_seconds=60)
    first_keys = {"keys": [{"kid": "first"}]}
    second_keys = {"keys": [{"kid": "second"}]}
    cache.set("https://first.example/jwks", first_keys)
    now += 30
    cache.set("https://second.example/jwks", second_keys)
    now += 31

    assert cache.get("https://first.example/jwks") is None
    assert cache.get("https://second.example/jwks") == second_keys
