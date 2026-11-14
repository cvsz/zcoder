"""
Retry classification and policy engine for ZCoder.

Provides intelligent retry logic with classification of errors
into retryable, non-retryable, and conditionally retryable categories.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from zcoder.core.resilience import CircuitBreaker


class RetryCategory(StrEnum):
    """Categories of retry behavior."""

    RETRYABLE = "retryable"  # Should always retry
    NON_RETRYABLE = "non_retryable"  # Should never retry
    CONDITIONAL = "conditional"  # Retry based on conditions
    RATE_LIMITED = "rate_limited"  # Retry with backoff for rate limits
    TRANSIENT = "transient"  # Temporary failures


class ErrorSeverity(StrEnum):
    """Error severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class RetryPolicy:
    """Retry policy configuration."""

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    retry_on: list[RetryCategory] = field(
        default_factory=lambda: [
            RetryCategory.RETRYABLE,
            RetryCategory.TRANSIENT,
            RetryCategory.RATE_LIMITED,
        ]
    )
    stop_on: list[RetryCategory] = field(
        default_factory=lambda: [
            RetryCategory.NON_RETRYABLE,
        ]
    )
    # Conditional retry conditions
    max_total_time: float = 300.0  # 5 minutes max
    respect_retry_after: bool = True


@dataclass
class RetryDecision:
    """Decision from retry classification."""

    should_retry: bool
    category: RetryCategory
    delay: float
    reason: str
    attempt: int
    max_attempts: int
    metadata: dict = field(default_factory=dict)


@dataclass
class RetryMetrics:
    """Metrics for retry tracking."""

    total_attempts: int = 0
    successful_retries: int = 0
    failed_retries: int = 0
    categories: dict[str, int] = field(default_factory=dict)
    total_delay: float = 0.0
    start_time: float = field(default_factory=time.time)


class ErrorClassifier:
    """Classifies errors into retry categories."""

    # Patterns for different error types
    RATE_LIMIT_PATTERNS = [
        r"rate.?limit",
        r"too many requests",
        r"429",
        r"quota.?exceeded",
        r"throttle",
    ]

    TRANSIENT_PATTERNS = [
        r"timeout",
        r"connection.?(reset|refused|aborted)",
        r"temporary.?failure",
        r"service.?unavailable",
        r"503",
        r"502",
        r"504",
        r"econnreset",
        r"etimedout",
        r"econnrefused",
        r"network.?error",
        r"dns.?failure",
    ]

    NON_RETRYABLE_PATTERNS = [
        r"401",
        r"403",
        r"unauthorized",
        r"forbidden",
        r"invalid.?key",
        r"invalid.?token",
        r"authentication.?failed",
        r"permission.?denied",
        r"400",
        r"bad.?request",
        r"invalid.?format",
        r"malformed",
        r"not.?found",
        r"404",
        r"model.?not.?found",
        r"context.?length.?exceeded",
        r"max.?tokens.?exceeded",
    ]

    RETRYABLE_PATTERNS = [
        r"500",
        r"internal.?server.?error",
        r"service.?error",
        r"unknown.?error",
        r"upstream.?error",
    ]

    def __init__(self):
        self._compiled_patterns = {
            RetryCategory.RATE_LIMITED: [re.compile(p, re.IGNORECASE) for p in self.RATE_LIMIT_PATTERNS],
            RetryCategory.TRANSIENT: [re.compile(p, re.IGNORECASE) for p in self.TRANSIENT_PATTERNS],
            RetryCategory.NON_RETRYABLE: [re.compile(p, re.IGNORECASE) for p in self.NON_RETRYABLE_PATTERNS],
            RetryCategory.RETRYABLE: [re.compile(p, re.IGNORECASE) for p in self.RETRYABLE_PATTERNS],
        }

    def classify(self, error: Exception | str) -> tuple[RetryCategory, str]:
        """Classify an error into a retry category.

        Args:
            error: Exception or error message string

        Returns:
            Tuple of (category, reason)
        """
        error_str = str(error).lower()

        # Check non-retryable first (highest priority)
        for pattern in self._compiled_patterns[RetryCategory.NON_RETRYABLE]:
            if pattern.search(error_str):
                return RetryCategory.NON_RETRYABLE, f"Matched non-retryable pattern: {pattern.pattern}"

        # Check rate limited
        for pattern in self._compiled_patterns[RetryCategory.RATE_LIMITED]:
            if pattern.search(error_str):
                return RetryCategory.RATE_LIMITED, f"Matched rate limit pattern: {pattern.pattern}"

        # Check transient
        for pattern in self._compiled_patterns[RetryCategory.TRANSIENT]:
            if pattern.search(error_str):
                return RetryCategory.TRANSIENT, f"Matched transient pattern: {pattern.pattern}"

        # Check retryable
        for pattern in self._compiled_patterns[RetryCategory.RETRYABLE]:
            if pattern.search(error_str):
                return RetryCategory.RETRYABLE, f"Matched retryable pattern: {pattern.pattern}"

        # Default to transient for unknown errors
        return RetryCategory.TRANSIENT, "Unknown error, defaulting to transient"


