"""
timeout.py — Idle watchdog for streaming operations (Phase 3 of Big Upgrade).

``IdleWatchdog`` tracks the last activity time and cancels an operation if
no activity is observed within a configurable timeout window.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable


class IdleWatchdog:
    """Watchdog that triggers a callback when no activity is observed.

    Call ``touch()`` whenever activity occurs (e.g. a token is received).
    If the elapsed time since the last touch exceeds ``timeout``, the
    ``on_idle`` callback is invoked and the watchdog stops.
    """

    def __init__(self, timeout: float, on_idle: Callable[[], None]) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._timeout = timeout
        self._on_idle = on_idle
        self._last_activity = time.monotonic()
        self._task: asyncio.Task[None] | None = None
        self._stopped = False

    def touch(self) -> None:
        """Record activity, resetting the idle timer."""
        self._last_activity = time.monotonic()

    def start(self) -> None:
        """Start the watchdog loop in the current event loop."""
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        try:
            while not self._stopped:
                await asyncio.sleep(min(self._timeout, 1.0))
                if time.monotonic() - self._last_activity >= self._timeout:
                    self._on_idle()
                    return
        except asyncio.CancelledError:
            return

    def stop(self) -> None:
        """Stop the watchdog without firing ``on_idle``."""
        self._stopped = True
        if self._task is not None:
            self._task.cancel()
            self._task = None

    @property
    def elapsed(self) -> float:
        """Seconds since the last touch."""
        return time.monotonic() - self._last_activity
