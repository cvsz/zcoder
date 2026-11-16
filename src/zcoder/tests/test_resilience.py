"""Tests for zcoder.core.resilience - retry, circuit breaker, HTTP error translation."""

from __future__ import annotations

import time

import pytest

from zcoder.core.exceptions import (
    APIError,
    AuthenticationError,
    CircuitOpenError,
    RateLimitError,
    TransientAPIError,
    ValidationError,
)
from zcoder.core.resilience import CircuitBreaker, _is_retryable, raise_for_http_error, retry


class TestCircuitBreaker:
    """Tests for CircuitBreaker - three-state (closed/open/half-open)."""

    def test_initial_state_closed(self):
        cb = CircuitBreaker()
        assert cb.state == "closed"
        assert cb._failures == 0

    def test_before_call_closed(self):
        cb = CircuitBreaker()
        cb.before_call()  # Should not raise
        assert cb.state == "closed"

    def test_on_failure_increments(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.on_failure()
        cb.on_failure()
        assert cb._failures == 2
        assert cb.state == "closed"  # Not yet at threshold

    def test_on_failure_opens_at_threshold(self):
        cb = CircuitBreaker(failure_threshold=2)
        cb.on_failure()
        assert cb.state == "closed"
        cb.on_failure()
        assert cb.state == "open"
        assert cb._opened_at > 0

    def test_before_call_when_open_raises(self):
        cb = CircuitBreaker(failure_threshold=1, reset_timeout=60)
        cb.on_failure()  # Opens the circuit
        with pytest.raises(CircuitOpenError, match="Circuit breaker is open"):
            cb.before_call()

    def test_before_call_half_open_after_reset(self):
        cb = CircuitBreaker(failure_threshold=1, reset_timeout=0.1)
        cb.on_failure()  # Opens
        assert cb.state == "open"
        time.sleep(0.15)  # Wait for reset timeout
        cb.before_call()  # Should transition to half_open
        assert cb.state == "half_open"

    def test_on_success_closes(self):
        cb = CircuitBreaker(failure_threshold=1)
        cb.on_failure()  # Open
        assert cb.state == "open"
        cb.on_success()  # Close
        assert cb.state == "closed"
        assert cb._failures == 0

    def test_on_failure_from_half_open_opens(self):
        cb = CircuitBreaker(failure_threshold=2, reset_timeout=0.1)
        cb.on_failure()
        cb.on_failure()  # Open
        assert cb.state == "open"
        time.sleep(0.15)
        cb.before_call()  # Half-open
        assert cb.state == "half_open"
        cb.on_failure()  # Fail again -> open
        assert cb.state == "open"


class TestRetryDecorator:
    """Tests for the retry decorator."""

    def test_no_retry_on_success(self):
        calls = []

        @retry(max_attempts=3)
        def fn():
            calls.append(1)
            return "ok"

        assert fn() == "ok"
        assert len(calls) == 1

    def test_retry_on_retryable_error(self):
        calls = []

        @retry(max_attempts=3, base_delay=0.01, sleep=lambda d: None)
        def fn():
            calls.append(1)
            if len(calls) < 3:
                raise TransientAPIError("transient")
            return "success"

        assert fn() == "success"
        assert len(calls) == 3

    def test_no_retry_on_non_retryable_error(self):
        calls = []

        @retry(max_attempts=3, base_delay=0.01, sleep=lambda d: None)
        def fn():
            calls.append(1)
            raise ValidationError("bad input")

        with pytest.raises(ValidationError, match="bad input"):
            fn()
        assert len(calls) == 1  # Not retried

    def test_retry_exhausted_raises_last_error(self):
        calls = []

        @retry(max_attempts=2, base_delay=0.01, sleep=lambda d: None)
        def fn():
            calls.append(1)
            raise RateLimitError("rate limited")

        with pytest.raises(RateLimitError, match="rate limited"):
            fn()
        assert len(calls) == 2  # Tried max_attempts times

    def test_retry_uses_retry_after(self):
        calls = []
        delays = []

        @retry(max_attempts=3, base_delay=1.0, sleep=lambda d: delays.append(d))
        def fn():
            calls.append(1)
            if len(calls) < 2:
                raise RateLimitError("rate limited", retry_after=0.05)
            return "ok"

        assert fn() == "ok"
        assert len(calls) == 2
        # retry_after should be used instead of backoff
        assert delays == [0.05]

    def test_retry_with_breaker(self):
        breaker = CircuitBreaker(failure_threshold=1, reset_timeout=60)

        @retry(max_attempts=3, base_delay=0.01, sleep=lambda d: None, breaker=breaker)
        def fn():
            raise TransientAPIError("transient")

        # First failure opens the circuit, subsequent call fails fast
        with pytest.raises(CircuitOpenError):
            fn()
        assert breaker.state == "open"


class TestRaiseForHTTPError:
    """Tests for raise_for_http_error - HTTP error translation."""

    def test_http_401_becomes_auth_error(self):
        import urllib.error

        exc = urllib.error.HTTPError("https://api.example.com", 401, "Unauthorized", {}, None)
        with pytest.raises(AuthenticationError, match="401"):
            raise_for_http_error(exc)

    def test_http_429_becomes_rate_limit(self):
        import urllib.error

        headers = {"Retry-After": "10"}
        exc = urllib.error.HTTPError("https://api.example.com", 429, "Too Many Requests", headers, None)
        with pytest.raises(RateLimitError) as ctx:
            raise_for_http_error(exc)
        assert ctx.value.retry_after == 10.0

    def test_http_500_becomes_transient(self):
        import urllib.error

        exc = urllib.error.HTTPError("https://api.example.com", 500, "Internal Server Error", {}, None)
        with pytest.raises(TransientAPIError, match="500"):
            raise_for_http_error(exc)

    def test_http_404_becomes_api_error(self):
        import urllib.error

        exc = urllib.error.HTTPError("https://api.example.com", 404, "Not Found", {}, None)
        with pytest.raises(APIError, match="404") as ctx:
            raise_for_http_error(exc)
        assert ctx.value.status_code == 404

    def test_timeout_becomes_transient(self):
        exc = TimeoutError("connection timed out")
        with pytest.raises(TransientAPIError, match="Network error"):
            raise_for_http_error(exc)

    def test_connection_error_becomes_transient(self):
        exc = ConnectionError("connection refused")
        with pytest.raises(TransientAPIError, match="Network error"):
            raise_for_http_error(exc)

    def test_non_http_error_re_raised(self):
        exc = ValueError("not an http error")
        with pytest.raises(ValueError, match="not an http error"):
            raise_for_http_error(exc)

    def test_zcoder_error_not_retried(self):
        err = ValidationError("bad input")
        assert not _is_retryable(err)

    def test_transient_error_is_retried(self):
        err = TransientAPIError("server error")
        assert _is_retryable(err)
