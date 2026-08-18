"""
resilience.py — Retries, backoff, and circuit breaking for outbound API calls

Everything in this module is dependency-free (stdlib only) so it works in
the PyInstaller-packaged binary the same as from source.

Usage:

    from resilience import retry, CircuitBreaker
    from exceptions import TransientAPIError, RateLimitError

    breaker = CircuitBreaker(failure_threshold=5, reset_timeout=30)

    @retry(max_attempts=4, base_delay=1.0, breaker=breaker)
    def call_api():
        ...

Retry policy:
- Only exceptions whose class (or `RETRYABLE = True`, see exceptions.py)
  marks them retryable are retried. Everything else propagates immediately
  — we never blindly retry a 400 or a refusal.
- Exponential backoff with full jitter (AWS's recommended jitter strategy):
  delay = random(0, min(cap, base * 2**attempt)). Avoids the thundering-herd
  effect of synchronized retries when many CLI instances hit a rate limit
  at once (e.g. a CI matrix or --agent-orchestrate fan-out).
- RateLimitError's `retry_after` (from a 429's Retry-After header, wired in
  by the call site) takes precedence over computed backoff when present.
"""

from __future__ import annotations

import functools
import json
import logging
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, TypeVar

from exceptions import (
    APIError,
    AuthenticationError,
    CircuitOpenError,
    RateLimitError,
    TransientAPIError,
    ZCoderError,
)

logger = logging.getLogger("zcoder.resilience")

T = TypeVar("T")


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, ZCoderError):
        return exc.RETRYABLE
    # Unknown/unexpected exceptions are not retried by default — retrying
    # a bug just makes it slower to surface. Network-layer exceptions from
    # urllib are wrapped into TransientAPIError at the call site instead of
    # being retried here as bare exceptions.
    return False


def raise_for_http_error(exc: BaseException) -> None:
    """Translate a raw urllib exception into the ZCoderError hierarchy.

    Every module that makes a direct HTTP call (rather than going through
    the `anthropic` SDK client, which retries internally) should route its
    urllib.error.HTTPError / network-layer exceptions through this before
    handing them to `retry()` — otherwise `_is_retryable` never sees an
    ZCoderError and nothing gets retried, silently. Originally written
    once for coder.py's Messages API call; every direct-HTTP module hits
    the same three cases (auth, rate limit, transient) so the mapping
    belongs here rather than being re-copied at each call site.

    Always raises; never returns normally.
    """
    if isinstance(exc, urllib.error.HTTPError):
        try:
            body = exc.read().decode(errors="replace")
        except Exception:
            body = ""
        if exc.code == 401:
            raise AuthenticationError("API key rejected (401)", details={"body": body[:300]}) from exc
        if exc.code == 429:
            retry_after = None
            try:
                retry_after = float(exc.headers.get("Retry-After", "")) if exc.headers else None
            except (TypeError, ValueError):
                pass
            raise RateLimitError(
                "Rate limited (429)", retry_after=retry_after, details={"body": body[:300]}
            ) from exc
        if exc.code >= 500:
            raise TransientAPIError(f"Server error ({exc.code})", details={"body": body[:300]}) from exc
        raise APIError(
            f"Request rejected ({exc.code})", status_code=exc.code, details={"body": body[:300]}
        ) from exc
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        # Covers socket timeouts and connection resets from urllib, which
        # surface as plain OSError/ConnectionError subclasses, not HTTPError.
        # These are transient/retryable by nature.
        raise TransientAPIError(f"Network error: {exc}") from exc
    raise exc


def extract_response_metadata(headers) -> dict:
    """Extract standard Claude API response metadata headers without leaking secrets."""
    if not headers:
        return {}
    meta = {}
    if "request-id" in headers:
        meta["request_id"] = headers.get("request-id")
    if "anthropic-workspace-id" in headers:
        meta["workspace_id"] = headers.get("anthropic-workspace-id")
    if "anthropic-ratelimit-requests-remaining" in headers:
        try:
            meta["ratelimit_requests_remaining"] = int(headers.get("anthropic-ratelimit-requests-remaining"))
        except (ValueError, TypeError):
            pass
    if "anthropic-ratelimit-tokens-remaining" in headers:
        try:
            meta["ratelimit_tokens_remaining"] = int(headers.get("anthropic-ratelimit-tokens-remaining"))
        except (ValueError, TypeError):
            pass
    return meta


def safe_urlopen(req, timeout: float):
    """Open an HTTP(S) URL after rejecting local-file/custom URL schemes.

    ``urllib.request.urlopen`` accepts ``file:``, ``ftp:`` and custom handlers;
    ZCoder's network clients must only cross the explicit HTTP(S) boundary.
    """
    url = req.full_url if isinstance(req, urllib.request.Request) else str(req)
    scheme = urllib.parse.urlparse(url).scheme.lower()
    if scheme not in {"http", "https"}:
        raise ValueError(f"Unsupported URL scheme for outbound request: {scheme or '<missing>'}")
    return urllib.request.urlopen(req, timeout=timeout)  # nosec B310 -- scheme checked above


