"""zcoder.app.shutdown — Application shutdown handler (Phase 3 of Big Upgrade).

Manages graceful shutdown by cancelling all pending lifecycle controllers
and running cleanup callbacks. Follows the "One Async Operation = One
Lifecycle Controller" pattern — shutdown cancels every controller.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from zcoder.lifecycle.lifecycle import LifecycleController

logger = logging.getLogger(__name__)


class ShutdownManager:
    """Manages graceful application shutdown.

    Tracks all lifecycle controllers created during the application's
    lifetime. On shutdown, cancels all pending operations and runs
    cleanup callbacks in reverse registration order.
    """

    def __init__(self) -> None:
        self._controllers: list[LifecycleController] = []
        self._shutdown_callbacks: list[Callable[[], None]] = []
        self._shutting_down: bool = False

    def register_controller(self, controller: LifecycleController) -> None:
        """Register a lifecycle controller for shutdown management.

        When ``shutdown()`` is called, all registered controllers will
        have their ``cancel()`` method invoked.
        """
        if self._shutting_down:
            # Already shutting down — cancel immediately.
            controller.cancel()
        else:
            self._controllers.append(controller)

    def register_shutdown_callback(self, callback: Callable[[], None]) -> None:
        """Register a callback to run during shutdown.

        Callbacks run after all controllers are cancelled, in reverse
        registration order.
        """
        self._shutdown_callbacks.append(callback)

    async def shutdown(self) -> None:
        """Perform graceful shutdown.

        1. Sets the shutting_down flag (prevents new controller registration).
        2. Cancels all registered lifecycle controllers.
        3. Runs all shutdown callbacks in reverse registration order.
        """
        if self._shutting_down:
            return
        self._shutting_down = True

        logger.info("Shutting down %d lifecycle controller(s)", len(self._controllers))

        # Cancel all controllers
        for controller in self._controllers:
            controller.cancel()

        # Wait briefly for tasks to respond to cancellation
        await asyncio.sleep(0)

        # Run shutdown callbacks in reverse order
        for callback in reversed(self._shutdown_callbacks):
            try:
                callback()
            except Exception as exc:
                logger.error("Shutdown callback failed: %s", exc, exc_info=True)

        logger.info("Shutdown complete")

    def is_shutting_down(self) -> bool:
        """True if shutdown has been initiated."""
        return self._shutting_down


# Global shutdown manager instance — shared across the application.
shutdown_manager = ShutdownManager()


__all__ = [
    "ShutdownManager",
    "shutdown_manager",
]
