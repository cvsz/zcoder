"""zcoder.async.lifecycle — Async lifecycle controller (Phase 3 of Big Upgrade).

Provides ``LifecycleController`` which manages the startup, cancellation,
and teardown of one async operation. Each async operation (streaming,
tool execution, model call) gets its own lifecycle controller.

Implements: One Async Operation = One Lifecycle Controller (Section 4.9).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from zcoder.agent.orchestration.cancellation import AbortSignal


class LifecycleController:
    """Controls the lifecycle of one async operation.

    Manages startup, cancellation, and cleanup for a single operation.
    Uses an ``asyncio.Event`` as the cancellation signal — when the event
    is set, all dependent work should stop.

    Follows: One Async Operation = One Lifecycle Controller (Section 4.9).
    """

    def __init__(self, name: str = "operation") -> None:
        self._name = name
        self._cancel_event = asyncio.Event()
        self._abort_signal = AbortSignal()
        self._tasks: set[asyncio.Task] = set()
        self._cleanup_callbacks: list[Callable[[], None]] = []
        self._started: bool = False
        self._completed: bool = False
        self._cancelled: bool = False
        self._exception: BaseException | None = None

    @property
    def name(self) -> str:
        """The operation name."""
        return self._name

    @property
    def is_cancelled(self) -> bool:
        """True if cancellation has been requested."""
        return self._cancelled

    @property
    def is_completed(self) -> bool:
        """True if the operation has completed (successfully or with error)."""
        return self._completed

    @property
    def aborted(self) -> bool:
        """True if the abort signal has been triggered."""
        return self._abort_signal.aborted

    @property
    def cancel_event(self) -> asyncio.Event:
        """The underlying asyncio.Event used for cancellation signalling."""
        return self._cancel_event

    @property
    def abort_signal(self) -> AbortSignal:
        """The abort signal for streaming operations."""
        return self._abort_signal

    def start(self) -> None:
        """Mark the operation as started.

        Must be called before any work begins. Can only be called once.
        """
        if self._started:
            raise RuntimeError(f"LifecycleController '{self._name}' already started")
        if self._completed or self._cancelled:
            raise RuntimeError(f"LifecycleController '{self._name}' already finished")
        self._started = True

    def register_task(self, task: asyncio.Task) -> None:
        """Register a task managed by this controller.

        Registered tasks are cancelled when ``cancel()`` is called.
        """
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def register_cleanup(self, callback: Callable[[], None]) -> None:
        """Register a cleanup callback to run on teardown.

        Cleanup callbacks run when ``close()`` or ``cancel()`` is called,
        even if the operation completed successfully.
        """
        self._cleanup_callbacks.append(callback)

    def cancel(self) -> None:
        """Request cancellation of the operation.

        Sets the cancel event, triggers the abort signal, and cancels all
        registered tasks. Idempotent.
        """
        if self._completed:
            return
        self._cancelled = True
        self._cancel_event.set()
        self._abort_signal.abort()
        for task in list(self._tasks):
            if not task.done():
                task.cancel()

    def complete(self, exception: BaseException | None = None) -> None:
        """Mark the operation as completed.

        @param exception - optional exception if the operation failed.
        """
        if self._completed or self._cancelled:
            return
        self._completed = True
        self._exception = exception

    async def wait(self) -> None:
        """Wait for the operation to complete or be cancelled.

        Raises ``asyncio.CancelledError`` if cancelled.
        """
        while not self._completed and not self._cancelled:
            try:
                await asyncio.wait_for(self._cancel_event.wait(), timeout=0.1)
            except TimeoutError:
                continue
        if self._cancelled:
            raise asyncio.CancelledError(f"LifecycleController '{self._name}' was cancelled")
        if self._exception:
            raise self._exception

    def check_cancelled(self) -> None:
        """Raise ``asyncio.CancelledError`` if the operation is cancelled."""
        if self._cancelled:
            raise asyncio.CancelledError(f"LifecycleController '{self._name}' was cancelled")

    def close(self) -> None:
        """Teardown the operation.

        Runs all registered cleanup callbacks. Called when the operation
        is finished (successfully, with error, or cancelled).
        """
        for callback in self._cleanup_callbacks:
            try:
                callback()
            except Exception:
                # Cleanup failures must not prevent other cleanup.
                pass
        self._cleanup_callbacks.clear()


__all__ = [
    "LifecycleController",
]
