"""
cancellation.py — Abort signal for streaming requests (Phase 3 of Big Upgrade).

Provides ``AbortSignal`` so callers can cancel an in-flight streaming
request mid-stream.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

_logger = logging.getLogger(__name__)


class AbortSignal:
    """Signal used to request cancellation of an in-flight operation.

    Consumers poll ``aborted`` or register ``on_abort`` callbacks. Once set,
    the signal cannot be cleared (a new ``AbortSignal`` must be created for
    the next operation).
    """

    def __init__(self) -> None:
        self._aborted: bool = False
        self._callbacks: list[Callable] = []

    @property
    def aborted(self) -> bool:
        """True if cancellation has been requested."""
        return self._aborted

    def abort(self) -> None:
        """Request cancellation. Idempotent."""
        if self._aborted:
            return
        self._aborted = True
        for cb in self._callbacks:
            try:
                cb()
            except Exception:
                # Callback failures must not prevent cancellation.
                _logger.warning("cancellation callback %r failed", cb, exc_info=True)

    def on_abort(self, callback: Callable) -> None:
        """Register a callback to run when ``abort()`` is called."""
        if self._aborted:
            callback()
        else:
            self._callbacks.append(callback)

    def check(self) -> None:
        """Raise ``CancelledError`` if aborted."""
        import asyncio

        if self._aborted:
            raise asyncio.CancelledError("request aborted by caller")