class RetryEngine:
    """Intelligent retry engine with classification and metrics."""

    def __init__(self, policy: RetryPolicy | None = None, classifier: ErrorClassifier | None = None):
        self.policy = policy or RetryPolicy()
        self.classifier = classifier or ErrorClassifier()
        self.metrics = RetryMetrics()
        self._circuit_breaker = CircuitBreaker(failure_threshold=5, reset_timeout=30)

    def should_retry(self, error: Exception | str, attempt: int) -> RetryDecision:
        """Determine if an error should be retried.

        Args:
            error: The error that occurred
            attempt: Current attempt number (1-indexed)

        Returns:
            RetryDecision with retry decision and delay
        """
        category, reason = self.classifier.classify(error)

        # Check if we've exceeded max attempts
        if attempt >= self.policy.max_attempts:
            return RetryDecision(
                should_retry=False,
                category=category,
                delay=0.0,
                reason=f"Max attempts ({self.policy.max_attempts}) reached",
                attempt=attempt,
                max_attempts=self.policy.max_attempts,
            )

        # Check total time limit
        elapsed = time.time() - self.metrics.start_time
        if elapsed >= self.policy.max_total_time:
            return RetryDecision(
                should_retry=False,
                category=category,
                delay=0.0,
                reason=f"Max total time ({self.policy.max_total_time}s) exceeded",
                attempt=attempt,
                max_attempts=self.policy.max_attempts,
            )

        # Check circuit breaker
        if self._circuit_breaker.state == "open":
            return RetryDecision(
                should_retry=False,
                category=category,
                delay=0.0,
                reason="Circuit breaker open",
                attempt=attempt,
                max_attempts=self.policy.max_attempts,
            )

        # Determine if should retry based on category
        should_retry = category in self.policy.retry_on
        should_stop = category in self.policy.stop_on

        if should_stop:
            should_retry = False

        # Calculate delay
        delay = 0.0
        if should_retry:
            delay = self._calculate_delay(attempt, category)

        # Update metrics
        self.metrics.total_attempts += 1
        self.metrics.categories[category.value] = self.metrics.categories.get(category.value, 0) + 1

        return RetryDecision(
            should_retry=should_retry,
            category=category,
            delay=delay,
            reason=reason,
            attempt=attempt,
            max_attempts=self.policy.max_attempts,
        )

    def _calculate_delay(self, attempt: int, category: RetryCategory) -> float:
        """Calculate delay for retry attempt."""
        base = self.policy.base_delay * (self.policy.exponential_base ** (attempt - 1))
        delay = min(base, self.policy.max_delay)

        # Add jitter
        if self.policy.jitter:
            import random

            delay = delay * (0.5 + random.random() * 0.5)  # 50-100% of calculated delay

        # Special handling for rate limited - longer delay
        if category == RetryCategory.RATE_LIMITED:
            delay = max(delay, 60.0)  # At least 60 seconds for rate limits

        return delay

    def record_success(self) -> None:
        """Record a successful retry."""
        self.metrics.successful_retries += 1
        self._circuit_breaker.on_success()

    def record_failure(self) -> None:
        """Record a failed retry."""
        self.metrics.failed_retries += 1
        self._circuit_breaker.on_failure()

    def get_metrics(self) -> RetryMetrics:
        return self.metrics

    def reset_metrics(self) -> None:
        self.metrics = RetryMetrics()


