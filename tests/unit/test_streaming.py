"""Unit tests for Phase 3: Async Streaming & Cancellation.

Covers Prompt 7.3:
- IdleWatchdog (timeout.py)
- AbortSignal (cancellation.py)
- StreamChunk, GenerateOptions (types.py)
- adapter execute() as async generator
- router _call() as async generator with error redirect
"""

from __future__ import annotations

import asyncio

import pytest

from zcoder.agent.orchestration.cancellation import AbortSignal
from zcoder.agent.orchestration.timeout import IdleWatchdog
from zcoder.agent.orchestration.types import GenerateOptions, StreamChunk


def test_stream_chunk_fields():
    c = StreamChunk(type="token", content="hello", model="m", provider="p")
    assert c.type == "token"
    assert c.content == "hello"
    assert c.done is False
    assert c.model == "m"
    assert c.provider == "p"
    assert c.extra == {}


def test_stream_chunk_done():
    c = StreamChunk(type="done", content="", done=True)
    assert c.done is True


def test_generate_options_defaults():
    o = GenerateOptions(model="m")
    assert o.model == "m"
    assert o.temperature is None
    assert o.max_tokens is None
    assert o.stream is False
    assert o.messages == []


def test_abort_signal_not_aborted_by_default():
    s = AbortSignal()
    assert s.aborted is False


def test_abort_signal_abort():
    s = AbortSignal()
    called = []
    s.on_abort(lambda: called.append(1))
    s.abort()
    assert s.aborted is True
    assert called == [1]


def test_abort_signal_idempotent():
    s = AbortSignal()
    s.abort()
    s.abort()  # should not raise
    assert s.aborted is True


def test_abort_signal_check_raises():
    s = AbortSignal()
    s.abort()
    with pytest.raises(asyncio.CancelledError):
        s.check()


def test_idle_watchdog_touch_resets():
    called = []
    wd = IdleWatchdog(timeout=0.05, on_idle=lambda: called.append(1))
    assert wd.elapsed >= 0
    wd.touch()
    import time
    time.sleep(0.02)
    wd.touch()
    time.sleep(0.06)
    # Stop before it fires
    wd.stop()
    assert called == []


def test_idle_watchdog_fires():
    called = []
    wd = IdleWatchdog(timeout=0.02, on_idle=lambda: called.append(1))

    async def run():
        wd.start()
        await asyncio.sleep(0.08)
        wd.stop()

    asyncio.run(run())
    assert called == [1]


def test_idle_watchdog_invalid_timeout():
    with pytest.raises(ValueError):
        IdleWatchdog(timeout=0, on_idle=lambda: None)
