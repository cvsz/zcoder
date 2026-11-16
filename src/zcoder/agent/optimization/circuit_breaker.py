"""Circuit breaker for tool execution — mirrors deepseek-harness circuit breaker patterns.

Provides a circuit breaker with closed/open/half-open states for protecting
against cascading failures in tool execution.
"""

from __future__ import annotations

import asyncio
import enum
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


class CircuitState(enum.Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation, requests pass through
    OPEN = "open"  # Failing, requests are rejected immediately
    HALF_OPEN = "half_open"  # Testing if service has recovered


@dataclass
class CircuitBreakerStats:
    """Circuit breaker statistics."""

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    state_changes: int = 0
    last_state_change: float | None = None
    last_failure_time: float | None = None
    last_success_time: float | None = None


class CircuitBreaker:
    """Circuit breaker with closed/open/half-open states.

    Mirrors deepseek-harness circuit breaker patterns for tool execution.
    Protects against cascading failures by opening the circuit after a
    configurable number of failures, and half-opening to test recovery.
    """

    def __init__(
        self,
        name: str = "default",
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3,
        on_state_change: Callable[[str, CircuitState, CircuitState], None] | None = None,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self._on_state_change = on_state_change

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float | None = None
        self._last_success_time: float | None = None
        self._state_changed_at: float = time.time()
        self._half_open_calls = 0
        self._lock = __import__("threading").RLock()
        self.stats = CircuitBreakerStats()

    @property
    def state(self) -> CircuitState:
        """Current circuit breaker state."""
        with self._lock:
            self._check_state_transition()
            return self._state

    def _check_state_transition(self) -> None:
        """Check if state should transition based on time."""
        now = time.time()

        if self._state == CircuitState.OPEN:
            if now - self._state_changed_at >= self.recovery_timeout:
                self._transition(CircuitState.HALF_OPEN)
        elif self._state == CircuitState.HALF_OPEN:
            # Half-open stays until calls are exhausted or a failure occurs
            pass

    def _transition(self, new_state: CircuitState) -> None:
        """Transition to a new state."""
        old_state = self._state
        self._state = new_state
        self._state_changed_at = time.time()
        self.stats.state_changes += 1
        self.stats.last_state_change = self._state_changed_at

        if self._on_state_change:
            self._on_state_change(self.name, old_state, new_state)

    def record_success(self) -> None:
        """Record a successful call."""
        with self._lock:
            self.stats.total_calls += 1
            self.stats.successful_calls += 1
            self._last_success_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.half_open_max_calls:
                    self._transition(CircuitState.CLOSED)
                    self._failure_count = 0
            elif self._state == CircuitState.CLOSED:
                # Gradually reduce failure count on success
                self._failure_count = max(0, self._failure_count - 1)

    def record_failure(self) -> None:
        """Record a failed call."""
        with self._lock:
            self.stats.total_calls += 1
            self.stats.failed_calls += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._transition(CircuitState.OPEN)
                self._failure_count = self.failure_threshold
            elif self._state == CircuitState.CLOSED:
                self._failure_count += 1
                if self._failure_count >= self.failure_threshold:
                    self._transition(CircuitState.OPEN)

    def record_rejection(self) -> None:
        """Record a rejected call (circuit was open)."""
        with self._lock:
            self.stats.total_calls += 1
            self.stats.rejected_calls += 1

    def can_execute(self) -> bool:
        """Check if a call can be executed (circuit is closed or half-open with capacity)."""
        with self._lock:
            self._check_state_transition()

            if self._state == CircuitState.CLOSED:
                return True
            if self._state == CircuitState.OPEN:
                return False
            if self._state == CircuitState.HALF_OPEN:
                return self._half_open_calls < self.half_open_max_calls
            return False

    def acquire(self) -> bool:
        """Attempt to acquire permission to execute.

        Returns True if execution is allowed, False if circuit is open.
        Increments half-open call counter if in half-open state.
        """
        with self._lock:
            self._check_state_transition()

            if self._state == CircuitState.CLOSED:
                return True
            if self._state == CircuitState.OPEN:
                self.record_rejection()
                return False
            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls < self.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                self.record_rejection()
                return False
            return False

    def release(self, success: bool) -> None:
        """Release after execution, recording success or failure."""
        if success:
            self.record_success()
        else:
            self.record_failure()

    async def call(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        """Execute a function through the circuit breaker.

        Raises CircuitBreakerOpenError if the circuit is open.
        """
        if not self.acquire():
            raise CircuitBreakerOpenError(self.name)

        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            self.release(True)
            return result
        except Exception:
            self.release(False)
            raise


class CircuitBreakerOpenError(Exception):
    """Raised when the circuit breaker is open and rejects a call."""

    def __init__(self, name: str):
        super().__init__(f"Circuit breaker {name!r} is open")
        self.name = name
        self.code = "CIRCUIT_BREAKER_OPEN"


__all__ = [
    "CircuitState",
    "CircuitBreaker",
    "CircuitBreakerStats",
    "CircuitBreakerOpenError",
]