# Retry decorator with classification


def classified_retry(
    policy: RetryPolicy | None = None,
    classifier: ErrorClassifier | None = None,
):
    """Decorator for retry with classification.

    Usage:
        @classified_retry(policy=RetryPolicy(max_attempts=5))
        async def my_function():
            ...
    """
    engine = RetryEngine(policy, classifier)

    def decorator(func: Callable) -> Callable:
        import functools

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            attempt = 0
            while True:
                attempt += 1
                try:
                    result = await func(*args, **kwargs)
                    engine.record_success()
                    return result
                except Exception as e:
                    decision = engine.should_retry(e, attempt)
                    if not decision.should_retry:
                        engine.record_failure()
                        raise

                    engine.record_failure()
                    await asyncio.sleep(decision.delay)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            attempt = 0
            while True:
                attempt += 1
                try:
                    result = func(*args, **kwargs)
                    engine.record_success()
                    return result
                except Exception as e:
                    decision = engine.should_retry(e, attempt)
                    if not decision.should_retry:
                        engine.record_failure()
                        raise

                    engine.record_failure()
                    time.sleep(decision.delay)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# Provider-specific retry policies

OPENAI_RETRY_POLICY = RetryPolicy(
    max_attempts=5,
    base_delay=1.0,
    max_delay=60.0,
    exponential_base=2.0,
    jitter=True,
    retry_on=[
        RetryCategory.RETRYABLE,
        RetryCategory.TRANSIENT,
        RetryCategory.RATE_LIMITED,
    ],
    stop_on=[RetryCategory.NON_RETRYABLE],
    max_total_time=300.0,
)

ANTHROPIC_RETRY_POLICY = RetryPolicy(
    max_attempts=4,
    base_delay=2.0,
    max_delay=120.0,
    exponential_base=2.0,
    jitter=True,
    retry_on=[
        RetryCategory.RETRYABLE,
        RetryCategory.TRANSIENT,
        RetryCategory.RATE_LIMITED,
    ],
    stop_on=[RetryCategory.NON_RETRYABLE],
    max_total_time=300.0,
)

VLLM_RETRY_POLICY = RetryPolicy(
    max_attempts=3,
    base_delay=0.5,
    max_delay=30.0,
    exponential_base=2.0,
    jitter=True,
    retry_on=[
        RetryCategory.RETRYABLE,
        RetryCategory.TRANSIENT,
    ],
    stop_on=[
        RetryCategory.NON_RETRYABLE,
        RetryCategory.RATE_LIMITED,  # vLLM local shouldn't have rate limits
    ],
    max_total_time=120.0,
)

OLLAMA_RETRY_POLICY = RetryPolicy(
    max_attempts=3,
    base_delay=1.0,
    max_delay=30.0,
    exponential_base=2.0,
    jitter=True,
    retry_on=[
        RetryCategory.RETRYABLE,
        RetryCategory.TRANSIENT,
    ],
    stop_on=[RetryCategory.NON_RETRYABLE],
    max_total_time=120.0,
)

DEFAULT_RETRY_POLICY = RetryPolicy()


def get_retry_policy(provider: str) -> RetryPolicy:
    """Get retry policy for a provider."""
    policies = {
        "openai": OPENAI_RETRY_POLICY,
        "anthropic": ANTHROPIC_RETRY_POLICY,
        "vllm": VLLM_RETRY_POLICY,
        "ollama": OLLAMA_RETRY_POLICY,
    }
    return policies.get(provider.lower(), DEFAULT_RETRY_POLICY)
