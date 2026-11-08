"""Validate signed JWT claims and isolate signing-key caches by issuer URL."""

from __future__ import annotations

import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

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


def test_validator_rejects_malformed_token(validator):
    """Malformed tokens must be rejected as invalid, not crash."""
    with pytest.raises(oidc.TokenInvalidError):
        validator.validate_token("not.a.real.jwt.token")


def test_validator_rejects_invalid_signature(validator, signing_key):
    """Tokens signed with a different key must be rejected."""
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = jwt.encode(
        {
            "iss": "https://issuer.example",
            "aud": "zcoder",
            "sub": "user-1",
            "exp": time.time() + 60,
        },
        other_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )
    with pytest.raises(oidc.TokenInvalidError):
        validator.validate_token(token)


def test_validator_rejects_unsigned_none_algorithm(validator, signing_key):
    """Algorithm confusion: 'alg: none' (unsigned) tokens must be rejected."""
    token = jwt.encode(
        {
            "iss": "https://issuer.example",
            "aud": "zcoder",
            "sub": "user-1",
            "exp": time.time() + 60,
        },
        key="",
        algorithm="none",
    )
    with pytest.raises(oidc.TokenInvalidError):
        validator.validate_token(token)


def test_validator_rejects_unsupported_symmetric_algorithm(validator, signing_key):
    """Symmetric algorithms (e.g. HS256) must be rejected by the allowlist."""
    token = jwt.encode(
        {
            "iss": "https://issuer.example",
            "aud": "zcoder",
            "sub": "user-1",
            "exp": time.time() + 60,
        },
        key="s" * 32,
        algorithm="HS256",
    )
    with pytest.raises(oidc.TokenInvalidError):
        validator.validate_token(token)


def test_validator_rejects_wrong_issuer(validator, signing_key):
    """Tokens issued by a different issuer must be rejected (verify_iss)."""
    token = encode_token(signing_key, iss="https://attacker.example")
    with pytest.raises(oidc.TokenInvalidError):
        validator.validate_token(token)


def test_validator_rejects_wrong_audience(validator, signing_key):
    """Tokens addressed to a different audience must be rejected (verify_aud)."""
    token = encode_token(signing_key, aud="wrong-audience")
    with pytest.raises(oidc.TokenInvalidError):
        validator.validate_token(token)


def test_validator_rejects_unknown_key_id(validator, signing_key):
    """A token whose kid is absent from the JWKS must be rejected."""
    token = jwt.encode(
        {
            "iss": "https://issuer.example",
            "aud": "zcoder",
            "sub": "user-1",
            "exp": time.time() + 60,
        },
        signing_key,
        algorithm="RS256",
        headers={"kid": "unknown-kid"},
    )
    with pytest.raises(oidc.TokenInvalidError, match="No matching JWKS key"):
        validator.validate_token(token)


def test_validator_key_rotation(validator, signing_key, monkeypatch):
    """A signing key rotated into the JWKS verifies; the JWKS is re-fetched per validator."""
    new_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    new_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(new_key.public_key()))
    new_jwk["kid"] = "rotated-key"
    old_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key()))
    old_jwk["kid"] = "test-key"
    monkeypatch.setattr(oidc, "_fetch_jwks", lambda uri: {"keys": [old_jwk, new_jwk]})
    token = jwt.encode(
        {
            "iss": "https://issuer.example",
            "aud": "zcoder",
            "sub": "user-2",
            "exp": time.time() + 60,
        },
        new_key,
        algorithm="RS256",
        headers={"kid": "rotated-key"},
    )
    identity = validator.validate_token(token)
    assert identity.sub == "user-2"


def test_validator_rejects_invalid_jwks(validator, signing_key, monkeypatch):
    """A JWKS endpoint with no usable keys must fail closed."""
    monkeypatch.setattr(oidc, "_fetch_jwks", lambda uri: {"keys": []})
    with pytest.raises(oidc.TokenInvalidError):
        validator.validate_token(encode_token(signing_key))


def test_validator_raises_clear_error_when_pyjwt_missing(monkeypatch):
    """Without PyJWT the validator fails closed with a clear error (import regression guard)."""
    monkeypatch.setattr(oidc, "_JWT_AVAILABLE", False)
    validator = oidc.OidcValidator(issuer="https://issuer.example", audience="zcoder")
    with pytest.raises(oidc.AuthError, match="PyJWT is required"):
        validator.validate_token("any.token.string")


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_fetch_jwks_over_http_with_httpx(signing_key):
    """JWKS retrieval over HTTP works end-to-end and results are cached."""
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key()))
    public_jwk["kid"] = "http-key"
    jwks_body = json.dumps({"keys": [public_jwk]}).encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/.well-known/jwks.json":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(jwks_body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *args) -> None:
            pass

    port = _find_free_port()
    server = HTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        jwks_uri = f"http://127.0.0.1:{port}/.well-known/jwks.json"
        first = oidc._fetch_jwks(jwks_uri)
        assert first == {"keys": [public_jwk]}
        # Second call is served from the TTL cache (same object).
        assert oidc._fetch_jwks(jwks_uri) is first
    finally:
        server.shutdown()
        server.server_close()
