"""
zcoder.tools.waterfall — Waterfall listener pattern for tool events.

Provides WaterfallListenerChain which runs listeners sequentially, where each
listener can:
1. Transform the value and pass it to the next listener
2. Short-circuit by returning without calling next()
3. Delegate by calling next() to continue the chain

Follows: Waterfall Listener Semantics (deepseek-harness Section 4.3).
Waterfall listeners MUST call next() to delegate — returning without it
short-circuits the chain.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

# WaterfallListener: (value, next) -> Awaitable[Any]
#   value: the input value
#   next: callable to delegate to the next listener
#   Returns: transformed value or short-circuited result
WaterfallListener = Callable[[Any, Callable[[], Awaitable[Any]]], Awaitable[Any]]


class WaterfallListenerChain:
    """Chain of waterfall listeners executed sequentially.

    Each listener receives (value, next) where:
    - value: the current value (transformed by previous listeners)
    - next: async callable to delegate to the next listener in the chain

    A listener MUST call next() to delegate. Returning without calling
    next() short-circuits the chain — subsequent listeners are not invoked.
    """

    def __init__(self, listeners: list[WaterfallListener] | None = None) -> None:
        self._listeners = list(listeners or [])

    def add_listener(self, listener: WaterfallListener) -> None:
        """Add a listener to the end of the chain."""
        self._listeners.append(listener)

    def insert_listener(self, index: int, listener: WaterfallListener) -> None:
        """Insert a listener at a specific position."""
        self._listeners.insert(index, listener)

    async def run(self, initial: Any) -> Any:
        """Run all listeners in order.

        @param initial - initial value passed to the first listener
        @returns the final value after all listeners (or short-circuit result)
        """

        async def next_step(index: int, value: Any) -> Any:
            if index >= len(self._listeners):
                return value
            listener = self._listeners[index]
            return await listener(value, lambda next_value, *args, **kwargs: next_step(index + 1, next_value))

        return await next_step(0, initial)

    def __len__(self) -> int:
        return len(self._listeners)

    def __iter__(self):
        return iter(self._listeners)


__all__ = [
    "WaterfallListener",
    "WaterfallListenerChain",
]
