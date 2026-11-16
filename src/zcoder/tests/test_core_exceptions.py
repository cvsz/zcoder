"""Tests for zcoder.core.exceptions - structured exception hierarchy."""

from __future__ import annotations

from zcoder.core.exceptions import (
    APIError,
    AuthenticationError,
    CircuitOpenError,
    ConfigError,
    RateLimitError,
    RefusalError,
    SecurityError,
    TransientAPIError,
    ValidationError,
    ZCoderError,
)


class TestZCoderErrorBase:
    """Tests for the base ZCoderError class."""

    def test_creation(self):
        err = ZCoderError("something went wrong")
        assert str(err) == "something went wrong"
        assert err.error_code == "ZCODER_ERROR"
        assert err.RETRYABLE is False
        assert err.message == "something went wrong"
        assert err.details == {}

    def test_creation_with_details(self):
        err = ZCoderError("failed", details={"key": "value", "code": 42})
        assert err.details == {"key": "value", "code": 42}

    def test_creation_with_cause(self):
        cause = ValueError("root cause")
        err = ZCoderError("wrapped", cause=cause)
        assert err.__cause__ is cause

    def test_to_dict(self):
        err = ZCoderError("test error", details={"foo": "bar"})
        d = err.to_dict()
        assert d == {
            "error_code": "ZCODER_ERROR",
            "message": "test error",
            "details": {"foo": "bar"},
        }


class TestConfigError:
    """Tests for ConfigError."""

    def test_defaults(self):
        err = ConfigError("bad config")
        assert err.error_code == "CONFIG_ERROR"
        assert err.RETRYABLE is False
        assert str(err) == "bad config"


class TestAuthenticationError:
    """Tests for AuthenticationError."""

    def test_defaults(self):
        err = AuthenticationError("invalid key")
        assert err.error_code == "AUTH_ERROR"
        assert err.RETRYABLE is False


class TestRateLimitError:
    """Tests for RateLimitError."""

    def test_defaults(self):
        err = RateLimitError("rate limited")
        assert err.error_code == "RATE_LIMIT"
        assert err.RETRYABLE is True
        assert err.retry_after is None

    def test_with_retry_after(self):
        err = RateLimitError("rate limited", retry_after=30.5)
        assert err.retry_after == 30.5


class TestTransientAPIError:
    """Tests for TransientAPIError."""

    def test_defaults(self):
        err = TransientAPIError("server error")
        assert err.error_code == "TRANSIENT_API_ERROR"
        assert err.RETRYABLE is True


class TestAPIError:
    """Tests for APIError."""

    def test_defaults(self):
        err = APIError("bad request")
        assert err.error_code == "API_ERROR"
        assert err.RETRYABLE is False
        assert err.status_code is None

    def test_with_status_code(self):
        err = APIError("not found", status_code=404)
        assert err.status_code == 404


class TestRefusalError:
    """Tests for RefusalError."""

    def test_defaults(self):
        err = RefusalError("model refused")
        assert err.error_code == "MODEL_REFUSAL"
        assert err.RETRYABLE is False


class TestValidationError:
    """Tests for ValidationError."""

    def test_defaults(self):
        err = ValidationError("bad input")
        assert err.error_code == "VALIDATION_ERROR"
        assert err.RETRYABLE is False


class TestSecurityError:
    """Tests for SecurityError."""

    def test_defaults(self):
        err = SecurityError("path traversal")
        assert err.error_code == "SECURITY_ERROR"
        assert err.RETRYABLE is False


class TestCircuitOpenError:
    """Tests for CircuitOpenError."""

    def test_defaults(self):
        err = CircuitOpenError("circuit open")
        assert err.error_code == "CIRCUIT_OPEN"
        assert err.RETRYABLE is False


class TestExceptionInheritance:
    """Tests that all custom exceptions inherit from ZCoderError."""

    def test_all_inherit_from_zcoder_error(self):
        for exc_cls in [
            ConfigError,
            AuthenticationError,
            RateLimitError,
            TransientAPIError,
            APIError,
            RefusalError,
            ValidationError,
            SecurityError,
            CircuitOpenError,
        ]:
            assert issubclass(exc_cls, ZCoderError)
            err = exc_cls("test")
            assert isinstance(err, ZCoderError)
            assert isinstance(err, Exception)
