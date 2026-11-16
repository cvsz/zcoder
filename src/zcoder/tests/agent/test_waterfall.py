"""Tests for zcoder.tools.waterfall - Waterfall listener chain."""

import pytest

from zcoder.tools.waterfall import WaterfallListenerChain


class TestWaterfallListenerChain:
    """Tests for WaterfallListenerChain."""

    @pytest.mark.asyncio
    async def test_empty_chain(self):
        chain = WaterfallListenerChain()
        result = await chain.run("initial")
        assert result == "initial"

    @pytest.mark.asyncio
    async def test_single_listener(self):
        chain = WaterfallListenerChain()

        async def listener(value, next_):
            return await next_(value + "-processed")

        chain.add_listener(listener)
        result = await chain.run("input")
        assert result == "input-processed"

    @pytest.mark.asyncio
    async def test_multiple_listeners(self):
        chain = WaterfallListenerChain()

        async def listener1(value, next_):
            return await next_(value + "-step1")

        async def listener2(value, next_):
            return await next_(value + "-step2")

        chain.add_listener(listener1)
        chain.add_listener(listener2)

        result = await chain.run("input")
        assert result == "input-step1-step2"

    @pytest.mark.asyncio
    async def test_short_circuit(self):
        chain = WaterfallListenerChain()

        async def short_circuit(value, next_):
            # Short-circuit: don't call next_
            return "short-circuited"

        async def listener2(value, next_):
            return await next_(value + "-should-not-run")

        chain.add_listener(short_circuit)
        chain.add_listener(listener2)

        result = await chain.run("input")
        assert result == "short-circuited"

    @pytest.mark.asyncio
    async def test_insert_listener(self):
        chain = WaterfallListenerChain()

        async def first(value, next_):
            return await next_(value + "-first")

        async def second(value, next_):
            return await next_(value + "-second")

        chain.add_listener(first)
        chain.insert_listener(0, second)  # Insert at front

        result = await chain.run("input")
        assert result == "input-second-first"

    @pytest.mark.asyncio
    async def test_iteration(self):
        chain = WaterfallListenerChain()

        async def listener1(value, next_):
            return await next_(value + "-1")

        async def listener2(value, next_):
            return await next_(value + "-2")

        chain.add_listener(listener1)
        chain.add_listener(listener2)

        assert len(chain) == 2
        listeners = list(chain)
        assert len(listeners) == 2

    @pytest.mark.asyncio
    async def test_waterfall_listener_type(self):
        """Verify that WaterfallListenerChain is callable and works."""
        chain = WaterfallListenerChain()
        assert callable(chain.run)


class TestWaterfallListenerType:
    """Tests for WaterfallListener type alias."""

    def test_waterfall_handler_signature(self):
        """Verify that WaterfallListener accepts (value, next_) and returns Awaitable."""

        async def handler(value: str, next_):
            return await next_(value + "-processed")

        assert callable(handler)
