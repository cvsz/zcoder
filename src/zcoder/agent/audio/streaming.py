"""
Audio streaming contracts for ZCoder.

Provides streaming audio interfaces and contracts for real-time audio processing.
"""

from __future__ import annotations

import abc
import asyncio
import queue
import threading
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

import numpy as np


@dataclass
class AudioStreamConfig:
    """Configuration for audio stream."""

    sample_rate: int = 16000
    channels: int = 1
    dtype: str = "int16"
    chunk_size: int = 1024
    buffer_size: int = 4096


@dataclass
class AudioChunk:
    """A chunk of audio data with metadata."""

    data: np.ndarray
    sample_rate: int
    channels: int
    timestamp: float
    is_final: bool = False
    sequence: int = 0


class AudioStream(abc.ABC):
    """Abstract base class for audio streams."""

    @abc.abstractmethod
    async def read(self) -> AudioChunk | None:
        """Read next audio chunk."""
        pass

    @abc.abstractmethod
    async def write(self, chunk: AudioChunk) -> None:
        """Write audio chunk to stream."""
        pass

    @abc.abstractmethod
    async def close(self) -> None:
        """Close the stream."""
        pass

    @abc.abstractmethod
    async def __aiter__(self) -> AsyncIterator[AudioChunk]:
        """Async iterator over audio chunks."""
        pass


class MemoryAudioStream(AudioStream):
    """In-memory audio stream for testing and local processing."""

    def __init__(self, config: AudioStreamConfig | None = None):
        self.config = config or AudioStreamConfig()
        self._queue: asyncio.Queue[AudioChunk] = asyncio.Queue()
        self._closed = False
        self._sequence = 0

    async def read(self) -> AudioChunk | None:
        if self._closed:
            return None
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=1.0)
        except TimeoutError:
            return None

    async def write(self, chunk: AudioChunk) -> None:
        if self._closed:
            raise RuntimeError("Stream is closed")
        chunk.sequence = self._sequence
        self._sequence += 1
        await self._queue.put(chunk)

    async def close(self) -> None:
        self._closed = True
        # Send final chunk
        final_chunk = AudioChunk(
            data=np.array([], dtype=np.int16),
            sample_rate=16000,
            channels=1,
            timestamp=0,
            is_final=True,
        )
        await self._queue.put(final_chunk)

    async def __aiter__(self):
        while not self._closed:
            chunk = await self.read()
            if chunk is None:
                continue
            if chunk.is_final:
                yield chunk
                break
            yield chunk


class CallbackAudioStream(AudioStream):
    """Audio stream that uses callbacks for read/write."""

    def __init__(
        self,
        read_callback: Callable[[], AudioChunk | None],
        write_callback: Callable[[AudioChunk], None],
        close_callback: Callable[[], None] | None = None,
    ):
        self._read_callback = read_callback
        self._write_callback = write_callback
        self._close_callback = close_callback

    async def read(self) -> AudioChunk | None:
        return await asyncio.to_thread(self._read_callback)

    async def write(self, chunk: AudioChunk) -> None:
        await asyncio.to_thread(self._write_callback, chunk)

    async def close(self) -> None:
        if self._close_callback:
            await asyncio.to_thread(self._close_callback)

    async def __aiter__(self):
        while True:
            chunk = await self.read()
            if chunk is None or chunk.is_final:
                if chunk:
                    yield chunk
                break
            yield chunk


class ThreadedAudioStream:
    """Thread-safe audio stream for synchronous code."""

    def __init__(self, config: AudioStreamConfig | None = None):
        self.config = config or AudioStreamConfig()
        self._queue: queue.Queue[AudioChunk] = queue.Queue(maxsize=100)
        self._closed = False
        self._sequence = 0
        self._lock = threading.Lock()

    def read(self, timeout: float = 1.0) -> AudioChunk | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def write(self, chunk: AudioChunk) -> None:
        with self._lock:
            if self._closed:
                raise RuntimeError("Stream is closed")
            chunk.sequence = self._sequence
            self._sequence += 1
            self._queue.put(chunk)

    def close(self) -> None:
        with self._lock:
            self._closed = True
            final_chunk = AudioChunk(
                data=np.array([], dtype=np.int16),
                sample_rate=16000,
                channels=1,
                timestamp=0,
                is_final=True,
            )
            self._queue.put(final_chunk)

    def __iter__(self):
        while not self._closed:
            chunk = self.read(timeout=1.0)
            if chunk is None:
                continue
            if chunk.is_final:
                yield chunk
                break
            yield chunk

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class AudioStreamMixer:
    """Mixes multiple audio streams into one."""

    def __init__(self, config: AudioStreamConfig | None = None):
        self.config = config or AudioStreamConfig()
        self._streams: list[AudioStream] = []
        self._mixed_queue: asyncio.Queue[AudioChunk] = asyncio.Queue()
        self._mixing_task: asyncio.Task | None = None
        self._closed = False

    def add_stream(self, stream: AudioStream) -> None:
        self._streams.append(stream)

    def remove_stream(self, stream: AudioStream) -> None:
        if stream in self._streams:
            self._streams.remove(stream)

    async def start(self) -> None:
        if self._mixing_task is not None:
            return
        self._closed = False
        self._mixing_task = asyncio.create_task(self._mix_loop())

    async def stop(self) -> None:
        self._closed = True
        if self._mixing_task:
            self._mixing_task.cancel()
            try:
                await self._mixing_task
            except asyncio.CancelledError:
                pass

    async def _mix_loop(self) -> None:
        while not self._closed:
            chunks = []
            for stream in self._streams:
                try:
                    chunk = await asyncio.wait_for(stream.read(), timeout=0.1)
                    if chunk:
                        chunks.append(chunk)
                except TimeoutError:
                    pass

            if chunks:
                # Simple mixing: sum all chunks
                mixed_data: np.ndarray = np.zeros_like(chunks[0].data, dtype=np.float32)
                for chunk in chunks:
                    if chunk.data.shape == mixed_data.shape:
                        mixed_data += chunk.data.astype(np.float32)

                # Normalize
                mixed_data = mixed_data / len(chunks)
                mixed_data = np.clip(mixed_data, -32768, 32767).astype(np.int16)

                # Here we would output the mixed chunk
                # For now, just acknowledge
                pass

            await asyncio.sleep(0.01)

    async def close(self) -> None:
        await self.stop()


def create_audio_stream(stream_type: str = "memory", **kwargs) -> AudioStream | AudioStreamMixer:
    """Factory function to create audio stream.

    Args:
        stream_type: "memory", "callback", or "mixer"
        **kwargs: Stream-specific arguments

    Returns:
        AudioStream or AudioStreamMixer instance
    """
    if stream_type == "memory":
        return MemoryAudioStream(**kwargs)
    elif stream_type == "callback":
        return CallbackAudioStream(**kwargs)
    elif stream_type == "mixer":
        return AudioStreamMixer(**kwargs)
    else:
        raise ValueError(f"Unknown stream type: {stream_type}")