def shell_command_argv(command: str) -> list[str]:
    """Return an explicit platform shell argv for trusted hook/Bash boundaries.

    Callers must perform their normal policy/sandbox checks before invoking this.
    Using an explicit argv avoids implicit ``shell=True`` subprocess execution.
    """
    if os.name == "nt":
        return [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", command]
    return ["/bin/sh", "-c", command]


def urlopen_json(req: urllib.request.Request, timeout: float) -> dict:
    """`urllib.request.urlopen(req)` that returns parsed JSON and translates
    failures via `raise_for_http_error`. Call this from inside a function
    decorated with `@retry(...)` — it does not retry by itself."""
    try:
        with safe_urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode())
            if isinstance(data, dict):
                headers = getattr(r, "headers", None)
                meta = extract_response_metadata(headers) if headers is not None else {}
                if meta:
                    data["_response_metadata"] = meta
                    if "workspace_id" in meta:
                        data["_workspace_id"] = meta["workspace_id"]
                    if "request_id" in meta:
                        data["_request_id"] = meta["request_id"]
            return data
    except (urllib.error.HTTPError, TimeoutError, ConnectionError, OSError) as e:
        raise_for_http_error(e)


def urlopen_text(req: urllib.request.Request, timeout: float) -> str:
    """Like `urlopen_json` but returns the raw decoded body (for endpoints
    that don't return JSON, e.g. fetching a diff or a web page)."""
    try:
        with safe_urlopen(req, timeout=timeout) as r:
            return r.read().decode(errors="replace")
    except (urllib.error.HTTPError, TimeoutError, ConnectionError, OSError) as e:
        raise_for_http_error(e)


@dataclass
class CircuitBreaker:
    """A simple three-state (closed/open/half-open) circuit breaker.

    Protects a downstream dependency (the Anthropic API) from being hammered
    by retries during an outage: after `failure_threshold` consecutive
    failures the circuit opens and calls fail fast (CircuitOpenError) for
    `reset_timeout` seconds, then allows one trial call (half-open) to
    decide whether to close again.
    """

    failure_threshold: int = 5
    reset_timeout: float = 30.0
    _failures: int = field(default=0, init=False)
    _state: str = field(default="closed", init=False)  # closed | open | half_open
    _opened_at: float = field(default=0.0, init=False)

    def before_call(self):
        if self._state == "open":
            if time.monotonic() - self._opened_at >= self.reset_timeout:
                self._state = "half_open"
                logger.info("circuit_breaker_half_open")
            else:
                raise CircuitOpenError(
                    "Circuit breaker is open — too many recent failures",
                    details={
                        "reset_in_s": round(self.reset_timeout - (time.monotonic() - self._opened_at), 1)
                    },
                )

    def on_success(self):
        if self._state != "closed":
            logger.info("circuit_breaker_closed")
        self._failures = 0
        self._state = "closed"

    def on_failure(self):
        self._failures += 1
        if self._state == "half_open" or self._failures >= self.failure_threshold:
            self._state = "open"
            self._opened_at = time.monotonic()
            logger.warning("circuit_breaker_open", extra={"failures": self._failures})

    @property
    def state(self) -> str:
        return self._state


def _backoff_delay(attempt: int, base_delay: float, max_delay: float) -> float:
    """Full-jitter exponential backoff: uniform(0, min(cap, base * 2**attempt))."""
    cap = min(max_delay, base_delay * (2**attempt))
    return random.uniform(0, cap)


def retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 20.0,
    breaker: CircuitBreaker | None = None,
    sleep: Callable[[float], None] = time.sleep,
):
    """Decorator: retry a callable on retryable ZCoderError subclasses.

    `sleep` is injectable for tests so retry-delay tests don't actually
    sleep in the process; see tests/test_resilience.py.
    """

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> T:
            last_exc: BaseException | None = None
            for attempt in range(max_attempts):
                if breaker is not None:
                    breaker.before_call()
                try:
                    result = fn(*args, **kwargs)
                except ZCoderError as exc:
                    last_exc = exc
                    if breaker is not None:
                        breaker.on_failure()
                    if not _is_retryable(exc) or attempt == max_attempts - 1:
                        raise
                    delay = getattr(exc, "retry_after", None)
                    if delay is None:
                        delay = _backoff_delay(attempt, base_delay, max_delay)
                    logger.warning(
                        "retrying_after_failure",
                        extra={
                            "attempt": attempt + 1,
                            "max_attempts": max_attempts,
                            "delay_s": round(delay, 2),
                            "error_code": exc.error_code,
                        },
                    )
                    sleep(delay)
                    continue
                else:
                    if breaker is not None:
                        breaker.on_success()
                    return result
            # Unreachable in practice (loop always returns or raises), but
            # keeps type checkers happy and guards against a future edit
            # accidentally falling through.
            assert last_exc is not None
            raise last_exc

        return wrapper

    return decorator
