"""Tests for zcoder.services.llm.streaming - async streaming service."""

import pytest

from zcoder.agent.orchestration.cancellation import AbortSignal
from zcoder.services.llm.streaming import StreamableLLMProvider, collect_stream
from zcoder.services.llm.types import GenerateOptions, GenerateResult, StreamChunk


class _FakeProvider:
    """Fake LLMProvider for testing streaming."""

    def __init__(self, chunks: list[StreamChunk] | None = None, error: Exception | None = None):
        self._chunks = chunks or [
            StreamChunk(type="token", content="Hello", delta="Hello", provider="test"),
            StreamChunk(type="token", content=" world", delta=" world", provider="test"),
            StreamChunk(type="done", done=True, provider="test"),
        ]
        self._error = error
        self.provider_name = "test"

    async def generate(self, options):
        raise NotImplementedError("not used in streaming tests")

    async def generate_stream(self, options):
        if self._error:
            raise self._error
        for chunk in self._chunks:
            yield chunk


class TestStreamableLLMProvider:
    """Tests for StreamableLLMProvider wrapper."""

    def test_provider_name_delegates(self):
        provider = _FakeProvider()
        signal = AbortSignal()
        wrapped = StreamableLLMProvider(provider, signal)
        assert wrapped.provider_name == "test"

    @pytest.mark.asyncio
    async def test_stream_normal(self):
        provider = _FakeProvider()
        signal = AbortSignal()
        wrapped = StreamableLLMProvider(provider, signal)

        chunks = []
        async for chunk in wrapped.generate_stream(
            GenerateOptions(model="test", messages=[{"role": "user", "content": "Hi"}])
        ):
            chunks.append(chunk)

        assert len(chunks) == 3
        assert chunks[0].type == "token"
        assert chunks[0].delta == "Hello"
        assert chunks[1].delta == " world"
        assert chunks[2].type == "done"
        assert chunks[2].done is True

    @pytest.mark.asyncio
    async def test_stream_aborted(self):
        provider = _FakeProvider()
        signal = AbortSignal()
        wrapped = StreamableLLMProvider(provider, signal)

        # Abort after first chunk
        chunks = []
        async for chunk in wrapped.generate_stream(
            GenerateOptions(model="test", messages=[{"role": "user", "content": "Hi"}])
        ):
            chunks.append(chunk)
            if len(chunks) == 1:
                signal.abort()

        # Should yield the abort marker chunk
        assert any(c.type == "done" and c.extra.get("aborted") for c in chunks)

    @pytest.mark.asyncio
    async def test_stream_stops_on_done(self):
        provider = _FakeProvider()
        signal = AbortSignal()
        wrapped = StreamableLLMProvider(provider, signal)

        chunks = []
        async for chunk in wrapped.generate_stream(
            GenerateOptions(model="test", messages=[{"role": "user", "content": "Hi"}])
        ):
            chunks.append(chunk)

        # Should stop at done chunk
        assert chunks[-1].done is True
        assert len(chunks) == 3


class TestCollectStream:
    """Tests for collect_stream helper."""

    @pytest.mark.asyncio
    async def test_collect_tokens(self):
        chunks = [
            StreamChunk(type="token", content="Hello", delta="Hello", provider="test", model="test-model"),
            StreamChunk(type="token", content=" world", delta=" world", provider="test"),
            StreamChunk(type="done", done=True, provider="test"),
        ]

        result = await collect_stream(_aiter(chunks))

        assert isinstance(result, GenerateResult)
        assert result.content == "Hello world"
        assert result.model == "test-model"
        assert result.provider == "test"

    @pytest.mark.asyncio
    async def test_collect_error(self):
        chunks = [
            StreamChunk(type="error", content="Something went wrong", provider="test"),
        ]

        with pytest.raises(RuntimeError, match="Stream error"):
            await collect_stream(_aiter(chunks))

    @pytest.mark.asyncio
    async def test_collect_empty(self):
        result = await collect_stream(_aiter([]))

        assert isinstance(result, GenerateResult)
        assert result.content == ""
        assert result.model == ""
        assert result.provider == ""


async def _aiter(items):
    """Helper to turn a list into an async iterator."""
    for item in items:
        yield item
