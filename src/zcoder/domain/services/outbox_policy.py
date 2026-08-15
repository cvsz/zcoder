"""Bounded poison-message policy for durable outbox delivery.

Upgrade-39 keeps retry cadence external.  This module only decides the durable
state after one failed delivery attempt; it never sleeps, polls, or retries.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OutboxFailureTransition:
    """Durable state to persist after exactly one failed delivery attempt."""

    attempts: int
    status: str


def transition_after_failure(current_attempts: int, max_attempts: int) -> OutboxFailureTransition:
    """Return the bounded state transition after one handler failure.

    ``current_attempts`` is the number already persisted before this invocation.
    The caller remains responsible for persisting the returned state and error.
    No retry is performed here.
    """
    if current_attempts < 0:
        raise ValueError("current_attempts must be >= 0")
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    attempts = current_attempts + 1
    status = "DEAD" if attempts >= max_attempts else "PENDING"
    return OutboxFailureTransition(attempts=attempts, status=status)
